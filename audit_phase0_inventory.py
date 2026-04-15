import os
from pathlib import Path
from collections import Counter

print('='*70)
print('REPOSITORY INVENTORY')
print('='*70)

# File counts by type
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
                lines = len(Path(os.path.join(root,f)).read_text(encoding='utf-8', errors='ignore').splitlines())
                total_lines += lines
            except: 
                pass

print(f'Total files: {total_files}')
print(f'Python files: {ext_counts[".py"]}')
print(f'Python lines: {total_lines:,}')
print()

# Count test files specifically
test_files = []
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ('.git','__pycache__')]
    for f in files:
        if f.startswith('test_') and f.endswith('.py'):
            test_files.append(os.path.join(root, f))

print(f'Test files found: {len(test_files)}')

# Top-level structure
print()
print('Top-level directories:')
for item in sorted(Path('.').iterdir()):
    if item.is_dir() and not item.name.startswith('.'):
        py_count = len(list(item.rglob('*.py')))
        print(f'  {item.name}/  ({py_count} python files)')
