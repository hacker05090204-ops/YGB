import os, subprocess
from pathlib import Path
from collections import Counter
import json

print('='*70)
print('YBG COMPLETE SELF-ANALYSIS')
print('='*70)

checks = {}

# 1. Test baseline
r = subprocess.run(['python','-m','pytest','-q','--tb=no'],
                   capture_output=True, text=True, timeout=30)
lines = [l for l in r.stdout.split('\n') if 'passed' in l or 'failed' in l]
checks['test_baseline'] = lines[0] if lines else 'UNKNOWN'
print(f'Tests: {checks["test_baseline"]}')

# 2. MoE wired?
moe_refs = 0
tc_path = Path('training_controller.py')
if tc_path.exists():
    try:
        content = tc_path.read_text(encoding='utf-8', errors='ignore')
        moe_refs = content.count('MoEClassifier') + content.count('YGB_USE_MOE')
    except Exception as e:
        print(f'  Warning: Could not read training_controller.py: {e}')
checks['moe_in_controller'] = moe_refs > 0
print(f'MoE in training_controller.py: {"YES" if moe_refs>0 else "NO — CRITICAL"}')

# 3. What model is actually built?
os.environ['YGB_USE_MOE'] = 'true'
try:
    from training_controller import _build_configured_model
    m = _build_configured_model()
    params = sum(p.numel() for p in m.parameters())
    checks['model_params'] = params
    checks['model_class'] = type(m).__name__
    print(f'Model: {type(m).__name__} ({params:,} params / {params/1e6:.2f}M)')
    if params < 500_000:
        print('  *** CRITICAL: Still 296K BugClassifier — MoE NOT WIRED ***')
except Exception as e:
    checks['model_error'] = str(e)
    print(f'Model build failed: {e}')

# 4. Bare excepts
bare = 0
import re
for directory in ['backend', 'impl_v1', 'scripts']:
    dir_path = Path(directory)
    if dir_path.exists():
        for py_file in dir_path.rglob('*.py'):
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                # Count bare except patterns
                bare += len(re.findall(r'except\s*:\s*$', content, re.MULTILINE))
                bare += len(re.findall(r'except\s+Exception\s*:\s*pass', content))
                bare += len(re.findall(r'except\s+.*:\s*pass', content))
            except Exception as e:
                logger.debug("run_self_analysis: file read failed: %s", repr(e))
checks['bare_excepts'] = bare
print(f'Bare except:pass violations: {bare} (target: 0)')

# 5. Expert queue
try:
    from scripts.expert_task_queue import ExpertTaskQueue
    q = ExpertTaskQueue()
    statuses = q.get_status()
    dist = Counter(e.status for e in statuses)
    checks['expert_queue'] = dict(dist)
    print(f'Expert queue: {len(statuses)} experts — {dict(dist)}')
except Exception as e:
    checks['expert_queue_error'] = str(e)
    print(f'Expert queue: ERROR — {e}')

# 6. Per-expert checkpoints
ckpt_dir = Path('checkpoints')
if ckpt_dir.exists():
    expert_ckpts = list(ckpt_dir.glob('expert_*.safetensors'))
    global_ckpts = list(ckpt_dir.glob('g38_*.safetensors'))
    checks['per_expert_checkpoints'] = len(expert_ckpts)
    checks['global_checkpoints'] = len(global_ckpts)
    print(f'Per-expert checkpoints: {len(expert_ckpts)}')
    print(f'Global checkpoints: {len(global_ckpts)}')
else:
    print('Checkpoints dir: MISSING')

# 7. Scrapers
scrapers_dir = Path('backend/ingestion/scrapers')
if scrapers_dir.exists():
    scrapers = [f.stem for f in scrapers_dir.glob('*.py')
                if f.stem not in ('__init__','base_scraper')]
    checks['scrapers'] = scrapers
    print(f'Scrapers ({len(scrapers)}): {scrapers}')
else:
    print('Scrapers: MISSING DIRECTORY')

# 8. Wiring checks
wiring = {}
files_to_check = {
    'RL→trainer': ('backend/training/incremental_trainer.py',
                   ['get_reward_buffer','sample_weights','rl_feedback']),
    'EWC→trainer': ('backend/training/incremental_trainer.py',
                    ['ewc_loss','AdaptiveLearner','get_ewc_loss']),
    'ClassBalancer→trainer': ('backend/training/incremental_trainer.py',
                              ['ClassBalancer','class_weights']),
    'LabelSmoothing→trainer': ('backend/training/incremental_trainer.py',
                               ['label_smoothing']),
    'EarlyStopping→trainer': ('backend/training/incremental_trainer.py',
                              ['EarlyStopping']),
    'AMP→trainer': ('backend/training/incremental_trainer.py',
                    ['GradScaler','autocast']),
    'GroundingValidator→router': ('backend/assistant/query_router.py',
                                  ['GroundingValidator']),
    'Distribution→autograbber': ('backend/ingestion/autograbber.py',
                                 ['on_new_grab_cycle','DistributionMonitor']),
    'AllScrapers→autograbber': ('backend/ingestion/autograbber.py',
                                ['exploitdb','msrc','redhat','snyk','vulnrichment']),
    'Cache→system_status': ('backend/api/system_status.py',
                            ['_cache_ts','CACHE_TTL','_trigger_background']),
    'SyncMode→sync_engine': ('backend/sync/sync_engine.py',
                             ['SyncMode','STANDALONE','get_sync_mode']),
    'Workflow→industrial_agent': ('backend/tasks/industrial_agent.py',
                                  ['AutonomousWorkflowOrchestrator','WorkflowCycleResult']),
}

for name, (filepath, keywords) in files_to_check.items():
    p = Path(filepath)
    if not p.exists():
        wiring[name] = 'FILE MISSING'
        continue
    try:
        content = p.read_text(encoding='utf-8', errors='ignore')
        found = [k for k in keywords if k in content]
        wiring[name] = f'WIRED ({len(found)}/{len(keywords)})' if found else 'NOT WIRED'
        status = '✓' if found else '✗'
        print(f'  {status} {name}: {wiring[name]}')
    except Exception as e:
        wiring[name] = f'ERROR: {str(e)[:30]}'
        print(f'  ✗ {name}: {wiring[name]}')

# 9. Security gaps
sec = {}
ag_path = Path('backend/auth/auth_guard.py')
if ag_path.exists():
    try:
        ag_content = ag_path.read_text(encoding='utf-8', errors='ignore')
        sec['bypass_exists'] = 'is_temporary_auth_bypass_enabled' in ag_content
        sec['bypass_prod_gated'] = ('YGB_ENV' in ag_content and 'production' in ag_content)
        print(f'Auth bypass: exists={sec.get("bypass_exists")} prod_gated={sec.get("bypass_prod_gated")}')
    except Exception as e:
        print(f'Auth guard check failed: {e}')

with open('/tmp/ybg_analysis.json','w') as f:
    json.dump({'checks': checks, 'wiring': wiring, 'security': sec}, f, indent=2)

print('\nAnalysis written to /tmp/ybg_analysis.json')
print('='*70)
