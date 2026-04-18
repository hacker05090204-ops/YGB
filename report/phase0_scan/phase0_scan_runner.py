from __future__ import annotations

import ast
import json
import os
import re
import time
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "report" / "phase0_scan"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

EXCLUDED_PARTS = {"__pycache__", ".git", "node_modules", "dist", ".next"}
PRODUCTION_EXCLUDED_PARTS = EXCLUDED_PARTS | {"tests"}


def _is_excluded(path: Path, include_tests: bool = True) -> bool:
    excluded = EXCLUDED_PARTS if include_tests else PRODUCTION_EXCLUDED_PARTS
    if any(part in excluded for part in path.parts):
        return True
    if not include_tests and path.name.startswith("test_"):
        return True
    return False


def _iter_py_files(include_tests: bool = True) -> Iterable[Path]:
    for path in ROOT.rglob("*.py"):
        if not _is_excluded(path, include_tests=include_tests):
            yield path


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _write_text_report(filename: str, lines: list[str]) -> None:
    (REPORT_DIR / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")


def scan_a() -> None:
    lines = ["=" * 70, "SCAN A: PLANNED BUT NOT IMPLEMENTED", "=" * 70]
    planned: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(item_type: str, location: str) -> None:
        key = (item_type, location)
        if key not in seen:
            seen.add(key)
            planned.append({"type": item_type, "location": location[:240]})

    for path in _iter_py_files(include_tests=True):
        text = _read_text(path)
        rel = _rel(path)
        file_lines = text.splitlines()

        for idx, line in enumerate(file_lines, start=1):
            stripped = line.strip()
            if "raise NotImplementedError" in line:
                add("NotImplementedError", f"{rel}:{idx}: {stripped}")
            if any(token in line for token in ("# TODO", "# FIXME", "# NOT IMPLEMENTED")):
                if "tests" not in path.parts and not path.name.startswith("test_"):
                    add("TODO", f"{rel}:{idx}: {stripped}")

        for idx, line in enumerate(file_lines[:-1], start=1):
            if re.match(r"^\s*(async\s+def|def)\s+\w+\s*\(.*\)\s*:", line):
                nxt = file_lines[idx].strip()
                if nxt in {"pass", "...", "# TODO", "# FIXME", "# NOT IMPLEMENTED"}:
                    add("empty_function", f"{rel}:{idx}: {line.strip()}")

        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            add("syntax_parse_error", f"{rel}:{exc.lineno}: {exc.msg}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and len(node.body) == 1:
                stmt = node.body[0]
                if isinstance(stmt, ast.Pass):
                    add("empty_function", f"{rel}:{node.lineno}: def {node.name}(...) pass")
                elif (
                    isinstance(stmt, ast.Expr)
                    and isinstance(getattr(stmt, "value", None), ast.Constant)
                    and stmt.value.value is Ellipsis
                ):
                    add("empty_function", f"{rel}:{node.lineno}: def {node.name}(...) ...")

    for directory in ROOT.iterdir():
        if directory.is_dir() and not directory.name.startswith(".") and directory.name not in {"node_modules", "dist", ".next"}:
            has_python = any(True for child in directory.rglob("*.py") if not _is_excluded(child, include_tests=True))
            if not has_python:
                add("empty_directory", directory.name)

    lines.append(f"Found {len(planned)} planned-but-not-implemented items")
    for item in planned[:50]:
        lines.append(f"  [{item['type']}] {item['location'][:90]}")
    lines.append("")
    lines.append("Full list: report/phase0_scan/planned_not_implemented.json")

    (REPORT_DIR / "planned_not_implemented.json").write_text(json.dumps(planned, indent=2), encoding="utf-8")
    _write_text_report("scan_a.txt", lines)


def scan_b() -> None:
    lines = ["=" * 70, "SCAN B: MOCK/FAKE DATA HUNT", "=" * 70]
    violations: list[dict[str, str]] = []

    patterns = {
        "CRITICAL_FAKE_TENSOR": [
            r"np\.random\.rand\(",
            r"np\.random\.randn\(",
            r"np\.random\.randint\(",
            r"torch\.randn\(",
            r"torch\.rand\(",
            r"torch\.zeros\(.*label",
            r"torch\.ones\(.*label",
        ],
        "CRITICAL_HARDCODED_METRIC": [
            r"return 0\.95",
            r"return 0\.87",
            r"return 0\.9",
            r"accuracy\s*=\s*1\.0",
            r"f1\s*=\s*0\.9",
            r"val_f1\s*=\s*0\.8",
            r"return True\s*# always",
            r"return 1\.0\s*# fake",
            r"return \[\]\s*# TODO",
            r"return \{\}\s*# placeholder",
        ],
        "CRITICAL_SIMULATED": [
            r"SIMULATED",
            r"simulated_result",
            r"fake_",
            r"FAKE ",
            r"dummy_data",
            r"mock_data",
            r"synthetic_data",
            r"placeholder_value",
        ],
        "CRITICAL_BYPASS": [
            r"skip_verification\s*=\s*True",
            r"bypass_auth",
            r"TEMP_AUTH_BYPASS",
            r"skip_validation\s*=\s*True",
        ],
        "HIGH_INCOMPLETE": [
            r"except:\s*pass",
            r"except Exception:\s*pass",
            r"except Exception as e:\s*pass",
        ],
        "HIGH_HARDCODED_DEVICE": [
            r"leader_node.*RTX",
            r"RTX2050",
            r"RTX 2050",
            r"hostname.*=.*laptop",
            r"device.*=.*my_machine",
        ],
    }

    for path in _iter_py_files(include_tests=False):
        text = _read_text(path)
        rel = _rel(path)
        file_lines = text.splitlines()
        for severity, regexes in patterns.items():
            for regex in regexes:
                matcher = re.compile(regex)
                for idx, line in enumerate(file_lines, start=1):
                    if matcher.search(line):
                        violations.append(
                            {
                                "severity": severity,
                                "file": rel,
                                "pattern": regex,
                                "line": f"{idx}:{line.strip()[:100]}",
                            }
                        )

    (REPORT_DIR / "mock_violations.json").write_text(json.dumps(violations, indent=2), encoding="utf-8")

    critical = [v for v in violations if "CRITICAL" in v["severity"]]
    high = [v for v in violations if "HIGH" in v["severity"]]
    lines.append(f"CRITICAL violations: {len(critical)}")
    lines.append(f"HIGH violations: {len(high)}")
    lines.append("")
    lines.append("CRITICAL (must fix):")
    for item in critical[:30]:
        lines.append(f"  [{item['file']}] {item['line']}")
    _write_text_report("scan_b.txt", lines)


def scan_c() -> None:
    lines = ["=" * 70, "SCAN C: WIRING STATUS", "=" * 70]
    wiring_matrix = [
        ("MoE→training_controller", "training_controller.py", "MoEClassifier", "CRITICAL"),
        ("MoE→auto_train_controller", "backend/training/auto_train_controller.py", "MoEClassifier", "CRITICAL"),
        ("EarlyStopping→trainer", "backend/training/incremental_trainer.py", "EarlyStopping", "HIGH"),
        ("GradScaler→trainer", "backend/training/incremental_trainer.py", "GradScaler", "HIGH"),
        ("label_smoothing→trainer", "backend/training/incremental_trainer.py", "label_smoothing", "HIGH"),
        ("weight_decay→optimizer", "backend/training/incremental_trainer.py", "weight_decay", "HIGH"),
        ("clip_grad_norm→trainer", "backend/training/incremental_trainer.py", "clip_grad_norm", "HIGH"),
        ("ClassBalancer→trainer", "backend/training/incremental_trainer.py", "ClassBalancer", "HIGH"),
        ("val_f1_checkpoint", "backend/training/incremental_trainer.py", "val_f1", "HIGH"),
        ("RL_rewards→auto_trainer", "backend/training/auto_train_controller.py", "get_reward_buffer", "HIGH"),
        ("RL_weights→trainer", "backend/training/incremental_trainer.py", "sample_weights", "HIGH"),
        ("CISA_KEV→rl_collector", "backend/ingestion/autograbber.py", "process_new_cisa_kev", "HIGH"),
        ("EWC→trainer_loss", "backend/training/incremental_trainer.py", "ewc_loss", "HIGH"),
        ("DistMonitor→autograbber", "backend/ingestion/autograbber.py", "on_new_grab_cycle", "MEDIUM"),
        ("QualityScorer→autograbber", "backend/ingestion/autograbber.py", "SampleQualityScorer", "CRITICAL"),
        ("PurityEnforcer→autograbber", "backend/ingestion/autograbber.py", "DataPurityEnforcer", "CRITICAL"),
        ("DedupStore→autograbber", "backend/ingestion/autograbber.py", "DedupStore", "CRITICAL"),
        ("9scrapers→autograbber", "backend/ingestion/autograbber.py", "exploitdb", "HIGH"),
        ("StatusCache→system_status", "backend/api/system_status.py", "CACHE_TTL", "HIGH"),
        ("BgRefresh→system_status", "backend/api/system_status.py", "_trigger_background", "HIGH"),
        ("GovernanceHardFail", "impl_v1/training/data/governance_pipeline.py", "raise RuntimeError", "CRITICAL"),
        ("AuditNoSwallow", "impl_v1/training/data/governance_pipeline.py", "raise", "CRITICAL"),
        ("WorkflowOrchestrator→agent", "backend/tasks/industrial_agent.py", "AutonomousWorkflowOrchestrator", "HIGH"),
        ("DBConnectionPool", "api/database.py", "pool", "CRITICAL"),
        ("BypassDisabledProd", "backend/auth/auth_guard.py", "production", "CRITICAL"),
        ("ExpertDistributor", "backend/distributed/expert_distributor.py", "ExpertDistributor", "HIGH"),
        ("CloudWorker", "scripts/cloud_worker.py", "CloudGPUWorker", "HIGH"),
        ("FastWhisperSTT", "backend/voice/production_voice.py", "FastWhisperSTT", "MEDIUM"),
        ("SelfReflectionEngine", "backend/agent/self_reflection.py", "SelfReflectionEngine", "MEDIUM"),
        ("FieldRegistry80plus", "backend/testing/field_registry.py", "ALL_FIELDS", "MEDIUM"),
        ("OSV_fix", "backend/ingestion/scrapers/osv_scraper.py", "api.osv.dev", "HIGH"),
        ("ExploitDB_fix", "backend/ingestion/scrapers/exploit_db_scraper.py", "exploit-db.com", "HIGH"),
        ("RedHat_fix", "backend/ingestion/scrapers/vendor_advisory_scraper.py", "redhat", "HIGH"),
        ("Snyk_fix", "backend/ingestion/scrapers/snyk_scraper.py", "snyk", "HIGH"),
        ("VulnRichment_fix", "backend/ingestion/scrapers/vulnrichment_scraper.py", "vulnrichment", "HIGH"),
        ("GPU_MoE", "impl_v1/phase49/moe/__init__.py", ".to(device)", "HIGH"),
        ("GPU_auto_trainer", "backend/training/auto_train_controller.py", "cuda", "HIGH"),
        ("SSD_IO_async", "backend/ingestion/autograbber.py", "asyncio", "HIGH"),
        ("SSD_storage_path", "backend/storage/tiered_storage.py", "ssd", "MEDIUM"),
        ("NonceDB_persist", "HUMANOID_HUNTER", r"sqlite|redis", "CRITICAL"),
        ("CompressionRealBytes", "backend/training/compression_engine.py", "stat().st_size", "HIGH"),
        ("VulnDetectionEngine", "backend/intelligence", "vulnerability_detector", "CRITICAL"),
        ("PayloadGenerator", "backend/intelligence", "payload_generator", "HIGH"),
        ("ScannerEngine", "backend/scanner", "scanner", "HIGH"),
    ]

    results: dict[str, list[dict[str, str]]] = {"wired": [], "not_wired": [], "file_missing": []}

    for desc, filepath, pattern, criticality in wiring_matrix:
        target = ROOT / filepath
        found = False
        if target.is_dir():
            regex = re.compile(pattern)
            for py_file in target.rglob("*.py"):
                if _is_excluded(py_file, include_tests=True):
                    continue
                if regex.search(_read_text(py_file)):
                    found = True
                    break
        elif target.exists():
            found = bool(re.search(pattern, _read_text(target)))
        else:
            results["file_missing"].append({"desc": desc, "path": filepath, "criticality": criticality})
            lines.append(f"  FILE MISSING  [{criticality}] {desc}: {filepath}")
            continue

        if found:
            results["wired"].append({"desc": desc, "path": filepath})
        else:
            results["not_wired"].append(
                {"desc": desc, "path": filepath, "pattern": pattern, "criticality": criticality}
            )
            lines.append(f'  NOT WIRED     [{criticality}] {desc}: "{pattern}" missing in {filepath}')

    lines.append("")
    lines.append(f"WIRED:        {len(results['wired'])}/{len(wiring_matrix)}")
    lines.append(f"NOT_WIRED:    {len(results['not_wired'])}/{len(wiring_matrix)}")
    lines.append(f"FILE_MISSING: {len(results['file_missing'])}/{len(wiring_matrix)}")

    (REPORT_DIR / "wiring_status.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    _write_text_report("scan_c.txt", lines)


def scan_d() -> None:
    lines = ["=" * 70, "SCAN D: GPU UTILIZATION", "=" * 70]

    try:
        import torch

        has_gpu = torch.cuda.is_available()
        if has_gpu:
            props = torch.cuda.get_device_properties(0)
            lines.append(f"GPU: {props.name} | VRAM: {props.total_memory / 1e9:.1f}GB | CUDA: {torch.version.cuda}")
            lines.append(f"GPU count: {torch.cuda.device_count()}")
        else:
            lines.append("WARNING: No GPU available — Colab/Lightning required for training")
    except ImportError:
        lines.append("ERROR: torch not installed")

    gpu_required_files = [
        "training_controller.py",
        "backend/training/incremental_trainer.py",
        "backend/training/auto_train_controller.py",
        "impl_v1/phase49/moe/__init__.py",
        "impl_v1/phase49/moe/expert.py",
        "backend/ingestion/industrial_autograbber.py",
    ]
    gpu_indicators = [".to(device)", ".cuda()", "torch.cuda", "device = ", "GradScaler", "autocast"]

    lines.append("")
    lines.append("--- GPU Usage in Critical Files ---")
    for filepath in gpu_required_files:
        path = ROOT / filepath
        if not path.exists():
            lines.append(f"  MISSING  {filepath}")
            continue
        content = _read_text(path)
        found = [indicator for indicator in gpu_indicators if indicator in content]
        if len(found) >= 3:
            lines.append(f"  GPU OK   {filepath}: {found}")
        elif found:
            lines.append(f"  GPU WEAK {filepath}: only {found} — needs more GPU ops")
        else:
            lines.append(f"  NO GPU   {filepath} — running on CPU only!")

    cpu_pattern = re.compile(r"device\s*=\s*.*cpu|device.*cpu.*fallback")
    cpu_hits: list[str] = []
    for filepath in ["backend/training", "training_controller.py"]:
        target = ROOT / filepath
        if target.is_dir():
            for py_file in target.rglob("*.py"):
                text = _read_text(py_file)
                for idx, line in enumerate(text.splitlines(), start=1):
                    if cpu_pattern.search(line):
                        cpu_hits.append(f"{_rel(py_file)}:{idx}:{line.strip()}")
        elif target.exists():
            text = _read_text(target)
            for idx, line in enumerate(text.splitlines(), start=1):
                if cpu_pattern.search(line):
                    cpu_hits.append(f"{_rel(target)}:{idx}:{line.strip()}")

    lines.append("")
    lines.append(f"CPU-only patterns: {len(cpu_hits)} (these should GPU-first)")
    for hit in cpu_hits[:5]:
        lines.append(f"  {hit[:90]}")
    _write_text_report("scan_d.txt", lines)


def scan_e() -> None:
    lines = ["=" * 70, "SCAN E: SCRAPER URL HEALTH", "=" * 70]
    results: dict[str, dict[str, object]] = {}
    live_count = 0
    ua = "YBG-Roo/2.0 (security research; non-commercial)"

    urls = {
        "NVD_v2": {"method": "GET", "url": "https://services.nvd.nist.gov/rest/json/cves/2.0", "params": {"resultsPerPage": 1}},
        "CISA_KEV": {"method": "GET", "url": "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"},
        "OSV_API": {
            "method": "POST",
            "url": "https://api.osv.dev/v1/query",
            "json": {"package": {"ecosystem": "npm", "name": "lodash"}},
        },
        "GitHub_Adv": {"method": "GET", "url": "https://api.github.com/advisories", "params": {"per_page": 1, "type": "reviewed"}},
        "ExploitDB_CSV": {"method": "GET", "url": "https://gitlab.com/exploit-database/exploitdb/-/raw/main/files_exploits.csv", "stream": True},
        "MSRC": {"method": "GET", "url": "https://api.msrc.microsoft.com/cvrf/v2.0/updates"},
        "RedHat_API": {
            "method": "GET",
            "url": "https://access.redhat.com/hydra/rest/securitydata/cve.json",
            "params": {"per_page": 1, "after": "2024-01-01"},
        },
        "Snyk_Query": {
            "method": "POST",
            "url": "https://api.osv.dev/v1/query",
            "json": {"package": {"ecosystem": "npm", "name": "lodash"}},
        },
        "VulnRichment": {"method": "GET", "url": "https://api.github.com/repos/cisagov/vulnrichment/contents/"},
        "PacketStorm": {"method": "GET", "url": "https://rss.packetstormsecurity.com/files/"},
        "AlpineSecDB": {"method": "GET", "url": "https://secdb.alpinelinux.org/v3.20/main.json", "stream": True},
        "DebianSec": {"method": "GET", "url": "https://security-tracker.debian.org/tracker/CVE-2024-3094", "timeout": 20},
    }

    try:
        import requests
    except ImportError as exc:
        lines.append(f"ERROR: requests not installed: {exc}")
        (REPORT_DIR / "scraper_health.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        _write_text_report("scan_e.txt", lines)
        return

    for name, request_spec in urls.items():
        started = time.perf_counter()
        try:
            response = requests.request(
                request_spec["method"],
                request_spec["url"],
                params=request_spec.get("params"),
                json=request_spec.get("json"),
                timeout=request_spec.get("timeout", 12),
                headers={"User-Agent": ua},
                stream=bool(request_spec.get("stream", False)),
            )
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            code = response.status_code
            if code == 200:
                live_count += 1
                results[name] = {"status": "LIVE", "code": 200, "ms": elapsed_ms}
                lines.append(f"  LIVE  {name}: {elapsed_ms}ms")
            elif code == 304:
                live_count += 1
                results[name] = {"status": "NO_DELTA", "code": 304, "ms": elapsed_ms}
                lines.append(f"  304   {name}: no delta")
            elif code == 400:
                results[name] = {"status": "FIX_URL", "code": 400, "url": request_spec["url"]}
                lines.append(f"  400   {name}: URL format wrong — FIX SCRAPER")
            elif code == 404:
                results[name] = {"status": "MOVED", "code": 404, "url": request_spec["url"]}
                lines.append(f"  404   {name}: endpoint moved — UPDATE URL")
            elif code == 410:
                results[name] = {"status": "GONE", "code": 410, "url": request_spec["url"]}
                lines.append(f"  410   {name}: endpoint gone — FIND ALTERNATIVE")
            else:
                results[name] = {"status": f"HTTP_{code}", "code": code}
                lines.append(f"  {code}  {name}: unexpected")
        except requests.Timeout:
            results[name] = {"status": "TIMEOUT"}
            lines.append(f"  TIME  {name}: timeout")
        except Exception as exc:  # explicit record for scan output only
            results[name] = {"status": "ERROR", "error": str(exc)[:80]}
            lines.append(f"  ERR   {name}: {str(exc)[:40]}")
        time.sleep(1)

    broken = [name for name, result in results.items() if result.get("status") not in {"LIVE", "NO_DELTA"}]
    lines.append("")
    lines.append(f"LIVE: {live_count}/{len(urls)} sources reachable")
    lines.append(f"BROKEN (need URL fix): {broken}")

    (REPORT_DIR / "scraper_health.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    _write_text_report("scan_e.txt", lines)


def scan_f() -> None:
    lines = ["=" * 70, "SCAN F: CAPABILITY GAPS", "=" * 70]
    search_roots = [ROOT / "backend", ROOT / "api", ROOT / "impl_v1", ROOT / "HUMANOID_HUNTER", ROOT / "training_controller.py"]

    capabilities = {
        "SQL Injection Detection": ["sqli_detect", "sql_inject", "sqlinjection", "sqli_scanner"],
        "XSS Detection": ["xss_detect", "xss_scanner", "xss_payload", "reflected_xss"],
        "SSRF Detection": ["ssrf_detect", "ssrf_scanner", "ssrf_payload"],
        "Auth Bypass Detection": ["auth_bypass_detect", "authbypass_scan"],
        "IDOR Detection": ["idor_detect", "idor_scan", "object_reference"],
        "RCE Detection": ["rce_detect", "rce_scan", "command_inject"],
        "Payload Generation": ["payload_gen", "generate_payload", "payload_builder"],
        "POC Generation": ["poc_gen", "generate_poc", "poc_builder", "exploit_gen"],
        "Vulnerability Scanner": ["vuln_scan", "vulnerability_scan", "scanner_engine"],
        "Report Generation (real)": ["vuln_report", "vulnerability_report_gen", "writeup_gen"],
        "Self-Reflection Loop": ["self_reflect", "SelfReflectionEngine", "invent_method"],
        "Deep RL Agent": ["DeepRLAgent", "GRPORewardNormalizer", "deep_rl"],
        "Multi-GPU DDP": ["DistributedDataParallel", "torch.distributed", "dist.init_process"],
        "Real NCCL": ["ncclAllReduce", "nccl_allreduce", "ncclInit"],
        "Production STT": ["WhisperModel", "faster_whisper", "transcribe_audio"],
        "Bug Bounty Integration": ["hackerone", "bugcrowd", "intigriti", "platform_submit"],
        "Sandbox Execution": ["sandbox_exec", "isolate_execution", "containment_exec"],
        "Evidence Capture": ["evidence_capture", "screenshot_evidence", "capture_proof"],
        "Exploit Chain": ["exploit_chain", "chain_attack", "multi_step_exploit"],
        "Scope Validator": ["scope_valid", "in_scope_check", "target_scope"],
    }

    searchable: list[tuple[str, str]] = []
    for root in search_roots:
        if root.is_file():
            searchable.append((_rel(root), _read_text(root)))
        elif root.exists():
            for py_file in root.rglob("*.py"):
                if _is_excluded(py_file, include_tests=False):
                    continue
                searchable.append((_rel(py_file), _read_text(py_file)))

    results: dict[str, dict[str, object]] = {}
    for capability, patterns in capabilities.items():
        found_in: list[str] = []
        for pattern in patterns:
            for rel_path, content in searchable:
                if pattern in content:
                    found_in.append(rel_path)
        deduped = sorted(set(found_in))[:3]
        status = "IMPLEMENTED" if deduped else "MISSING"
        results[capability] = {"status": status, "files": deduped}
        icon = "✓" if status == "IMPLEMENTED" else "✗"
        lines.append(f"  {icon} {capability}: {status}")
        for file_path in deduped[:2]:
            lines.append(f"    → {file_path}")

    missing = [name for name, result in results.items() if result["status"] == "MISSING"]
    lines.append("")
    lines.append(f"MISSING CAPABILITIES: {len(missing)}/{len(capabilities)}")
    lines.append("These must be implemented:")
    for item in missing:
        lines.append(f"  ❌ {item}")

    (REPORT_DIR / "capability_gaps.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    _write_text_report("scan_f.txt", lines)


def scan_g() -> None:
    lines = ["=" * 70, "SCAN G: SSD MIGRATION STATUS", "=" * 70]
    hdd_patterns = [r"D:\\", "/hdd/", "/mnt/hdd", "hdd_drive", ".tmp_hdd", "HDD_PATH", "hdd_path", "D:/ygb_data"]
    ssd_indicators = ["ssd", "SSD", "/fast/", "/nvme/", "training/features_safetensors"]

    hdd_refs: list[dict[str, str]] = []
    for path in _iter_py_files(include_tests=True):
        text = _read_text(path)
        rel = _rel(path)
        for idx, line in enumerate(text.splitlines(), start=1):
            for pattern in hdd_patterns:
                if pattern in line:
                    hdd_refs.append({"file": rel, "line": f"{idx}:{line.strip()[:100]}", "pattern": pattern})

    lines.append(f"HDD path references found: {len(hdd_refs)}")
    for ref in hdd_refs[:20]:
        lines.append(f"  {ref['file']}: {ref['line']}")

    ssd_refs: list[str] = []
    for path in _iter_py_files(include_tests=True):
        text = _read_text(path)
        rel = _rel(path)
        for idx, line in enumerate(text.splitlines(), start=1):
            if any(pattern in line for pattern in ssd_indicators):
                ssd_refs.append(f"{rel}:{idx}:{line.strip()[:90]}")

    lines.append("")
    lines.append(f"SSD path references: {len(ssd_refs)}")
    for ref in ssd_refs[:10]:
        lines.append(f"  {ref}")

    data_sizes: dict[str, dict[str, float | int]] = {}
    for directory in ["data", "training/features_safetensors", "checkpoints"]:
        path = ROOT / directory
        if path.exists():
            total = 0
            count = 0
            for item in path.rglob("*"):
                if item.is_file():
                    count += 1
                    try:
                        total += item.stat().st_size
                    except OSError:
                        continue
            data_sizes[directory] = {"bytes": total, "files": count, "mb": round(total / 1024 / 1024, 1)}
            lines.append("")
            lines.append(f"{directory}/: {count} files, {total / 1024 / 1024:.1f}MB")

    (REPORT_DIR / "ssd_migration.json").write_text(
        json.dumps({"hdd_refs": hdd_refs, "ssd_refs": len(ssd_refs), "data_sizes": data_sizes}, indent=2),
        encoding="utf-8",
    )
    _write_text_report("scan_g.txt", lines)


def main() -> None:
    os.chdir(ROOT)
    scan_a()
    scan_b()
    scan_c()
    scan_d()
    scan_e()
    scan_f()
    scan_g()
    print("Phase 0 scan reports written to report/phase0_scan")


if __name__ == "__main__":
    main()
