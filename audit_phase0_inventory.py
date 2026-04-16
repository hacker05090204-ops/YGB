#!/usr/bin/env python3
"""Phase 0: Repository Inventory"""
import os
import logging
from pathlib import Path
from collections import Counter

logger = logging.getLogger(__name__)

print('='*70)
print('REPOSITORY INVENTORY')
print('='*70)

ext_counts = Counter()
total_lines = 0
total_files = 0

for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in('.git','__pycache__','.pytest_cache','node_modules')]
    for f in files:
        ext = Path(f).suffix.lower()
        ext_counts[ext] += 1
        total_files += 1
        if ext == '.py':
            try:
                fpath = Path(os.path.join(root,f))
                lines = len(fpath.read_text(encoding='utf-8', errors='ignore').splitlines())
                total_lines += lines
            except Exception as e:
                logger.debug("audit: file read failed: %s", repr(e))

print(f'Total files: {total_files}')
print(f'Python files: {ext_counts[".py"]}')
print(f'Python lines: {total_lines:,}')

test_files = []
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ('.git','__pycache__')]
    for f in files:
        if f.startswith('test_') and f.endswith('.py'):
            test_files.append(os.path.join(root, f))

print(f'Test files found: {len(test_files)}')
print()
print('Top-level directories:')
for item in sorted(Path('.').iterdir()):
    if item.is_dir() and not item.name.startswith('.'):
        py_count = len(list(item.rglob('*.py')))
        print(f'  {item.name}/  ({py_count} python files)')

# Count classes and functions
print()
print('Code structure analysis:')
total_classes = 0
total_functions = 0
markers = {}

for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in('.git','__pycache__','.pytest_cache')]
    for f in files:
        if f.endswith('.py'):
            try:
                fpath = Path(os.path.join(root, f))
                content = fpath.read_text(encoding='utf-8', errors='ignore')
                total_classes += content.count('\nclass ')
                total_functions += content.count('\ndef ')
                
                # Check for markers
                for marker in ['TODO', 'FIXME', 'HACK', 'PLACEHOLDER', 'NOT IMPLEMENTED', 
                               'STUB', 'MOCK', 'FAKE', 'SIMULATED', 'NotImplementedError']:
                    count = content.upper().count(marker.upper())
                    if count > 0:
                        markers[marker] = markers.get(marker, 0) + count
            except Exception as e:
                logger.debug("audit: marker scan failed: %s", repr(e))

print(f'Total classes: {total_classes}')
print(f'Total functions/methods: {total_functions}')
print()
print('Code quality markers:')
for marker, count in sorted(markers.items(), key=lambda x: -x[1])[:10]:
    print(f'  {marker}: {count} occurrences')
