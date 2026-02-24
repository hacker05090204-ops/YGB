"""
Full codebase scan for remediation patterns.
Classifies hits as: PRODUCTION, TEST, THIRD_PARTY, CONFIG, DOCS
"""
import os
import re
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PATTERNS = {
    'mock': re.compile(r'\bmock\b', re.IGNORECASE),
    'simulate': re.compile(r'\bsimulat', re.IGNORECASE),
    'stimulate': re.compile(r'\bstimulat', re.IGNORECASE),
    'partial': re.compile(r'\bpartial\b', re.IGNORECASE),
    'stub': re.compile(r'\bstub\b', re.IGNORECASE),
    'placeholder': re.compile(r'\bplaceholder\b', re.IGNORECASE),
    'synthetic': re.compile(r'\bsynthetic\b', re.IGNORECASE),
    'not_implemented': re.compile(r'not.implement|NotImplemented', re.IGNORECASE),
    'todo': re.compile(r'\bTODO\b'),
    'fixme': re.compile(r'\bFIXME\b'),
}

EXCLUDED_DIRS = {'.git', 'node_modules', '__pycache__', '.next', '.gemini', 'dist', 'build'}
SCAN_EXTENSIONS = {'.py', '.ts', '.tsx', '.js', '.jsx', '.cpp', '.h', '.c', '.css',
                   '.json', '.env', '.yml', '.yaml', '.toml', '.cfg'}


def classify_path(filepath):
    rel = os.path.relpath(filepath, PROJECT_ROOT).replace('\\', '/')
    parts = rel.split('/')
    
    if any(p in ('tests', 'test', '__tests__') for p in parts):
        return 'TEST'
    if any(f.startswith('test_') or f.endswith('_test.py') for f in [parts[-1]]):
        return 'TEST'
    if 'node_modules' in parts or 'vendor' in parts:
        return 'THIRD_PARTY'
    if parts[-1].endswith(('.md', '.txt', '.yml', '.yaml', '.toml', '.cfg', '.json')):
        return 'CONFIG/DOCS'
    return 'PRODUCTION'


def scan():
    results = {}
    summary = {}
    
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in SCAN_EXTENSIONS:
                continue
            
            filepath = os.path.join(root, f)
            rel = os.path.relpath(filepath, PROJECT_ROOT).replace('\\', '/')
            classification = classify_path(filepath)
            
            try:
                content = open(filepath, 'r', encoding='utf-8', errors='ignore').read()
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    for pname, pat in PATTERNS.items():
                        if pat.search(line):
                            key = f"{pname}|{classification}"
                            summary[key] = summary.get(key, 0) + 1
                            if classification == 'PRODUCTION':
                                results.setdefault(pname, [])
                                results[pname].append({
                                    'file': rel,
                                    'line': i,
                                    'content': line.strip()[:120],
                                    'class': classification,
                                })
            except Exception:
                pass
    
    # Print summary
    print("=" * 60)
    print("PATTERN SUMMARY BY CLASSIFICATION")
    print("=" * 60)
    for key in sorted(summary.keys()):
        pattern, cls = key.split('|')
        print(f"  {pattern:20s} | {cls:15s} | {summary[key]:5d} hits")
    
    print()
    print("=" * 60)
    print("PRODUCTION-PATH HITS (need remediation)")
    print("=" * 60)
    prod_total = 0
    for pname in sorted(results.keys()):
        hits = results[pname]
        prod_total += len(hits)
        print(f"\n--- {pname} ({len(hits)} production hits) ---")
        for h in hits[:30]:  # Show first 30 per pattern
            print(f"  {h['file']}:{h['line']}")
            print(f"    {h['content']}")
        if len(hits) > 30:
            print(f"  ... and {len(hits) - 30} more")
    
    print(f"\nTOTAL PRODUCTION HITS: {prod_total}")
    return results


if __name__ == '__main__':
    scan()
