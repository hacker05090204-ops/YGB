#!/usr/bin/env python3
"""Phase 1: Mock/Fake/Simulated Data Detection"""
import subprocess
from pathlib import Path

PATTERNS = {
    'CRITICAL_FAKE': [
        'np.random.rand',
        'np.random.randn',
        'np.random.randint',
        'torch.randn',
        'torch.rand(',
        'random.random()',
        'random.uniform(',
        'fake_',
        '_fake',
        'mock_data',
        'synthetic_',
        'simulated_',
        'placeholder_',
        'dummy_data',
        'test_data_generation',
        'generate_fake',
        'fabricat',
    ],
    'CRITICAL_BYPASS': [
        'return True  # bypass',
        'skip_verification',
        'bypass_auth',
        'TEMP_AUTH_BYPASS',
        'skip_validation',
        'return []  # TODO',
        'pass  # implement',
        '# TODO: implement',
        '# FIXME: not implemented',
        'raise NotImplementedError',
        'return {}  # placeholder',
        'return None  # TODO',
    ],
    'CRITICAL_HARDCODED': [
        'return 0.95',
        'return 0.87',
        'accuracy = 1.0',
        'f1 = 0.9',
        'val_f1 = 0.8',
        'hardcoded',
    ],
    'WARNING_MOCK': [
        'mock.patch',
        'MagicMock',
        'Mock(',
        'unittest.mock',
        '_mock_',
        'mock_response',
        'mock_send',
        'mock_update',
        '_demo_handler',
        'demo_mode',
    ],
    'WARNING_INCOMPLETE': [
        'except: pass',
        'except Exception: pass',
        'bare_pass',
        '# not yet implemented',
        '# coming soon',
        '# TODO',
        '# FIXME',
        '# HACK',
    ],
}

print('='*70)
print('MOCK / FAKE / SIMULATED CODE DETECTION')
print('='*70)

results = {}
for severity, patterns in PATTERNS.items():
    print(f'\n--- {severity} ---')
    category_hits = []
    for pattern in patterns:
        try:
            r = subprocess.run(
                ['grep', '-rn', '--include=*.py', pattern, '.'],
                capture_output=True, text=True, timeout=30
            )
            hits = [l for l in r.stdout.split('\n')
                    if l.strip() and '__pycache__' not in l
                    and '/test_' not in l.split(':')[0]]
            if hits:
                print(f'  [{len(hits):3d} hits] {pattern}')
                for h in hits[:2]:
                    print(f'    {h.strip()[:100]}')
                category_hits.extend(hits)
        except subprocess.TimeoutExpired:
            print(f'  [TIMEOUT] {pattern}')
        except Exception as e:
            print(f'  [ERROR] {pattern}: {e}')
    results[severity] = len(category_hits)

print()
print('SUMMARY:')
for k, v in results.items():
    status = 'ACTION REQUIRED' if v > 0 and 'CRITICAL' in k else 'REVIEW'
    print(f'  {k}: {v} hits — {status}')
