from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import contextlib
import io
import os
import re
import statistics
import subprocess
import sys
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "report" / "industrial_audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STEP_FILES = {
    "step0": OUT_DIR / "step0_baseline.txt",
    "step1": OUT_DIR / "step1_mock_hunt.txt",
    "step2": OUT_DIR / "step2_bugs.txt",
    "step3": OUT_DIR / "step3_gpu.txt",
    "step4": OUT_DIR / "step4_scrapers.txt",
    "step5": OUT_DIR / "step5_parallelism.txt",
    "step6": OUT_DIR / "step6_planned_vs_implemented.txt",
    "step7": OUT_DIR / "step7_maturity.txt",
    "step9": OUT_DIR / "step9_final_gate.txt",
}

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "dist",
    ".next",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    ".tmp_hdd_drive",
}


def _print_header(title: str) -> None:
    print("=" * 70)
    print(title)
    print("=" * 70)


def _is_skipped(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def iter_files(paths: list[str], suffixes: set[str] | None = None):
    for raw in paths:
        path = ROOT / raw
        if not path.exists():
            continue
        if path.is_file():
            if suffixes is None or path.suffix.lower() in suffixes:
                yield path
            continue
        for file_path in path.rglob("*"):
            if _is_skipped(file_path):
                continue
            if file_path.is_file() and (suffixes is None or file_path.suffix.lower() in suffixes):
                yield file_path


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def is_test_or_audit_path(path_str: str) -> bool:
    normalized = path_str.replace("\\", "/").lower()
    path = Path(normalized)
    name = path.name
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    if "tests" in path.parts:
        return True
    return any(
        token in normalized
        for token in (
            "audit_",
            "_audit",
            "gate_test.py",
            "scripts/industrial_audit.py",
            "scripts/repo_audit_inventory.py",
            "mock_data_scanner.py",
        )
    )


def grep_literal(paths: list[str], suffixes: set[str], pattern: str, *, skip_tests: bool = False) -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    for file_path in iter_files(paths, suffixes):
        if skip_tests and file_path.name.startswith("test_"):
            continue
        text = read_text(file_path)
        if pattern not in text:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern in line:
                hits.append((rel(file_path), lineno, line.strip()))
    return hits


def grep_regex(
    paths: list[str],
    suffixes: set[str],
    pattern: str,
    *,
    flags: int = 0,
) -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    compiled = re.compile(pattern, flags)
    for file_path in iter_files(paths, suffixes):
        text = read_text(file_path)
        if not compiled.search(text):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if compiled.search(line):
                hits.append((rel(file_path), lineno, line.strip()))
    return hits


def run_async(coro):
    return asyncio.run(coro)


def _status_env() -> dict[str, str]:
    return {
        "YGB_APPROVAL_SECRET": os.getenv(
            "YGB_APPROVAL_SECRET",
            "audit-approval-secret-32chars-minimum!!",
        ),
        "JWT_SECRET": os.getenv(
            "JWT_SECRET",
            "audit-jwt-secret-32chars-minimum-value!!",
        ),
        "YGB_VIDEO_JWT_SECRET": os.getenv(
            "YGB_VIDEO_JWT_SECRET",
            "audit-video-jwt-secret-32chars-min!!",
        ),
    }


def cached_status_call(aggregated_system_status):
    previous = {key: os.environ.get(key) for key in _status_env()}
    os.environ.update(_status_env())
    try:
        return run_async(aggregated_system_status(user={"audit": True}))
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _audit_queue_status_path() -> Path:
    return OUT_DIR / "audit_experts_status.json"


def _queue_experts_snapshot(queue) -> list[dict[str, object]]:
    status = queue.get_status()
    if isinstance(status, dict):
        experts = status.get("experts")
        if isinstance(experts, list):
            return [dict(item) for item in experts if isinstance(item, dict)]
        return []
    if isinstance(status, list):
        return [dict(item) for item in status if isinstance(item, dict)]
    return []


def run_py(command: list[str], *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def write_step(step_name: str, fn: Callable[[], None]) -> Path:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn()
    output = buf.getvalue()
    out_path = STEP_FILES[step_name]
    out_path.write_text(output, encoding="utf-8")
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    if hasattr(sys.stdout, "buffer"):
        sys.stdout.buffer.write(output.encode(encoding, errors="backslashreplace"))
        sys.stdout.buffer.flush()
    else:
        print(output.encode(encoding, errors="backslashreplace").decode(encoding), end="")
    print(f"\nREPORT_PATH={rel(out_path)}")
    return out_path


def step0_baseline() -> None:
    _print_header("STEP 0: BASELINE INVENTORY")

    ext_counts = Counter()
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for file_name in files:
            ext_counts[Path(file_name).suffix.lower()] += 1

    total = sum(ext_counts.values())
    print(f"Total files: {total:,}")
    for ext, count in ext_counts.most_common(10):
        print(f"  {ext or '(no ext)'}: {count:,}")

    result = run_py([sys.executable, "-m", "pytest", "-q", "--tb=no", "--no-header"], timeout=3600)
    lines = [line for line in result.stdout.splitlines() if any(token in line for token in ("passed", "failed", "error"))]
    print()
    print(f"Test baseline: {lines[0] if lines else 'COULD NOT RUN'}")

    try:
        import torch

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            print(f"GPU: {props.name} ({props.total_memory / 1e9:.1f}GB VRAM)")
            print(f"CUDA: {torch.version.cuda}")
            print(f"GPU count: {torch.cuda.device_count()}")
        else:
            print("GPU: NOT AVAILABLE — all parallel work will use CPU threads")
    except ImportError:
        print("GPU: torch not installed")
    except Exception as exc:
        print(f"GPU: ERROR — {exc}")

    try:
        from backend.governance.authority_lock import AuthorityLock

        locked = AuthorityLock.verify_all_locked()
        print(f"Authority lock: {locked.get('all_locked')}")
    except Exception as exc:
        print(f"Authority lock: ERROR — {exc}")

    os.environ["YGB_USE_MOE"] = "true"
    try:
        from training_controller import _build_configured_model

        model = _build_configured_model()
        params = sum(p.numel() for p in model.parameters())
        print(f"Active model: {type(model).__name__} ({params:,} params / {params / 1e6:.1f}M)")
        if params < 500_000:
            print("  *** CRITICAL: Legacy 296K model still active — MoE NOT wired ***")
        elif params > 100_000_000:
            print("  *** MoE ACTIVE and wired correctly ***")
    except Exception as exc:
        print(f"Model check: ERROR — {exc}")


def step1_mock_hunt() -> None:
    _print_header("STEP 1: MOCK DATA HUNT")

    critical_patterns = [
        ("np.random.rand", r"\bnp\.random\.rand\s*\("),
        ("np.random.randn", r"\bnp\.random\.randn\s*\("),
        ("np.random.randint", r"\bnp\.random\.randint\s*\("),
        ("torch.randn(", r"\btorch\.randn\s*\("),
        ("torch.rand(", r"\btorch\.rand\s*\("),
        ("random.random()", r"\brandom\.random\s*\(\s*\)"),
        ("random.uniform(", r"\brandom\.uniform\s*\("),
        ("return 0.95", r"\breturn\s+0\.95\b"),
        ("return 0.87", r"\breturn\s+0\.87\b"),
        ("return 0.9", r"\breturn\s+0\.9\b(?!\d)"),
        ("accuracy = 1.0", r"\baccuracy\s*=\s*1\.0\b"),
        ("f1 = 0.9", r"\bf1\s*=\s*0\.9\b(?!\d)"),
        ("val_f1 = 0.8", r"\bval_f1\s*=\s*0\.8\b(?!\d)"),
        ("fake_", r"\bfake_"),
        ("dummy_data", r"\bdummy_data\b"),
        ("mock_data", r"\bmock_data\b"),
        ("synthetic_data", r"\bsynthetic_data\b"),
        ("simulated_result", r"\bsimulated_result\b"),
        ("placeholder_", r"\bplaceholder_"),
        ("FAKE", r"\bFAKE\b"),
        ("DUMMY", r"\bDUMMY\b"),
        ("SIMULATED", r"\bSIMULATED\b"),
        ("heuristic size ratio", r"heuristic size ratio"),
        ("sequential for-loop", r"sequential for-loop"),
    ]
    warning_patterns = [
        "TODO",
        "FIXME",
        "HACK",
        "NOT IMPLEMENTED",
        "raise NotImplementedError",
        "# mock",
        "# fake",
        "# simulated",
        "_demo_handler",
        "demo_mode",
        "except: pass",
        "except Exception: pass",
        "return []  # TODO",
        "return {}  # placeholder",
    ]
    critical_cpp = [
        ("gmtime()", r"\bgmtime\s*\("),
        ("manual json string concat", r"manual json string concat"),
        ("sprintf(", r"(?<![A-Za-z_])sprintf\s*\("),
        ("strcpy(", r"(?<![A-Za-z_])strcpy\s*\("),
        ("gets(", r"(?<![A-Za-z_])gets\s*\("),
    ]

    print()
    print("--- CRITICAL: Fake/Mock Data in Production ---")
    critical_total = 0
    for label, regex in critical_patterns:
        hits = [hit for hit in grep_regex(["."], {".py"}, regex) if not is_test_or_audit_path(hit[0])]
        if hits:
            critical_total += len({path for path, _, _ in hits})
            print(f'  [{len({path for path, _, _ in hits}):3d} files] "{label}"')
            for file_path, lineno, line in hits[:3]:
                print(f"    {file_path}:{lineno}: {line[:120]}")

    print()
    print("--- WARNING: Incomplete/Bypass Patterns ---")
    warning_total = 0
    for pattern in warning_patterns:
        hits = [
            hit
            for hit in grep_literal(["backend", "api", "training_controller.py"], {".py"}, pattern)
            if not is_test_or_audit_path(hit[0])
        ]
        if hits:
            warning_total += len(hits)
            print(f'  [{len(hits):3d} hits] "{pattern}"')
            for file_path, lineno, line in hits[:2]:
                print(f"    {file_path}:{lineno}: {line[:120]}")

    print()
    print("--- C++ Critical Issues ---")
    for label, regex in critical_cpp:
        hits = grep_regex(["native", "edge"], {".cpp", ".h"}, regex)
        if hits:
            print(f'  [{len(hits):3d} hits] "{label}"')
            for file_path, lineno, line in hits[:2]:
                print(f"    {file_path}:{lineno}: {line[:120]}")

    print()
    print("SUMMARY:")
    print(f"  Critical mock/fake patterns: {critical_total} production files affected")
    print(f"  Warning patterns: {warning_total} hits")
    print("  ACTION: Every critical pattern must be removed before production")


def step2_bug_verification() -> None:
    _print_header("STEP 2: CRITICAL BUG VERIFICATION")
    bugs: dict[str, str] = {}

    print()
    print("BUG-1: Single global aiosqlite connection (FLAW-008)")
    db_file = ROOT / "api" / "database.py"
    if db_file.exists():
        content = read_text(db_file)
        if "global" in content and "aiosqlite" in content:
            bugs["FLAW-008"] = "CONFIRMED"
            print("  STATUS: CONFIRMED — single global connection found")
            for file_path, lineno, line in grep_literal(["api/database.py"], {".py"}, "global")[:5]:
                print(f"    {file_path}:{lineno}: {line[:120]}")
            for file_path, lineno, line in grep_literal(["api/database.py"], {".py"}, "aiosqlite.connect")[:5]:
                print(f"    {file_path}:{lineno}: {line[:120]}")
        elif "pool" in content or "Pool" in content:
            bugs["FLAW-008"] = "FIXED"
            print("  STATUS: FIXED — connection pool found")
        else:
            bugs["FLAW-008"] = "UNKNOWN"
            print("  STATUS: UNKNOWN — cannot determine")
    else:
        bugs["FLAW-008"] = "FILE MISSING"
        print("  STATUS: FILE MISSING")

    print()
    print("BUG-2: Fake NCCL allreduce (FLAW-N001)")
    allreduce_file = ROOT / "native" / "distributed" / "async_allreduce.cpp"
    if allreduce_file.exists():
        content = read_text(allreduce_file)
        if (
            ("ncclAllReduce" in content or "MPI_Allreduce" in content)
            and "b.data[i] *= scale" not in content
            and "float scale = 1.0f" not in content
        ):
            bugs["FLAW-N001"] = "FIXED"
            print("  STATUS: FIXED — real NCCL/MPI call found")
        elif "b.data[i] *= scale" in content or "float scale = 1.0f" in content:
            bugs["FLAW-N001"] = "CONFIRMED"
            print("  STATUS: CONFIRMED — only local scaling, NO real allreduce")
            for file_path, lineno, line in grep_literal(["native/distributed/async_allreduce.cpp"], {".cpp"}, "scale")[:5]:
                print(f"    {file_path}:{lineno}: {line[:120]}")
        else:
            bugs["FLAW-N001"] = "UNKNOWN"
            print("  STATUS: UNKNOWN")
    else:
        bugs["FLAW-N001"] = "FILE MISSING"
        print("  STATUS: FILE MISSING — native layer may not be built")

    print()
    print("BUG-3: No C++ build system (FLAW-N004)")
    cmake_files = [path for path in ROOT.rglob("CMakeLists.txt") if not _is_skipped(path)]
    makefiles = [path for path in ROOT.rglob("Makefile") if not _is_skipped(path)]
    if cmake_files or makefiles:
        bugs["FLAW-N004"] = "FIXED"
        print(f"  STATUS: FIXED — {len(cmake_files)} CMakeLists.txt, {len(makefiles)} Makefiles found")
    else:
        bugs["FLAW-N004"] = "CONFIRMED"
        print("  STATUS: CONFIRMED — no build system for C++ native layer")
        dll_files = list((ROOT / "native").rglob("*.dll")) if (ROOT / "native").exists() else []
        so_files = list((ROOT / "native").rglob("*.so")) if (ROOT / "native").exists() else []
        print(f"    Pre-built artifacts: {len(dll_files)} .dll, {len(so_files)} .so — UNAUDITABLE")

    print()
    print("BUG-4: JSON injection in edge C++ (FLAW-015)")
    edge_file = ROOT / "edge" / "data_extractor.cpp"
    if edge_file.exists():
        content = read_text(edge_file)
        if (
            "nlohmann" in content
            or "rapidjson" in content
            or "json::" in content
            or (
                "escape_json(" in content
                and "escape_json(record.id)" in content
                and "escape_json(key)" in content
                and "escape_json(value)" in content
            )
        ):
            bugs["FLAW-015"] = "FIXED"
            print("  STATUS: FIXED — JSON output is escaped before serialization")
        elif "+" in content and '"' in content and "json" in content.lower():
            bugs["FLAW-015"] = "CONFIRMED"
            print("  STATUS: CONFIRMED — manual string concatenation for JSON")
            for file_path, lineno, line in grep_literal(["edge/data_extractor.cpp"], {".cpp"}, "json")[:3]:
                print(f"    {file_path}:{lineno}: {line[:120]}")
        else:
            bugs["FLAW-015"] = "UNKNOWN"
            print("  STATUS: UNKNOWN")
    else:
        bugs["FLAW-015"] = "FILE MISSING"
        print("  STATUS: FILE MISSING")

    print()
    print("BUG-5: Governance soft-skip on ImportError (FLAW-I002)")
    gov_files = list(ROOT.rglob("governance_pipeline.py"))
    if gov_files:
        content = read_text(gov_files[0])
        if "except ImportError" in content and "pass" in content:
            lines = content.splitlines()
            soft_skips = 0
            for idx, line in enumerate(lines):
                if "except ImportError" in line:
                    window = lines[idx + 1 : idx + 4]
                    if any(token in candidate.lower() for candidate in window for token in ("pass", "continue", "skip")):
                        soft_skips += 1
            if soft_skips > 0:
                bugs["FLAW-I002"] = "CONFIRMED"
                print(f"  STATUS: CONFIRMED — {soft_skips} soft-skip(s) found")
            else:
                bugs["FLAW-I002"] = "FIXED"
                print("  STATUS: FIXED — ImportError causes hard fail")
        else:
            bugs["FLAW-I002"] = "UNKNOWN"
            print("  STATUS: UNKNOWN")
    else:
        bugs["FLAW-I002"] = "FILE NOT FOUND"
        print("  STATUS: FILE NOT FOUND")

    print()
    print("BUG-6: Replay prevention lost on restart (FLAW-H002)")
    approval_ledger = ROOT / "backend" / "governance" / "approval_ledger.py"
    if approval_ledger.exists():
        content = read_text(approval_ledger)
        has_persist = "def _persist(" in content and "def load(" in content
        rebuilds_nonces = "self._used_nonces.add(nonce)" in content and "self._used_signatures.add(sig)" in content
        if has_persist and rebuilds_nonces:
            bugs["FLAW-H002"] = "FIXED"
            print(f"  STATUS: FIXED — nonce/signature replay state rebuilt from ledger in {rel(approval_ledger)}")
        else:
            bugs["FLAW-H002"] = "CONFIRMED"
            print(f"  STATUS: CONFIRMED — replay state does not rebuild from persistent ledger in {rel(approval_ledger)}")
    else:
        bugs["FLAW-H002"] = "UNKNOWN"
        print("  STATUS: UNKNOWN")

    print()
    print("BUG-7: Device-specific hardcoded defaults (FLAW-T003)")
    hits = grep_regex(
        ["."],
        {".py"},
        r'leader_node\s*:\s*str\s*=\s*"RTX2050"|'
        r'follower_node\s*:\s*str\s*=\s*"RTX3050"|'
        r'getattr\(config,\s*"leader_node",\s*"RTX2050"|'
        r'getattr\(config,\s*"follower_node",\s*"RTX3050"',
    )
    if hits:
        bugs["FLAW-T003"] = "CONFIRMED"
        print(f"  STATUS: CONFIRMED — {len(hits)} occurrences")
        for file_path, lineno, line in hits[:3]:
            print(f"    {file_path}:{lineno}: {line[:120]}")
    else:
        bugs["FLAW-T003"] = "FIXED"
        print("  STATUS: FIXED or not present")

    print()
    print("BUG-8: Compression engine returns fake stats (FLAW-N003)")
    for file_path in ROOT.rglob("compression_engine*"):
        if _is_skipped(file_path) or file_path.suffix.lower() not in {".cpp", ".py"}:
            continue
        content = read_text(file_path)
        if "heuristic" in content.lower() or "estimate" in content.lower():
            bugs["FLAW-N003"] = "CONFIRMED"
            print(f"  STATUS: CONFIRMED in {rel(file_path)}")
            for token in ("heuristic", "estimate", "ratio"):
                for hit in grep_literal([rel(file_path)], {file_path.suffix.lower()}, token)[:3]:
                    print(f"    {hit[0]}:{hit[1]}: {hit[2][:120]}")
            break
        if "actual" in content.lower() and "byte" in content.lower():
            bugs["FLAW-N003"] = "LIKELY FIXED"
            print(f"  STATUS: LIKELY FIXED in {rel(file_path)}")
            break

    print()
    _print_header("BUG SUMMARY")
    confirmed = [key for key, value in bugs.items() if "CONFIRMED" in value]
    fixed = [key for key, value in bugs.items() if "FIXED" in value]
    unknown = [key for key, value in bugs.items() if any(token in value for token in ("UNKNOWN", "MISSING", "NOT FOUND"))]
    print(f"CONFIRMED bugs: {len(confirmed)} — {confirmed}")
    print(f"FIXED bugs:     {len(fixed)} — {fixed}")
    print(f"UNKNOWN/MISSING:{len(unknown)} — {unknown}")


def step3_gpu_audit() -> None:
    _print_header("STEP 3: GPU UTILIZATION AUDIT")

    gpu_required = [
        ("training_controller.py", [".cuda()", ".to(device)", "torch.cuda", 'device = "cuda"']),
        ("backend/training/incremental_trainer.py", ["cuda", "device", "GradScaler", "autocast"]),
        ("backend/training/auto_train_controller.py", ["cuda", "device"]),
        ("impl_v1/phase49/moe/__init__.py", ["cuda", ".to(device)", ".cuda()"]),
    ]
    cpu_fallback_patterns = ['device = "cpu"', 'device="cpu"', '# use cpu', 'force_cpu', '.cpu()']
    parallel_patterns = {
        "ThreadPoolExecutor": "backend",
        "ProcessPoolExecutor": "backend",
        "asyncio.gather": "backend",
        "torch.multiprocessing": ".",
        "DistributedDataParallel": ".",
        "DDP": ".",
        "NCCL": ".",
        "ncclAllReduce": "native",
    }

    print()
    print("--- GPU Usage in Training Files ---")
    for file_name, patterns in gpu_required:
        file_path = ROOT / file_name
        if not file_path.exists():
            print(f"  MISSING  {file_name}")
            continue
        content = read_text(file_path)
        found = [pattern for pattern in patterns if pattern in content]
        if found:
            print(f"  GPU REFS {file_name}: {found}")
        else:
            print(f"  NO GPU   {file_name} — may be CPU-only!")

    print()
    print("--- CPU Fallback Patterns (should be minimal) ---")
    for pattern in cpu_fallback_patterns:
        hits = grep_literal(["backend/training", "training_controller.py"], {".py"}, pattern)
        if hits:
            print(f'  [{len(hits):3d}] "{pattern}"')
            for file_path, lineno, line in hits[:2]:
                print(f"    {file_path}:{lineno}: {line[:120]}")

    print()
    print("--- Parallel Execution Check ---")
    for pattern, directory in parallel_patterns.items():
        suffixes = {".py", ".cpp"}
        hits = grep_literal([directory], suffixes, pattern)
        status = f"FOUND ({len(hits)} refs)" if hits else "NOT FOUND"
        print(f"  {pattern}: {status}")

    print()
    print("--- Live GPU Test ---")
    try:
        import torch

        if torch.cuda.is_available():
            device = torch.device("cuda")
            x = torch.randn(1000, 1000, device=device)
            torch.cuda.synchronize()
            start = time.perf_counter()
            for _ in range(100):
                _ = torch.matmul(x, x)
            torch.cuda.synchronize()
            elapsed = time.perf_counter() - start
            gflops = 2 * 1000**3 * 100 / elapsed / 1e9
            print(f"  GPU matmul throughput: {gflops:.0f} GFLOPS")
            print(f"  GPU device: {torch.cuda.get_device_name(0)}")
            print(f"  GPU memory allocated: {torch.cuda.memory_allocated() / 1e9:.2f}GB")
            print(f"  GPU memory total: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB")
        else:
            print("  GPU: NOT AVAILABLE — all ops will be slow on CPU")
    except Exception as exc:
        print(f"  GPU test error: {exc}")


def step4_scraper_reality() -> None:
    _print_header("STEP 4: SCRAPER REALITY TEST")
    try:
        import requests
    except Exception as exc:
        print(f"requests import error: {exc}")
        return

    user_agent = "YBG-Audit/1.0 (security research; non-commercial)"
    timeout = 15
    sources = {
        "NVD 2.0": "https://services.nvd.nist.gov/rest/json/cves/2.0?resultsPerPage=1",
        "CISA KEV": "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
        "OSV API": "https://api.osv.dev/v1/query",
        "GitHub Adv": "https://api.github.com/advisories?per_page=1&type=reviewed",
        "ExploitDB": "https://exploit-db.com/download/exploits/",
        "MSRC": "https://api.msrc.microsoft.com/cvrf/v2.0/updates",
        "Red Hat": "https://access.redhat.com/labs/securitydataapi/cve.json?per_page=1",
        "Snyk npm": "https://security.snyk.io/api/v1/vuln?type=npm&page=1&perPage=1",
        "VulnRichment": "https://api.github.com/repos/cisagov/vulnrichment/git/trees/main",
    }

    live = 0
    total_real_cves = 0
    for name, url in sources.items():
        start = time.perf_counter()
        try:
            if "osv" in url:
                response = requests.post(url, json={"page_size": 1}, timeout=timeout, headers={"User-Agent": user_agent})
            else:
                response = requests.get(url, timeout=timeout, headers={"User-Agent": user_agent})
            elapsed_ms = (time.perf_counter() - start) * 1000
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                data = response.json() if "json" in content_type else {}
                cve_count = 0
                if isinstance(data, dict):
                    if "vulnerabilities" in data and isinstance(data["vulnerabilities"], list):
                        cve_count = len(data["vulnerabilities"])
                    elif "vulns" in data and isinstance(data["vulns"], list):
                        cve_count = len(data["vulns"])
                    elif "value" in data and isinstance(data["value"], list):
                        cve_count = len(data["value"])
                total_real_cves += cve_count
                live += 1
                print(f"  LIVE  {name}: {elapsed_ms:.0f}ms ({cve_count} items in response)")
            elif response.status_code == 304:
                live += 1
                print(f"  304   {name}: no delta ({elapsed_ms:.0f}ms)")
            elif response.status_code == 400:
                print(f"  400   {name}: bad request — check URL format")
            elif response.status_code == 403:
                print(f"  403   {name}: forbidden — may need User-Agent or auth")
            elif response.status_code == 429:
                print(f"  429   {name}: rate limited — implement backoff")
            else:
                print(f"  {response.status_code}  {name}: unexpected status")
        except requests.Timeout:
            print(f"  TIME  {name}: timeout after {timeout}s")
        except requests.ConnectionError:
            print(f"  DEAD  {name}: connection refused")
        except Exception as exc:
            print(f"  ERR   {name}: {str(exc)[:120]}")
        time.sleep(2)

    print()
    print(f"SOURCES REACHABLE: {live}/{len(sources)}")
    print(f"REAL CVEs IN RESPONSES: {total_real_cves}")
    print(f"DATA PIPELINE VIABILITY: {live / len(sources) * 100:.0f}%")
    if live < 6:
        print("WARNING: Less than 6/9 sources reachable — autograbber will have limited data")


def step5_parallelism() -> None:
    _print_header("STEP 5: PARALLELISM BENCHMARK")
    os.environ.update(
        {
            "YGB_USE_MOE": "true",
            "YGB_ENV": "development",
            "JWT_SECRET": "bench-jwt-32chars-minimum-for-test!!",
            "YGB_VIDEO_JWT_SECRET": "bench-video-jwt-32chars-min-test!!",
            "YGB_LEDGER_KEY": "bench-ledger-dev-key-32chars-test!!",
            "YGB_REQUIRE_ENCRYPTION": "false",
        }
    )

    print()
    print("--- Test 1: Filter Pipeline (Sequential vs Parallel) ---")
    try:
        from backend.ingestion.industrial_autograbber import FilterPipeline, RawSample

        def make_sample(idx: int):
            return RawSample(
                source="nvd_2025",
                cve_id=f"CVE-2024-{idx:05d}",
                title="RCE vulnerability",
                severity="CRITICAL",
                cvss_score=9.8,
                description=(
                    "Critical remote code execution vulnerability in the network stack allows unauthenticated attackers "
                    "to execute arbitrary code with SYSTEM privileges via a specially crafted packet sent to the "
                    "management interface on port 443."
                ),
                published_at="2024-01-15",
                has_public_exploit=True,
                raw_hash=uuid.uuid4().hex,
                fetched_at=datetime.now(UTC).isoformat(),
            )

        count = 1000
        samples = [make_sample(i) for i in range(count)]

        start = time.perf_counter()
        [FilterPipeline.run_all(sample, set()) for sample in samples]
        seq_ms = (time.perf_counter() - start) * 1000

        dedup_sets = [set() for _ in range(count)]
        start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
            list(executor.map(lambda pair: FilterPipeline.run_all(*pair), zip(samples, dedup_sets)))
        par_ms = (time.perf_counter() - start) * 1000

        speedup = seq_ms / par_ms if par_ms else 0.0
        seq_tps = count / (seq_ms / 1000)
        par_tps = count / (par_ms / 1000)
        print(f"  Sequential {count} samples: {seq_ms:.0f}ms ({seq_tps:,.0f}/sec)")
        print(f"  Parallel   {count} samples: {par_ms:.0f}ms ({par_tps:,.0f}/sec)")
        print(f"  Speedup: {speedup:.1f}x")
        par_tok_sec = par_tps * 200
        print(f"  Token throughput (est): {par_tok_sec:,.0f} tokens/sec")
        print("  Target: 1,000,000 tokens/sec")
        if par_tok_sec >= 1_000_000:
            print("  STATUS: TARGET MET")
        else:
            print(f"  STATUS: {1_000_000 / par_tok_sec:.0f}x MORE THROUGHPUT NEEDED")
            print("  FIX: Need asyncio + aiohttp for I/O-bound source fetching")
            print("       Need GPU-accelerated feature extraction")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    print()
    print("--- Test 2: Expert Queue Atomicity (10 simultaneous claims) ---")
    try:
        from scripts.expert_task_queue import ExpertTaskQueue

        queue = ExpertTaskQueue(status_path=_audit_queue_status_path())
        queue.initialize_status_file()
        claimed: list[str] = []
        errors: list[str] = []
        lock = threading.Lock()

        def claim() -> None:
            try:
                expert = queue.claim_next_expert(f"audit-worker-{uuid.uuid4().hex[:8]}")
                with lock:
                    if expert:
                        claimed.append(str(expert.get("expert_id")))
            except Exception as exc:
                with lock:
                    errors.append(str(exc))

        threads = [threading.Thread(target=claim) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        duplicates = len(claimed) != len(set(claimed))
        print(f"  10 concurrent claims: {len(claimed)} succeeded")
        print(f"  Duplicates: {'YES — RACE CONDITION BUG' if duplicates else 'NONE — PASS'}")
        if duplicates:
            print(f"  Claimed IDs: {sorted(claimed)}")
        print(f"  Errors: {len(errors)}")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    print()
    print("--- Test 3: System Status Cache Performance ---")
    try:
        os.environ.update(_status_env())
        from backend.api.system_status import aggregated_system_status

        cached_status_call(aggregated_system_status)
        timings = []
        for _ in range(20):
            start = time.perf_counter()
            cached_status_call(aggregated_system_status)
            timings.append((time.perf_counter() - start) * 1000)

        avg = statistics.mean(timings)
        p95 = sorted(timings)[int(0.95 * len(timings))]
        print(f"  Warm avg: {avg:.0f}ms")
        print(f"  P95: {p95:.0f}ms")
        print("  Target: <100ms")
        print(f"  Cache: {'WORKING' if avg < 100 else 'NOT WORKING — still slow'}")
        latest_status = cached_status_call(aggregated_system_status)
        if "cache_age_seconds" not in latest_status:
            print("  WARNING: cache_age_seconds missing — cache may not be implemented")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    print()
    print("--- Test 4: GPU vs CPU Speed Comparison ---")
    try:
        import torch
        import torch.nn as nn

        model_small = nn.Sequential(
            nn.Linear(267, 2048),
            nn.ReLU(),
            nn.Linear(2048, 2048),
            nn.ReLU(),
            nn.Linear(2048, 5),
        )
        x = torch.randn(32, 267)
        criterion = nn.CrossEntropyLoss()
        labels = torch.randint(0, 5, (32,))

        start = time.perf_counter()
        for _ in range(100):
            out = model_small(x)
            loss = criterion(out, labels)
            loss.backward()
        cpu_ms = (time.perf_counter() - start) * 1000 / 100
        print(f"  CPU forward+backward: {cpu_ms:.1f}ms/batch")

        if torch.cuda.is_available():
            model_gpu = model_small.cuda()
            x_gpu = x.cuda()
            labels_gpu = labels.cuda()
            torch.cuda.synchronize()
            start = time.perf_counter()
            for _ in range(100):
                out = model_gpu(x_gpu)
                loss = criterion(out, labels_gpu)
                loss.backward()
            torch.cuda.synchronize()
            gpu_ms = (time.perf_counter() - start) * 1000 / 100
            speedup = cpu_ms / gpu_ms if gpu_ms else 0.0
            print(f"  GPU forward+backward: {gpu_ms:.1f}ms/batch")
            print(f"  GPU speedup: {speedup:.1f}x faster than CPU")
        else:
            print("  GPU: Not available — training will be slower than GPU hardware")
    except Exception as exc:
        print(f"  ERROR: {exc}")


def step6_planned_vs_implemented() -> None:
    _print_header("STEP 6: PLANNED BUT NOT IMPLEMENTED")
    planned_features = [
        ("STT Pipeline (faster-whisper)", "backend/voice/production_voice.py", "FasterWhisperSTT"),
        ("TTS Pipeline (Piper)", "backend/voice/production_voice.py", "PiperTTS"),
        ("Voice Activity Detection", "backend/voice", "VAD"),
        ("Self-Reflection Engine", "backend/agent/self_reflection.py", "SelfReflectionEngine"),
        ("Method Invention Loop", "backend/agent/self_reflection.py", "invent_method"),
        ("Failure Pattern Analysis", "backend/agent", "failure_pattern"),
        ("Industrial AutoGrabber", "backend/ingestion/industrial_autograbber.py", "IndustrialAutoGrabber"),
        ("Parallel Source Fetching (asyncio)", "backend/ingestion/industrial_autograbber.py", "asyncio.gather"),
        ("11-Stage Filter Pipeline", "backend/ingestion/industrial_autograbber.py", "FilterPipeline"),
        ("Token-Aware Batching", "backend/ingestion/industrial_autograbber.py", "TokenBatch"),
        ("Expert Distributor", "backend/distributed/expert_distributor.py", "ExpertDistributor"),
        ("Cloud GPU Worker", "scripts/cloud_worker.py", "CloudGPUWorker"),
        ("Device Manager", "scripts/device_manager.py", "DeviceConfig"),
        ("Deep RL Agent", "backend/training/deep_rl_agent.py", "DeepRLAgent"),
        ("GRPO Reward Normalizer", "backend/training/deep_rl_agent.py", "GRPORewardNormalizer"),
        ("sklearn Feature Augmenter", "backend/training/deep_rl_agent.py", "SklearnFeatureAugmenter"),
        ("80+ Field Registry", "backend/testing/field_registry.py", "ALL_FIELDS"),
        ("Field-to-Expert Router", "backend/testing/field_registry.py", "get_fields_for_expert"),
        ("Zero-Loss Compressor", "backend/training/compression_engine.py", "ZeroLossCompressor"),
        ("Delta Compression", "backend/training/compression_engine.py", "delta"),
        ("MoE → training_controller", "training_controller.py", "MoEClassifier"),
        ("RL → incremental_trainer", "backend/training/incremental_trainer.py", "sample_weights"),
        ("EWC → incremental_trainer", "backend/training/incremental_trainer.py", "ewc_loss"),
        ("ClassBalancer → trainer", "backend/training/incremental_trainer.py", "ClassBalancer"),
        ("GradScaler → trainer", "backend/training/incremental_trainer.py", "GradScaler"),
        ("EarlyStopping → trainer", "backend/training/incremental_trainer.py", "EarlyStopping"),
        ("DB Connection Pool (FLAW-008)", "api/database.py", "pool"),
        ("JSON Library in C++ (FLAW-015)", "edge/data_extractor.cpp", "escape_json"),
        ("CMakeLists.txt (FLAW-N004)", "native/CMakeLists.txt", "cmake_minimum_required"),
        ("Real NCCL Allreduce (FLAW-N001)", "native/distributed/async_allreduce.cpp", "ncclAllReduce"),
        ("Persistent Nonces (FLAW-H002)", "backend/governance/approval_ledger.py", "_used_nonces"),
        ("Prometheus Metrics", "backend", "PrometheusMetricsRegistry"),
        ("Grafana Dashboard", ".", "grafana"),
        ("Redis Caching", "backend", "redis"),
        ("PostgreSQL Migration", "api", "asyncpg"),
    ]

    print(f"Checking {len(planned_features)} planned features...")
    print()
    implemented: list[str] = []
    missing: list[tuple[str, str, str]] = []
    partial: list[tuple[str, str, str]] = []

    for feature, location, pattern in planned_features:
        target = ROOT / location
        if not target.exists():
            missing.append((feature, location, "file/directory missing"))
            print(f"  MISSING   {feature}")
            continue

        suffixes = {".py", ".cpp", ".h", ".ts", ".tsx", ".md", ".txt", ".json"}
        hits = grep_literal([location], suffixes, pattern)
        if hits:
            implemented.append(feature)
            continue

        if target.is_file():
            partial.append((feature, location, f'file exists but "{pattern}" missing'))
            print(f"  PARTIAL   {feature}")
            print(f"            File exists: {location}")
            print(f'            Missing pattern: "{pattern}"')
        else:
            missing.append((feature, location, "file/directory missing"))
            print(f"  MISSING   {feature}")

    print()
    _print_header("IMPLEMENTATION STATUS")
    total = len(planned_features)
    print(f"IMPLEMENTED: {len(implemented)}/{total} ({len(implemented) / total * 100:.0f}%)")
    print(f"PARTIAL:     {len(partial)}/{total}")
    print(f"MISSING:     {len(missing)}/{total}")
    print()
    print("MISSING FEATURES (must implement):")
    for feature, location, _ in missing:
        print(f"  ❌ {feature}")
        print(f"     Expected: {location}")
    print()
    print("PARTIAL FEATURES (must complete wiring):")
    for feature, location, reason in partial:
        print(f"  ⚠️  {feature}")
        print(f"     {reason}")


def step7_maturity() -> None:
    _print_header("STEP 7: MATURITY RATING (EVIDENCE-BASED)")
    os.environ.update(
        {
            "YGB_USE_MOE": "true",
            "YGB_ENV": "development",
            "JWT_SECRET": "maturity-jwt-32chars-minimum-test!!",
            "YGB_VIDEO_JWT_SECRET": "maturity-video-32chars-min-test!!",
            "YGB_LEDGER_KEY": "maturity-ledger-dev-32chars-test!!",
            "YGB_REQUIRE_ENCRYPTION": "false",
        }
    )
    levels = {0: "NOT_STARTED", 1: "BASIC", 2: "PARTIAL", 3: "FUNCTIONAL", 4: "ADVANCED", 5: "PRODUCTION"}
    emoji = {0: "❌", 1: "🔴", 2: "🟡", 3: "🟢", 4: "🔵", 5: "⭐"}
    scores: dict[str, int] = {}

    def rate(name: str, fn: Callable[[], int]) -> int:
        try:
            level = fn()
            print(f"  {emoji.get(level, '❓')} {name}: {levels.get(level, 'UNKNOWN')} ({level}/5)")
            return level
        except Exception as exc:
            print(f"  ❌ {name}: ERROR — {str(exc)[:120]}")
            return 0

    print()
    print("--- Core ML ---")

    def rate_moe() -> int:
        try:
            from training_controller import _build_configured_model
            import torch

            model = _build_configured_model()
            params = sum(x.numel() for x in model.parameters())
            device = next(model.parameters()).device
            out = model(torch.randn(2, 267, device=device)).detach().cpu()
            if params > 100_000_000 and tuple(out.shape) == (2, 5):
                tc = read_text(ROOT / "training_controller.py")
                return 4 if "MoEClassifier" in tc else 3
            if params > 1_000_000:
                return 2
            return 1
        except Exception:
            return 0 if not (ROOT / "impl_v1" / "phase49" / "moe").exists() else 1

    def rate_training() -> int:
        content = read_text(ROOT / "backend" / "training" / "incremental_trainer.py")
        count = sum(
            token in content
            for token in (
                "label_smoothing",
                "weight_decay",
                "GradScaler",
                "EarlyStopping",
                "clip_grad_norm",
                "val_f1",
                "ClassBalancer",
                "sample_weights",
            )
        )
        if count >= 7:
            return 4
        if count >= 4:
            return 3
        if count >= 2:
            return 2
        return 1 if content else 0

    def rate_rl() -> int:
        try:
            from backend.training.rl_feedback import RLFeedbackCollector, RewardBuffer

            buf = RewardBuffer()
            collector = RLFeedbackCollector(buf)
            collector.record_prediction("CVE-2024-0001", "CRITICAL")
            collector.process_new_cisa_kev_batch(["CVE-2024-0001"])
            signals = buf.get_weighted_signals()
            if signals and signals[0][0].reward == 1.0:
                autograbber = read_text(ROOT / "backend" / "ingestion" / "autograbber.py")
                return 4 if "process_new_cisa_kev" in autograbber else 3
            return 2
        except Exception:
            return 0 if not (ROOT / "backend" / "training" / "rl_feedback.py").exists() else 1

    def rate_ewc() -> int:
        learner = ROOT / "backend" / "training" / "adaptive_learner.py"
        if not learner.exists():
            return 0
        content = read_text(learner)
        if "EWCRegularizer" not in content:
            return 1
        trainer = read_text(ROOT / "backend" / "training" / "incremental_trainer.py")
        return 4 if "ewc_loss" in trainer else 2

    scores["MoE Architecture"] = rate("MoE Architecture (23 experts)", rate_moe)
    scores["Training Anti-Overfit"] = rate("Training Anti-Overfitting", rate_training)
    scores["RL Feedback"] = rate("Reinforcement Learning", rate_rl)
    scores["EWC Adaptive"] = rate("EWC Adaptive Learning", rate_ewc)

    print()
    print("--- Data Pipeline ---")

    def rate_autograbber() -> int:
        content = read_text(ROOT / "backend" / "ingestion" / "autograbber.py")
        if not content:
            return 0
        scrapers = sum(1 for token in ("nvd", "cisa", "osv", "github", "exploitdb", "msrc", "redhat", "snyk", "vulnrichment") if token in content.lower())
        has_parallel = "asyncio" in content or "ThreadPoolExecutor" in content
        has_filter = "SampleQualityScorer" in content and "DataPurityEnforcer" in content
        if scrapers >= 9 and has_parallel and has_filter:
            return 4
        if scrapers >= 6 and has_filter:
            return 3
        if scrapers >= 3:
            return 2
        return 1

    def rate_industrial_grabber() -> int:
        content = read_text(ROOT / "backend" / "ingestion" / "industrial_autograbber.py")
        if not content:
            return 0
        if "asyncio.gather" in content and "FilterPipeline" in content and "TokenBatch" in content:
            return 4
        if "FilterPipeline" in content:
            return 2
        return 1

    def rate_scrapers() -> int:
        scraper_dir = ROOT / "backend" / "ingestion" / "scrapers"
        if not scraper_dir.exists():
            return 0
        scrapers = list(scraper_dir.glob("*_scraper.py"))
        if len(scrapers) >= 9:
            return 4
        if len(scrapers) >= 6:
            return 3
        if len(scrapers) >= 3:
            return 2
        return 1 if scrapers else 0

    scores["Autograbber"] = rate("Autograbber Pipeline", rate_autograbber)
    scores["Industrial Grabber"] = rate("Industrial Grabber (1M tok/sec)", rate_industrial_grabber)
    scores["Scrapers (9 sources)"] = rate("Data Scrapers (9 sources)", rate_scrapers)

    print()
    print("--- Security & Governance ---")

    def rate_security() -> int:
        os.environ["YGB_ENV"] = "production"
        try:
            from backend.auth.auth_guard import is_temporary_auth_bypass_enabled

            bypass = is_temporary_auth_bypass_enabled()
            bare_except_hits = grep_literal(["backend"], {".py"}, "except: pass") + grep_literal(["backend"], {".py"}, "except Exception: pass")
            db = read_text(ROOT / "api" / "database.py")
            has_pool = "pool" in db.lower()
            if not bypass and not bare_except_hits and has_pool:
                return 4
            if not bypass and not bare_except_hits:
                return 3
            if not bypass:
                return 2
            return 1
        except Exception:
            return 1

    def rate_governance() -> int:
        try:
            from backend.governance.authority_lock import AuthorityLock

            locked = AuthorityLock.verify_all_locked()
            if locked.get("all_locked"):
                gov_files = list(ROOT.rglob("governance_pipeline.py"))
                if gov_files:
                    content = read_text(gov_files[0])
                    if "except ImportError" in content and "pass" in content:
                        return 3
                return 4
            return 2
        except Exception:
            return 1

    scores["Security Hardening"] = rate("Security Hardening", rate_security)
    scores["Governance"] = rate("Governance (all_locked)", rate_governance)

    print()
    print("--- Operational ---")

    def rate_voice() -> int:
        primary = ROOT / "backend" / "voice" / "production_voice.py"
        fallback = ROOT / "backend" / "assistant" / "voice_runtime.py"
        if primary.exists():
            content = read_text(primary)
            if "FasterWhisperSTT" in content and "PiperTTS" in content:
                return 3
            return 2
        if fallback.exists():
            content = read_text(fallback)
            if "whisper" in content.lower():
                return 2
            return 1
        return 0

    def rate_self_reflect() -> int:
        content = read_text(ROOT / "backend" / "agent" / "self_reflection.py")
        if not content:
            return 0
        if "SelfReflectionEngine" in content and "invent" in content.lower():
            return 3
        return 1

    def rate_field_registry() -> int:
        file_path = ROOT / "backend" / "testing" / "field_registry.py"
        content = read_text(file_path)
        if not content:
            return 0
        try:
            from backend.testing.field_registry import ALL_FIELDS

            count = len(ALL_FIELDS)
            if count >= 80:
                return 4
            if count >= 50:
                return 3
            return 2
        except Exception:
            return 1 if "ALL_FIELDS" in content else 0

    def rate_sync() -> int:
        content = read_text(ROOT / "backend" / "sync" / "sync_engine.py")
        if not content:
            return 0
        if "STANDALONE" in content and "LocalSyncIndex" in content:
            return 3
        if "SyncMode" in content:
            return 2
        return 1

    def rate_compression() -> int:
        content = read_text(ROOT / "backend" / "training" / "compression_engine.py")
        if not content:
            return 0
        if "heuristic" in content.lower() or "estimate" in content.lower():
            return 2
        if "ZeroLossCompressor" in content and "lz4" in content:
            return 4
        if "ZeroLossCompressor" in content:
            return 3
        return 1

    scores["Voice STT/TTS"] = rate("Voice Pipeline STT→TTS", rate_voice)
    scores["Self-Reflection"] = rate("Self-Reflection Loop", rate_self_reflect)
    scores["Field Registry 80+"] = rate("80+ Field Testing", rate_field_registry)
    scores["Sync Engine"] = rate("Sync Engine", rate_sync)
    scores["Zero-Loss Compression"] = rate("Zero-Loss Compression", rate_compression)

    print()
    print("--- Performance ---")

    def rate_status_perf() -> int:
        try:
            os.environ.update(_status_env())
            from backend.api.system_status import aggregated_system_status

            cached_status_call(aggregated_system_status)
            values = []
            for _ in range(10):
                start = time.perf_counter()
                cached_status_call(aggregated_system_status)
                values.append((time.perf_counter() - start) * 1000)
            avg = statistics.mean(values)
            if avg < 50:
                return 5
            if avg < 100:
                return 4
            if avg < 500:
                return 3
            return 2
        except Exception:
            return 0

    def rate_expert_queue() -> int:
        try:
            from scripts.expert_task_queue import ExpertTaskQueue

            queue = ExpertTaskQueue(status_path=_audit_queue_status_path())
            queue.initialize_status_file()
            status = _queue_experts_snapshot(queue)
            if len(status) != 23:
                return 2
            claimed: list[str] = []
            lock = threading.Lock()

            def claim() -> None:
                expert = queue.claim_next_expert(f"maturity-worker-{uuid.uuid4().hex[:8]}")
                with lock:
                    if expert:
                        claimed.append(str(expert.get("expert_id")))

            threads = [threading.Thread(target=claim) for _ in range(5)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            if len(claimed) == len(set(claimed)):
                return 4
            return 2
        except Exception:
            return 0 if not (ROOT / "scripts" / "expert_task_queue.py").exists() else 1

    scores["Status Cache Perf"] = rate("Status API Performance", rate_status_perf)
    scores["Expert Queue"] = rate("Expert Task Queue (23 experts)", rate_expert_queue)

    print()
    _print_header("FINAL MATURITY SCORECARD")
    total = sum(scores.values())
    max_score = len(scores) * 5
    pct = total / max_score * 100 if max_score else 0.0
    by_level: dict[int, list[str]] = {level: [] for level in range(6)}
    for feature, score in scores.items():
        by_level[score].append(feature)
    for level in [5, 4, 3, 2, 1, 0]:
        features = by_level[level]
        if features:
            print(f"{emoji[level]} {levels[level]} ({len(features)}): {' | '.join(features)}")
    print()
    print(f"OVERALL SCORE: {total}/{max_score} = {pct:.0f}%")
    print()
    if pct >= 85:
        verdict = "NEAR PRODUCTION — minor gaps remain"
    elif pct >= 65:
        verdict = "FUNCTIONAL — significant gaps in advanced features"
    elif pct >= 45:
        verdict = "PARTIAL — core works but many features incomplete"
    else:
        verdict = "EARLY STAGE — substantial implementation needed"
    print(f"VERDICT: {verdict}")
    print()
    print("TOP PRIORITY FIXES:")
    low = sorted(((feature, score) for feature, score in scores.items() if score < 3), key=lambda item: item[1])
    for feature, score in low[:8]:
        print(f"  {emoji[score]} {feature} (currently {levels[score]}) — needs immediate work")


def step9_final_gate() -> None:
    _print_header("FINAL VERIFICATION GATE")
    os.environ.update(
        {
            "YGB_USE_MOE": "true",
            "YGB_ENV": "development",
            "JWT_SECRET": "final-gate-jwt-32chars-min-test!!!",
            "YGB_VIDEO_JWT_SECRET": "final-gate-video-jwt-32chars-min!!",
            "YGB_LEDGER_KEY": "final-gate-ledger-dev-32chars-key!!",
            "YGB_REQUIRE_ENCRYPTION": "false",
        }
    )
    gates: dict[str, str] = {}

    def gate(name: str, fn: Callable[[], bool]) -> None:
        try:
            result = fn()
            gates[name] = "PASS" if result else "FAIL"
            print(f"  {'✓' if result else '✗'} {name}")
        except Exception as exc:
            gates[name] = f"ERROR: {str(exc)[:120]}"
            print(f"  ✗ {name}: {str(exc)[:120]}")

    def g_tests() -> bool:
        result = run_py([sys.executable, "-m", "pytest", "-q", "--tb=no"], timeout=3600)
        match = re.search(r"(\d+)\s+passed", result.stdout)
        if match:
            count = int(match.group(1))
            print(f"    ({count} tests passed)")
            return count >= 3000
        return False

    def g_bare() -> bool:
        hits = grep_literal(["backend", "impl_v1"], {".py"}, "except: pass") + grep_literal(["backend", "impl_v1"], {".py"}, "except Exception: pass")
        print(f"    ({len(hits)} bare excepts found)")
        return len(hits) == 0

    def g_lock() -> bool:
        from backend.governance.authority_lock import AuthorityLock

        result = AuthorityLock.verify_all_locked()
        return result.get("all_locked") is True

    def g_moe() -> bool:
        from training_controller import _build_configured_model

        model = _build_configured_model()
        params = sum(x.numel() for x in model.parameters())
        print(f"    ({params / 1e6:.1f}M params)")
        return params > 100_000_000

    def g_nomock() -> bool:
        candidates = []
        for pattern in ("np.random.rand", "torch.randn(", "fake_data", "mock_data"):
            candidates.extend(grep_literal(["backend", "training_controller.py"], {".py"}, pattern, skip_tests=True))
        unique_files = sorted({path for path, _, _ in candidates})
        if unique_files:
            print(f"    FAIL: {len(unique_files)} files still have mock data: {unique_files[:3]}")
        return not unique_files

    def g_queue() -> bool:
        from scripts.expert_task_queue import ExpertTaskQueue

        queue = ExpertTaskQueue(status_path=_audit_queue_status_path())
        queue.initialize_status_file()
        assert len(_queue_experts_snapshot(queue)) == 23
        claimed: list[str] = []
        lock = threading.Lock()

        def claim() -> None:
            expert = queue.claim_next_expert(f"gate-worker-{uuid.uuid4().hex[:8]}")
            with lock:
                if expert:
                    claimed.append(str(expert.get("expert_id")))

        threads = [threading.Thread(target=claim) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        no_dup = len(claimed) == len(set(claimed))
        print(f"    (23 experts, {'no' if no_dup else 'DUPLICATE'} race condition)")
        return no_dup

    def g_cache() -> bool:
        os.environ.update(_status_env())
        from backend.api.system_status import aggregated_system_status

        cached_status_call(aggregated_system_status)
        values = []
        for _ in range(10):
            start = time.perf_counter()
            cached_status_call(aggregated_system_status)
            values.append((time.perf_counter() - start) * 1000)
        avg = statistics.mean(values)
        print(f"    (avg {avg:.0f}ms)")
        return avg < 100

    def g_scrapers() -> bool:
        scraper_dir = ROOT / "backend" / "ingestion" / "scrapers"
        if not scraper_dir.exists():
            return False
        scrapers = list(scraper_dir.glob("*_scraper.py"))
        print(f"    ({len(scrapers)} scrapers found)")
        return len(scrapers) >= 9

    def g_noextai() -> bool:
        hits = []
        for pattern in ("openai", "anthropic.Anthropic", "claude.ai", "gemini"):
            hits.extend(grep_literal(["backend", "api", "training_controller.py"], {".py"}, pattern))
        filtered = [hit for hit in hits if "test_" not in hit[0] and "__pycache__" not in hit[0]]
        if filtered:
            print("    FAIL: External AI API calls found:")
            for file_path, lineno, line in filtered[:3]:
                print(f"      {file_path}:{lineno}: {line[:120]}")
        return not filtered

    def g_bugs() -> bool:
        bugs_remaining = 0
        db = read_text(ROOT / "api" / "database.py")
        if "global" in db and "aiosqlite" in db and "pool" not in db.lower():
            print("    REMAINING: FLAW-008 (single DB connection)")
            bugs_remaining += 1
        if not list(ROOT.rglob("CMakeLists.txt")):
            print("    REMAINING: FLAW-N004 (no build system)")
            bugs_remaining += 1
        print(f"    ({bugs_remaining} critical bugs remaining)")
        return bugs_remaining == 0

    gate("Test suite >= 3000 passing", g_tests)
    gate("Zero bare except:pass", g_bare)
    gate("Authority lock all_locked=True", g_lock)
    gate("MoE active > 100M params", g_moe)
    gate("Zero mock/synthetic data in production", g_nomock)
    gate("Expert queue: 23 experts, atomic claims", g_queue)
    gate("Status cache < 100ms warm", g_cache)
    gate("9 scrapers defined", g_scrapers)
    gate("No external AI API dependencies", g_noextai)
    gate("All critical bugs fixed", g_bugs)

    print()
    _print_header("GATE RESULTS")
    passed = sum(1 for value in gates.values() if value == "PASS")
    total = len(gates)
    score = passed / total * 100 if total else 0.0
    print(f"PASSED: {passed}/{total} ({score:.0f}%)")
    print()
    if score >= 90:
        print("STATUS: PRODUCTION READY")
    elif score >= 70:
        print("STATUS: NEAR READY — fix remaining items")
    elif score >= 50:
        print("STATUS: FUNCTIONAL — significant work needed")
    else:
        print("STATUS: NOT READY — major gaps remain")

    failing = [(name, value) for name, value in gates.items() if value != "PASS"]
    if failing:
        print()
        print("FAILING GATES:")
        for name, value in failing:
            print(f"  ✗ {name}: {value}")


STEPS: dict[str, Callable[[], None]] = {
    "step0": step0_baseline,
    "step1": step1_mock_hunt,
    "step2": step2_bug_verification,
    "step3": step3_gpu_audit,
    "step4": step4_scraper_reality,
    "step5": step5_parallelism,
    "step6": step6_planned_vs_implemented,
    "step7": step7_maturity,
    "step9": step9_final_gate,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run industrial audit steps and persist outputs.")
    parser.add_argument("steps", nargs="*", choices=sorted(STEPS.keys()) + ["all"], default=["all"])
    args = parser.parse_args()
    selected = ["step0", "step1", "step2", "step3", "step4", "step5", "step6", "step7"] if args.steps == ["all"] else args.steps
    for step_name in selected:
        write_step(step_name, STEPS[step_name])


if __name__ == "__main__":
    main()
