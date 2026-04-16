from __future__ import annotations

import ast
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "report" / "repo_audit"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
}

TEXT_EXTENSIONS = {
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".jsonl",
    ".md",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".env",
    ".ps1",
    ".sh",
    ".bat",
    ".cmd",
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hpp",
    ".rs",
    ".sql",
    ".html",
    ".css",
    ".scss",
    ".lock",
}

TODO_MARKERS = ("TODO", "FIXME", "HACK", "PLACEHOLDER")

MOCK_PATTERNS = {
    "CRITICAL": [
        r"\bMOCK_DATA\b",
        r"\bFAKE_DATA\b",
        r"\bDEMO_DATA\b",
        r"\bPLACEHOLDER_DATA\b",
        r"generate_fake",
        r"generate_mock",
        r"synthetic_",
        r"simulated_",
        r"dummy_data",
        r"placeholder_",
        r"fake_",
    ],
    "WARNING": [
        r"MagicMock",
        r"mock\.patch",
        r"\bMock\(",
        r"demo_mode",
        r"sample_data",
        r"example_data",
        r"test_data",
    ],
    "ACCEPTABLE": [
        r"tmp_path",
        r"TemporaryDirectory",
        r"pytest\.skip",
    ],
}

STRUCTURE_RULES = {
    "governance": ["backend/governance", "governance", "impl_v1/governance"],
    "ml_training_core": ["backend/training", "training", "training_core"],
    "autograbber_ingestion": ["backend/ingestion", "scripts/fast_bridge_ingest.py", "scripts/ingestion_bootstrap.py"],
    "synchronization": ["backend/sync", "impl_v1/enterprise/checkpoint_sync.py"],
    "checkpoint_system": ["checkpoints", "impl_v1/training/checkpoints", "scripts/migrate_pt_to_safetensors.py"],
    "voice_pipeline": ["backend/voice", "voice_mode", "native/voice_capture", "impl_v1/training/voice"],
    "moe_expert_system": ["impl_v1/phase49/moe", "training_controller.py", "tests/test_moe_training.py"],
    "api_backend": ["backend/api", "api"],
    "frontend": ["frontend"],
    "native_layer": ["native", "impl_v1/phase49/native"],
    "reporting": ["report", "ai_report_generator", "native/report_engine"],
    "testing_validation": ["tests", "backend/tests", "impl_v1/phase49/tests"],
    "agent_workflows": ["backend/agent", "backend/tasks", "backend/assistant"],
    "edge_distributed_execution": ["edge", "impl_v1/training/distributed", "run_leader_ddp.py", "run_rtx3050_follower.py"],
    "auth_security": ["backend/auth", "native/security", "backend/cve", "backend/security"],
    "data_storage": ["data", "backend/storage", "secure_data"],
    "cve_intelligence": ["backend/cve", "backend/ingestion/scrapers"],
    "observability": ["logs", "backend/reliability", "backend/observability"],
}


def relpath(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def is_text_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return True
    name = path.name.lower()
    return name in {"dockerfile", "makefile"}


def read_text(path: Path) -> str | None:
    if not is_text_file(path):
        return None
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None


def count_lines(text: str | None) -> int | None:
    if text is None:
        return None
    if text == "":
        return 0
    return text.count("\n") + 1


def count_python_symbols(text: str | None) -> tuple[int, int, int]:
    if text is None:
        return 0, 0, 0
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return 0, 0, 0
    classes = 0
    functions = 0
    async_functions = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes += 1
        elif isinstance(node, ast.FunctionDef):
            functions += 1
        elif isinstance(node, ast.AsyncFunctionDef):
            functions += 1
            async_functions += 1
    return classes, functions, async_functions


def collect_inventory() -> dict[str, Any]:
    counts = Counter()
    top_level_python = Counter()
    top_level_all = Counter()
    markers = Counter()
    files: list[dict[str, Any]] = []
    texts: dict[str, str] = {}

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue

        rel = relpath(path)
        counts["total_files"] += 1
        top_level = rel.split("/", 1)[0] if "/" in rel else "."
        top_level_all[top_level] += 1

        is_python = path.suffix.lower() == ".py"
        is_test = (
            rel.startswith("tests/")
            or "/tests/" in f"/{rel}"
            or path.name.startswith("test_")
            or path.name.endswith("_test.py")
        )

        if is_python:
            counts["python_files"] += 1
            top_level_python[top_level] += 1
        if is_test:
            counts["test_files"] += 1

        text = read_text(path)
        file_lines = count_lines(text)
        file_markers = {marker: 0 for marker in TODO_MARKERS}
        classes = 0
        functions = 0
        async_functions = 0

        if text is not None:
            texts[rel] = text
            counts["text_files"] += 1
            counts["text_lines"] += file_lines or 0
            for marker in TODO_MARKERS:
                file_markers[marker] = text.count(marker)
                markers[marker] += file_markers[marker]

        if is_python:
            classes, functions, async_functions = count_python_symbols(text)
            counts["classes"] += classes
            counts["functions"] += functions
            counts["async_functions"] += async_functions

        files.append(
            {
                "path": rel,
                "suffix": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
                "line_count": file_lines,
                "is_python": is_python,
                "is_test": is_test,
                "classes": classes,
                "functions": functions,
                "async_functions": async_functions,
                "markers": file_markers,
            }
        )

    return {
        "summary": {
            "counts": dict(counts),
            "markers": dict(markers),
            "top_level_all": dict(sorted(top_level_all.items())),
            "top_level_python": dict(sorted(top_level_python.items())),
        },
        "files": files,
        "texts": texts,
    }


def collect_mock_findings(texts: dict[str, str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for rel, text in texts.items():
        for severity, patterns in MOCK_PATTERNS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                    findings.append(
                        {
                            "severity": severity,
                            "path": rel,
                            "line": text.count("\n", 0, match.start()) + 1,
                            "pattern": pattern,
                            "match": match.group(0),
                        }
                    )
    return findings


def collect_structures(files: list[dict[str, Any]]) -> dict[str, Any]:
    structures: dict[str, Any] = {}
    for name, prefixes in STRUCTURE_RULES.items():
        matched = [
            file
            for file in files
            if any(file["path"] == prefix or file["path"].startswith(prefix.rstrip("/") + "/") for prefix in prefixes)
        ]
        structures[name] = {
            "file_count": len(matched),
            "python_files": sum(1 for file in matched if file["is_python"]),
            "test_files": sum(1 for file in matched if file["is_test"]),
            "loc": sum(file["line_count"] or 0 for file in matched),
            "sample_files": [file["path"] for file in matched[:20]],
        }
    return structures


def collect_git_history(limit: int = 100) -> list[str]:
    command = [
        "git",
        "log",
        "--stat",
        "--decorate",
        "--date=iso",
        "--pretty=format:%H | %ad | %an | %s",
        f"-n{limit}",
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    return completed.stdout.splitlines()


def main() -> None:
    inventory = collect_inventory()
    payload = {
        "summary": inventory["summary"],
        "structures": collect_structures(inventory["files"]),
        "mock_findings": collect_mock_findings(inventory["texts"]),
        "git_history": collect_git_history(),
        "files": inventory["files"],
    }
    output_path = REPORT_DIR / "repo_audit_inventory.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    print(f"REPORT_PATH={output_path.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
