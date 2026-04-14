from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import ast
import json


ROOT = Path('.')
TARGETS = [
    ROOT / 'backend',
    ROOT / 'impl_v1',
    ROOT / 'scripts',
    ROOT / 'training_controller.py',
]
OUT_DIR = ROOT / '.tmp_hdd_drive'
OUT_DIR.mkdir(exist_ok=True)
RAW_JSON = OUT_DIR / 'phase0b_silent_handler_inventory.json'
SUMMARY_MD = OUT_DIR / 'phase0b_silent_handler_inventory.md'
SUMMARY_JSON = OUT_DIR / 'phase0b_silent_handler_summary.json'


def is_test_path(path_str: str) -> bool:
    lower = path_str.replace('\\', '/').lower()
    parts = lower.split('/')
    name = parts[-1]
    return '/tests/' in lower or name.startswith('test_') or name.endswith('_test.py') or name == 'conftest.py'


def infer_category(path_str: str, header: str, context: str) -> str:
    lower = f"{path_str}\n{header}\n{context}".lower()
    cleanup_keywords = [
        'cleanup', 'clean up', 'teardown', 'shutdown', 'close(', 'close ', 'closing',
        'terminate', 'stop(', 'stop ', 'cancel', 'kill(', 'kill ', 'join(', 'join ',
        'drain', 'release', 'dispose', 'best effort', 'best-effort', 'background',
        'loop', 'heartbeat',
    ]
    optional_keywords = [
        'optional', 'fallback', 'degraded', 'import ', 'importerror', 'module not found',
        'unavailable', 'not available', 'skip dependency', 'cuda', 'gpu', 'torch',
        'telegram', 'sounddevice', 'browser', 'voice', 'ffmpeg', 'psutil', 'playwright',
        'websocket',
    ]
    safe_default_keywords = [
        'default', 'return none', 'return {}', 'return []', 'return false', 'return 0',
        'cached', 'cache', 'existing', 'empty', 'missing', 'absent', 'noop', 'no-op',
        'ignore missing', 'probe', 'status', 'health', 'lookup', 'load', 'read', 'parse',
    ]

    if is_test_path(path_str):
        return 'tests-only / intentionally suppressing in tests'
    if any(keyword in lower for keyword in cleanup_keywords):
        return 'background loop / best-effort cleanup'
    if any(keyword in lower for keyword in optional_keywords):
        return 'optional feature fallback'
    if any(keyword in lower for keyword in safe_default_keywords):
        return 'safe-default return path'
    return 'likely bug / error masking'


def priority_rank(path_str: str, categories: list[str]) -> tuple[int, int, str]:
    lower = path_str.replace('\\', '/').lower()
    has_bug = any(category == 'likely bug / error masking' for category in categories)
    bug_rank = 0 if has_bug else 1
    if lower.startswith('backend/'):
        return (0, bug_rank, lower)
    if lower == 'training_controller.py':
        return (1, bug_rank, lower)
    if 'impl_v1/phase49/runtime/' in lower or 'impl_v1/phase49/governors/' in lower or 'impl_v1/production/' in lower:
        return (2, bug_rank, lower)
    if 'impl_v1/training/safety/' in lower or 'impl_v1/unified/' in lower or 'impl_v1/training/voice/' in lower:
        return (3, bug_rank, lower)
    if lower.startswith('scripts/'):
        return (4, bug_rank, lower)
    if is_test_path(lower):
        return (9, bug_rank, lower)
    return (5, bug_rank, lower)


def scan_file(path: Path) -> list[dict[str, object]]:
    try:
        text = path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        text = path.read_text(encoding='utf-8', errors='ignore')

    rel_path = path.relative_to(ROOT).as_posix()
    lines = text.splitlines()
    line_map = {index + 1: line for index, line in enumerate(lines)}
    tree = ast.parse(text)
    records: list[dict[str, object]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            line_no = getattr(handler, 'lineno', None)
            if line_no is None:
                continue

            body = getattr(handler, 'body', [])
            body_is_pass = len(body) == 1 and isinstance(body[0], ast.Pass)

            if handler.type is None:
                match_kind = 'bare except:'
            elif body_is_pass:
                match_kind = 'except ...: pass'
            else:
                continue

            exception_type = 'bare'
            if handler.type is not None:
                try:
                    exception_type = ast.unparse(handler.type)
                except Exception:
                    exception_type = type(handler.type).__name__

            end_line = getattr(handler, 'end_lineno', line_no)
            context_start = max(1, line_no - 2)
            context_end = min(len(lines), end_line + 2)
            context = '\n'.join(
                f"{number}: {line_map.get(number, '')}"
                for number in range(context_start, context_end + 1)
            )
            header = line_map.get(line_no, '').strip()
            category = infer_category(rel_path, header, context)
            scope = 'tests' if is_test_path(rel_path) else 'production'

            records.append(
                {
                    'path': rel_path,
                    'line': line_no,
                    'end_line': end_line,
                    'match_kind': match_kind,
                    'exception_type': exception_type,
                    'header': header,
                    'scope': scope,
                    'category': category,
                    'context': context,
                }
            )

    return records


def main() -> None:
    files: list[Path] = []
    for target in TARGETS:
        if target.is_dir():
            files.extend(sorted(path for path in target.rglob('*.py') if path.is_file()))
        elif target.is_file():
            files.append(target)

    records: list[dict[str, object]] = []
    for path in files:
        try:
            records.extend(scan_file(path))
        except SyntaxError:
            continue

    records.sort(key=lambda item: (str(item['path']), int(item['line']), str(item['match_kind'])))

    file_counts = Counter(str(record['path']) for record in records)
    scope_counts = Counter(str(record['scope']) for record in records)
    category_counts = Counter(str(record['category']) for record in records)
    file_categories: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        file_categories[str(record['path'])][str(record['category'])] += 1

    production_files = []
    for path, count in file_counts.items():
        if is_test_path(path):
            continue
        categories = list(file_categories[path].keys())
        production_files.append(
            {
                'path': path,
                'count': count,
                'categories': dict(file_categories[path]),
                'rank': priority_rank(path, categories),
            }
        )
    production_files.sort(key=lambda item: (item['rank'], -int(item['count']), str(item['path'])))

    recommended_batches: list[dict[str, object]] = []
    if production_files:
        batch1 = [str(item['path']) for item in production_files[:5]]
        recommended_batches.append(
            {
                'name': 'Batch 1 - top production files with highest operational value',
                'files': batch1,
            }
        )
        remaining_prod = [str(item['path']) for item in production_files[5:15]]
        if remaining_prod:
            recommended_batches.append(
                {
                    'name': 'Batch 2 - remaining production runtime and support paths',
                    'files': remaining_prod,
                }
            )

    test_files = sorted(path for path in file_counts if is_test_path(path))
    if test_files:
        recommended_batches.append(
            {
                'name': 'Batch 3 - tests-only suppressions after production cleanup',
                'files': test_files,
            }
        )

    summary = {
        'total_hits': len(records),
        'scopes': dict(scope_counts),
        'categories': dict(category_counts),
        'file_counts': dict(sorted(file_counts.items())),
        'training_controller_hits': file_counts.get('training_controller.py', 0),
        'top_production_files': [
            {
                'path': item['path'],
                'count': item['count'],
                'categories': item['categories'],
            }
            for item in production_files[:10]
        ],
        'recommended_batches': recommended_batches,
    }

    RAW_JSON.write_text(json.dumps({'total_hits': len(records), 'records': records}, indent=2), encoding='utf-8')
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding='utf-8')

    lines = []
    lines.append('# Phase 0B Silent Handler Inventory')
    lines.append('')
    lines.append(f'- Total remaining hits: {len(records)}')
    lines.append(f"- Production hits: {scope_counts.get('production', 0)}")
    lines.append(f"- Tests-only hits: {scope_counts.get('tests', 0)}")
    lines.append(f"- training_controller.py remaining hits: {file_counts.get('training_controller.py', 0)}")
    lines.append(f'- Raw inventory JSON: {RAW_JSON.as_posix()}')
    lines.append(f'- Summary JSON: {SUMMARY_JSON.as_posix()}')
    lines.append('')
    lines.append('## File-by-file counts')
    for path, count in sorted(file_counts.items()):
        scope = 'tests' if is_test_path(path) else 'production'
        cats = ', '.join(f'{name}={value}' for name, value in sorted(file_categories[path].items()))
        lines.append(f'- {path} — {count} hit(s) [{scope}] :: {cats}')
    if not file_counts:
        lines.append('- No matching silent handlers found in scope.')
    lines.append('')
    lines.append('## Category counts')
    for name, count in sorted(category_counts.items()):
        lines.append(f'- {name}: {count}')
    lines.append('')
    lines.append('## Top production files for Phase 0C')
    for index, item in enumerate(production_files[:10], start=1):
        cats = ', '.join(f'{name}={value}' for name, value in sorted(dict(item['categories']).items()))
        lines.append(f"- {index}. {item['path']} — {item['count']} hit(s) :: {cats}")
    if not production_files:
        lines.append('- No production hits remain.')
    lines.append('')
    lines.append('## Recommended batching plan for Phase 0C')
    for batch in recommended_batches:
        lines.append(f"- {batch['name']}:")
        for path in batch['files']:
            lines.append(f'  - {path}')
    if not recommended_batches:
        lines.append('- No remediation batches required.')
    lines.append('')
    lines.append('## Complete inventory')
    current_path = None
    for record in records:
        record_path = str(record['path'])
        if record_path != current_path:
            current_path = record_path
            lines.append(f'### {current_path}')
        lines.append(
            f"- L{record['line']}: {record['match_kind']} [{record['exception_type']}] | {record['scope']} | {record['category']} | {record['header']}"
        )

    SUMMARY_MD.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(
        json.dumps(
            {
                'total_hits': len(records),
                'raw_json': RAW_JSON.as_posix(),
                'summary_json': SUMMARY_JSON.as_posix(),
                'summary_md': SUMMARY_MD.as_posix(),
            },
            indent=2,
        )
    )


if __name__ == '__main__':
    main()
