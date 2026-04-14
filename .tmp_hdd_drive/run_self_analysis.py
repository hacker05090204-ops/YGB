"""YBG Self-Analysis Script"""
import os, subprocess, sys
from pathlib import Path
from collections import Counter
import json

print('='*70)
print('YBG COMPLETE SELF-ANALYSIS')
print('='*70)
checks = {}

# 1. Test baseline
try:
    r = subprocess.run(['python','-m','pytest','-q','--tb=no'],
                      capture_output=True, text=True, timeout=30)
    lines = [l for l in r.stdout.split('\n') if 'passed' in l or 'failed' in l]
    checks['test_baseline'] = lines[0] if lines else 'UNKNOWN'
    print(f"Tests: {checks['test_baseline']}")
except Exception as e:
    checks['test_baseline'] = f'ERROR: {e}'
    print(f"Tests: ERROR - {e}")

# 2. MoE wired?
try:
    with open('training_controller.py', 'r') as f:
        content = f.read()
    moe_refs = content.count('MoEClassifier') + content.count('YGB_USE_MOE')
    checks['moe_in_controller'] = moe_refs > 0
    print(f"MoE in training_controller.py: {'YES' if moe_refs>0 else 'NO — CRITICAL'} ({moe_refs} refs)")
except Exception as e:
    checks['moe_in_controller'] = False
    print(f"MoE check: ERROR - {e}")

# 3. Model params check
os.environ['YGB_USE_MOE'] = 'true'
try:
    sys.path.insert(0, os.getcwd())
    # Just check if MoE module exists
    from impl_v1.phase49.moe import MoEClassifier
    checks['moe_module_exists'] = True
    print("MoE module: EXISTS")
except ImportError as e:
    checks['moe_module_exists'] = False
    checks['moe_import_error'] = str(e)
    print(f"MoE module: MISSING - {e}")

# 4. Bare excepts count
try:
    r3 = subprocess.run(['grep','-rn','--include=*.py',
                        'except:$','backend/','impl_v1/','scripts/'],
                       capture_output=True, text=True, timeout=30)
    bare = len([l for l in r3.stdout.split('\n') if l.strip() and ':' in l])
    checks['bare_excepts'] = bare
    print(f"Bare except violations: {bare} (target: 0)")
except Exception as e:
    checks['bare_excepts'] = 'ERROR'
    print(f"Bare except check: ERROR - {e}")

# 5. Check impl_v1/phase49/moe directory
moe_dir = Path('impl_v1/phase49/moe')
if moe_dir.exists():
    moe_files = list(moe_dir.glob('*.py'))
    checks['moe_files'] = [f.name for f in moe_files]
    print(f"MoE files: {len(moe_files)} files found")
else:
    checks['moe_files'] = []
    print("MoE directory: NOT FOUND")

# 6. Check scrapers
scrapers_dir = Path('backend/ingestion/scrapers')
if scrapers_dir.exists():
    scrapers = [f.stem for f in scrapers_dir.glob('*.py')
                if f.stem not in ('__init__','base_scraper')]
    checks['scrapers'] = scrapers
    print(f"Scrapers ({len(scrapers)}): {scrapers}")
else:
    checks['scrapers'] = []
    print("Scrapers: MISSING DIRECTORY")

print('='*70)
Path('.tmp_hdd_drive').mkdir(exist_ok=True)
with open('.tmp_hdd_drive/ybg_analysis.json','w') as f:
    json.dump({'checks': checks}, f, indent=2)
print('Analysis written to .tmp_hdd_drive/ybg_analysis.json')
