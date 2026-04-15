"""YBG Complete Self-Analysis - Step 0"""
import os, subprocess, sys
from pathlib import Path
from collections import Counter
import json

print('='*70)
print('YBG COMPLETE SELF-ANALYSIS')
print('='*70)
checks = {}

# 1. Test baseline
print("\n[1/9] Running test baseline...")
try:
    r = subprocess.run(['python','-m','pytest','-q','--tb=no'],
                      capture_output=True, text=True, timeout=60)
    lines = [l for l in r.stdout.split('\n') if 'passed' in l or 'failed' in l]
    checks['test_baseline'] = lines[0] if lines else 'UNKNOWN'
    print(f'Tests: {checks["test_baseline"]}')
except Exception as e:
    checks['test_baseline'] = f'ERROR: {e}'
    print(f'Tests: ERROR - {e}')

# 2. MoE wired in training_controller?
print("\n[2/9] Checking MoE wiring...")
try:
    with open('training_controller.py', 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    moe_refs = content.count('MoEClassifier') + content.count('YGB_USE_MOE')
    checks['moe_in_controller'] = moe_refs > 0
    print(f'MoE in training_controller.py: {"YES" if moe_refs>0 else "NO — CRITICAL"} ({moe_refs} refs)')
except Exception as e:
    checks['moe_in_controller'] = False
    print(f'MoE check: ERROR - {e}')

# 3. What model is actually built?
print("\n[3/9] Testing model build...")
os.environ['YGB_USE_MOE'] = 'true'
try:
    sys.path.insert(0, os.getcwd())
    from impl_v1.phase49.moe import MoEClassifier, MoEConfig
    
    # Try to build model
    config = MoEConfig(
        d_model=1024, n_experts=23, top_k=2,
        expert_hidden_mult=2, dropout=0.3,
        gate_noise=1.0, aux_loss_coeff=0.01
    )
    config.expert_hidden_dim = 1024
    config.expert_n_layers = 4
    config.expert_n_heads = 8
    
    model = MoEClassifier(config, input_dim=267, output_dim=5)
    params = sum(p.numel() for p in model.parameters())
    checks['model_params'] = params
    checks['model_class'] = type(model).__name__
    print(f'Model: {type(model).__name__} ({params:,} params / {params/1e6:.2f}M)')
    if params < 500_000:
        print('  *** CRITICAL: Still < 500K — MoE NOT PROPERLY SCALED ***')
except Exception as e:
    checks['model_error'] = str(e)
    print(f'Model build: ERROR - {e}')

# 4. Bare excepts (Windows-compatible)
print("\n[4/9] Checking bare except violations...")
try:
    violations = []
    for root_dir in ['backend', 'impl_v1', 'scripts']:
        if Path(root_dir).exists():
            for py_file in Path(root_dir).rglob('*.py'):
                try:
                    content = py_file.read_text(encoding='utf-8', errors='ignore')
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        stripped = line.strip()
                        # Skip comments and strings
                        if stripped.startswith('#') or stripped.startswith('"') or stripped.startswith("'"):
                            continue
                        # Check for bare except: (must be actual code, not in string literals)
                        if 'except:' in line and stripped.endswith('except:'):
                            # Make sure it's not checking for except: (like in test code)
                            if "'except:'" not in line and '"except:"' not in line:
                                violations.append(f'{py_file}:{i}')
                        elif 'except Exception:' in line and i < len(lines):
                            next_line = lines[i].strip() if i < len(lines) else ''
                            if next_line == 'pass':
                                violations.append(f'{py_file}:{i}')
                except (OSError, UnicodeDecodeError, PermissionError):
                    pass
    checks['bare_excepts'] = len(violations)
    print(f'Bare except violations: {len(violations)} (target: 0)')
    if violations and len(violations) < 10:
        for v in violations[:5]:
            print(f'  - {v}')
except Exception as e:
    checks['bare_excepts'] = 'ERROR'
    print(f'Bare except check: ERROR - {e}')

# 5. Expert queue
print("\n[5/9] Checking expert queue...")
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
print("\n[6/9] Checking checkpoints...")
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
    checks['per_expert_checkpoints'] = 0
    checks['global_checkpoints'] = 0

# 7. Scrapers
print("\n[7/9] Checking scrapers...")
scrapers_dir = Path('backend/ingestion/scrapers')
if scrapers_dir.exists():
    scrapers = [f.stem for f in scrapers_dir.glob('*.py')
                if f.stem not in ('__init__','base_scraper')]
    checks['scrapers'] = scrapers
    print(f'Scrapers ({len(scrapers)}): {scrapers}')
else:
    print('Scrapers: MISSING DIRECTORY')
    checks['scrapers'] = []

# 8. Wiring checks
print("\n[8/9] Checking component wiring...")
wiring = {}
files_to_check = {
    'RL→trainer': ('backend/training/incremental_trainer.py',
                   ['get_reward_buffer','sample_weights','rl_feedback']),
    'EWC→trainer': ('backend/training/incremental_trainer.py',
                    ['ewc_loss','AdaptiveLearner','get_ewc_loss']),
    'ClassBalancer→trainer': ('backend/training/incremental_trainer.py',
                              ['ClassBalancer','class_weights']),
}

for name, (filepath, keywords) in files_to_check.items():
    p = Path(filepath)
    if not p.exists():
        wiring[name] = 'FILE MISSING'
        print(f'  ✗ {name}: FILE MISSING')
        continue
    try:
        content = p.read_text(encoding='utf-8', errors='ignore')
        found = [k for k in keywords if k in content]
        wiring[name] = f'WIRED ({len(found)}/{len(keywords)})' if found else 'NOT WIRED'
        status = '✓' if found else '✗'
        print(f'  {status} {name}: {wiring[name]}')
    except Exception as e:
        wiring[name] = f'ERROR: {e}'
        print(f'  ✗ {name}: ERROR')

# 9. Security gaps
print("\n[9/9] Checking security...")
sec = {}
ag_path = Path('backend/auth/auth_guard.py')
if ag_path.exists():
    try:
        ag_content = ag_path.read_text(encoding='utf-8', errors='ignore')
        sec['bypass_exists'] = 'is_temporary_auth_bypass_enabled' in ag_content
        sec['bypass_prod_gated'] = ('YGB_ENV' in ag_content and 'production' in ag_content)
        print(f'Auth bypass: exists={sec.get("bypass_exists")} prod_gated={sec.get("bypass_prod_gated")}')
    except Exception as e:
        print(f'Auth check: ERROR - {e}')

# Save results
print('\n' + '='*70)
output_path = Path('.tmp_hdd_drive/ybg_analysis.json')
output_path.parent.mkdir(exist_ok=True)
with open(output_path, 'w') as f:
    json.dump({'checks': checks, 'wiring': wiring, 'security': sec}, f, indent=2)
print(f'Analysis written to {output_path}')
print('='*70)

# Summary
print('\nSUMMARY:')
print(f'  MoE wired: {"YES" if checks.get("moe_in_controller") else "NO"}')
print(f'  Model params: {checks.get("model_params", "UNKNOWN"):,}' if isinstance(checks.get("model_params"), int) else f'  Model params: {checks.get("model_params", "UNKNOWN")}')
print(f'  Bare excepts: {checks.get("bare_excepts", "UNKNOWN")}')
print(f'  Scrapers: {len(checks.get("scrapers", []))}')
print(f'  Expert queue: {checks.get("expert_queue", "ERROR")}')
