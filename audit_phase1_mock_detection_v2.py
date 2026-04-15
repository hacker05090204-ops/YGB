from pathlib import Path
import re

PATTERNS = {
    'CRITICAL_FAKE': [
        'np.random.rand',
        'torch.randn',
        'torch.rand(',
        'fake_',
        'mock_data',
        'synthetic_',
        'placeholder_',
        'dummy_data',
    ],
    'CRITICAL_BYPASS': [
        'return True  # bypass',
        'skip_verification',
        'bypass_auth',
        'TEMP_AUTH_BYPASS',
        'raise NotImplementedError',
    ],
    'CRITICAL_HARDCODED': [
        'return 0.95',
        'accuracy = 1.0',
        'hardcoded',
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
        hits = []
        for py_file in Path('.').rglob('*.py'):
            if '__pycache__' in str(py_file) or 'test_' in py_file.name:
                continue
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                for i, line in enumerate(content.splitlines(), 1):
                    if pattern in line:
                        hits.append(f'{py_file}:{i}:{line.strip()[:80]}')
            except (OSError, UnicodeDecodeError, PermissionError):
                pass
        
        if hits:
            print(f'  [{len(hits):3d} hits] {pattern}')
            for h in hits[:3]:
                print(f'    {h}')
            category_hits.extend(hits)
    results[severity] = len(category_hits)

print()
print('SUMMARY:')
for k, v in results.items():
    status = 'ACTION REQUIRED' if v > 0 and 'CRITICAL' in k else 'REVIEW'
    print(f'  {k}: {v} hits — {status}')
