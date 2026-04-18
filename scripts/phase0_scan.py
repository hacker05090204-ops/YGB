from __future__ import annotations

import ast
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "report" / "phase0_scan"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def iter_py_files(base: Path = ROOT) -> Iterable[Path]:
    excluded_parts = {
        ".git",
        "__pycache__",
        "node_modules",
        "dist",
        ".next",
        ".venv",
        "venv",
    }
    for path in base.rglob("*.py"):
        if any(part in excluded_parts for part in path.parts):
            continue
        yield path


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def heading(title: str) -> str:
    return f"{'=' * 70}\n{title}\n{'=' * 70}\n"


def format_lines(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"


def print_console(text: str) -> None:
    safe = text.encode("ascii", errors="replace").decode("ascii")
    print(safe)


def scan_a() -> tuple[list[dict], str]:
    items: list[dict] = []
    out: list[str] = [heading("SCAN A: PLANNED BUT NOT IMPLEMENTED").rstrip()]

    for path in iter_py_files():
        content = safe_read(path)
        relpath = rel(path)

        for line_no, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if "raise NotImplementedError" in line:
                items.append(
                    {
                        "type": "NotImplementedError",
                        "file": relpath,
                        "line": line_no,
                        "location": f"{relpath}:{line_no}:{line.strip()[:200]}",
                    }
                )
            if (
                relpath.startswith("tests/")
                or "/tests/" in relpath
                or path.name.startswith("test_")
            ):
                continue
            todo_patterns = ("# TODO", "# FIXME", "# NOT IMPLEMENTED")
            if any(token in line for token in todo_patterns):
                items.append(
                    {
                        "type": "TODO",
                        "file": relpath,
                        "line": line_no,
                        "location": f"{relpath}:{line_no}:{line.strip()[:200]}",
                    }
                )

        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.body:
                continue
            body = node.body
            first = body[0]
            remaining = body[1:] if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) and isinstance(first.value.value, str) else body
            if len(remaining) == 1:
                only = remaining[0]
                empty = False
                if isinstance(only, ast.Pass):
                    empty = True
                elif isinstance(only, ast.Expr) and isinstance(getattr(only, "value", None), ast.Constant) and only.value.value == Ellipsis:
                    empty = True
                if empty:
                    items.append(
                        {
                            "type": "empty_function",
                            "file": relpath,
                            "line": node.lineno,
                            "location": f"{relpath}:{node.lineno}:def {node.name}(...)",
                        }
                    )

    for child in ROOT.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        if child.name in {"node_modules", "dist", ".next", "__pycache__"}:
            continue
        py_files = [p for p in child.rglob("*.py") if ".git" not in p.parts and "__pycache__" not in p.parts]
        if not py_files:
            items.append(
                {
                    "type": "empty_directory",
                    "file": rel(child),
                    "line": 0,
                    "location": rel(child),
                }
            )

    out.append(f"Found {len(items)} planned-but-not-implemented items")
    for item in items[:50]:
        out.append(f"  [{item['type']}] {item['location'][:150]}")
    out.append("")
    out.append("Full list: report/phase0_scan/planned_not_implemented.json")
    return items, format_lines(out)


def scan_b() -> tuple[list[dict], str]:
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
            r"accuracy = 1\.0",
            r"f1 = 0\.9",
            r"val_f1 = 0\.8",
            r"return True  # always",
            r"return 1\.0  # fake",
            r"return \[\]  # TODO",
            r"return \{\}  # placeholder",
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
            r"skip_verification = True",
            r"bypass_auth",
            r"TEMP_AUTH_BYPASS",
            r"skip_validation = True",
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

    violations: list[dict] = []
    out: list[str] = [heading("SCAN B: MOCK/FAKE DATA HUNT").rstrip()]

    for path in iter_py_files():
        relpath = rel(path)
        if relpath.startswith("tests/") or "/tests/" in relpath or path.name.startswith("test_"):
            continue
        content = safe_read(path)
        for severity, severity_patterns in patterns.items():
            for pattern in severity_patterns:
                regex = re.compile(pattern)
                for line_no, line in enumerate(content.splitlines(), start=1):
                    if regex.search(line):
                        violations.append(
                            {
                                "severity": severity,
                                "file": relpath,
                                "pattern": pattern,
                                "line": f"{line_no}:{line.strip()[:200]}",
                            }
                        )

    critical = [v for v in violations if "CRITICAL" in v["severity"]]
    high = [v for v in violations if "HIGH" in v["severity"]]
    out.append(f"CRITICAL violations: {len(critical)}")
    out.append(f"HIGH violations: {len(high)}")
    out.append("")
    out.append("CRITICAL (must fix):")
    for violation in critical[:30]:
        out.append(f"  [{violation['file']}] {violation['line']}")
    return violations, format_lines(out)


WIRING_MATRIX = [
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
    ("NonceDB_persist", "HUMANOID_HUNTER/", "sqlite|redis", "CRITICAL"),
    ("CompressionRealBytes", "backend/training/compression_engine.py", "stat().st_size", "HIGH"),
    ("VulnDetectionEngine", "backend/intelligence/", "vulnerability_detector", "CRITICAL"),
    ("PayloadGenerator", "backend/intelligence/", "payload_generator", "HIGH"),
    ("ScannerEngine", "backend/scanner/", "scanner", "HIGH"),
]


def scan_c() -> tuple[dict, str]:
    results = {"wired": [], "not_wired": [], "file_missing": []}
    out: list[str] = [heading("SCAN C: WIRING STATUS").rstrip()]

    for desc, filepath, pattern, criticality in WIRING_MATRIX:
        target = ROOT / filepath
        found = False
        if target.is_dir():
            compiled = re.compile(pattern)
            for py_file in target.rglob("*.py"):
                if compiled.search(safe_read(py_file)):
                    found = True
                    break
        elif target.exists():
            found = pattern in safe_read(target)
        else:
            results["file_missing"].append({"desc": desc, "path": filepath, "criticality": criticality})
            out.append(f"  FILE MISSING  [{criticality}] {desc}: {filepath}")
            continue

        if found:
            results["wired"].append({"desc": desc, "path": filepath})
        else:
            results["not_wired"].append(
                {"desc": desc, "path": filepath, "pattern": pattern, "criticality": criticality}
            )
            out.append(f"  NOT WIRED     [{criticality}] {desc}: \"{pattern}\" missing in {filepath}")

    out.append("")
    out.append(f"WIRED:        {len(results['wired'])}/{len(WIRING_MATRIX)}")
    out.append(f"NOT_WIRED:    {len(results['not_wired'])}/{len(WIRING_MATRIX)}")
    out.append(f"FILE_MISSING: {len(results['file_missing'])}/{len(WIRING_MATRIX)}")
    return results, format_lines(out)


def scan_d() -> tuple[dict, str]:
    out: list[str] = [heading("SCAN D: GPU UTILIZATION").rstrip()]
    info: dict = {"has_gpu": False, "gpu_files": [], "cpu_hits": []}
    try:
        import torch  # type: ignore

        has_gpu = torch.cuda.is_available()
        info["has_gpu"] = has_gpu
        if has_gpu:
            props = torch.cuda.get_device_properties(0)
            info["gpu_name"] = props.name
            info["gpu_vram_gb"] = round(props.total_memory / 1e9, 1)
            info["gpu_count"] = torch.cuda.device_count()
            info["cuda_version"] = torch.version.cuda
            out.append(
                f"GPU: {props.name} | VRAM: {props.total_memory / 1e9:.1f}GB | CUDA: {torch.version.cuda}"
            )
            out.append(f"GPU count: {torch.cuda.device_count()}")
        else:
            out.append("WARNING: No GPU available — Colab/Lightning required for training")
    except ImportError:
        out.append("ERROR: torch not installed")

    gpu_required = [
        "training_controller.py",
        "backend/training/incremental_trainer.py",
        "backend/training/auto_train_controller.py",
        "impl_v1/phase49/moe/__init__.py",
        "impl_v1/phase49/moe/expert.py",
        "backend/ingestion/industrial_autograbber.py",
    ]
    indicators = [".to(device)", ".cuda()", "torch.cuda", "device = ", "GradScaler", "autocast"]

    out.append("")
    out.append("--- GPU Usage in Critical Files ---")
    for filepath in gpu_required:
        path = ROOT / filepath
        if not path.exists():
            out.append(f"  MISSING  {filepath}")
            info["gpu_files"].append({"path": filepath, "status": "MISSING", "found": []})
            continue
        content = safe_read(path)
        found = [ind for ind in indicators if ind in content]
        status = "GPU OK" if len(found) >= 3 else "GPU WEAK" if found else "NO GPU"
        detail = found if found else []
        if status == "GPU OK":
            out.append(f"  GPU OK   {filepath}: {detail}")
        elif status == "GPU WEAK":
            out.append(f"  GPU WEAK {filepath}: only {detail} — needs more GPU ops")
        else:
            out.append(f"  NO GPU   {filepath} — running on CPU only!")
        info["gpu_files"].append({"path": filepath, "status": status, "found": detail})

    cpu_regex = re.compile(r"device\s*=\s*.*cpu|device.*cpu.*fallback")
    cpu_hits: list[str] = []
    for filepath in [ROOT / "backend/training", ROOT / "training_controller.py"]:
        if filepath.is_dir():
            for py_file in filepath.rglob("*.py"):
                for line_no, line in enumerate(safe_read(py_file).splitlines(), start=1):
                    if cpu_regex.search(line):
                        cpu_hits.append(f"{rel(py_file)}:{line_no}:{line.strip()[:200]}")
        elif filepath.exists():
            for line_no, line in enumerate(safe_read(filepath).splitlines(), start=1):
                if cpu_regex.search(line):
                    cpu_hits.append(f"{rel(filepath)}:{line_no}:{line.strip()[:200]}")
    info["cpu_hits"] = cpu_hits
    out.append("")
    out.append(f"CPU-only patterns: {len(cpu_hits)} (these should GPU-first)")
    for hit in cpu_hits[:5]:
        out.append(f"  {hit[:150]}")
    return info, format_lines(out)


def scan_e() -> tuple[dict, str]:
    out: list[str] = [heading("SCAN E: SCRAPER URL HEALTH").rstrip()]
    results: dict = {}
    live_count = 0
    try:
        import requests  # type: ignore
    except ImportError as exc:
        results = {"error": f"requests missing: {exc}"}
        out.append(results["error"])
        return results, format_lines(out)

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
            if response.status_code == 200:
                live_count += 1
                results[name] = {"status": "LIVE", "code": 200, "ms": elapsed_ms}
                out.append(f"  LIVE  {name}: {elapsed_ms}ms")
            elif response.status_code == 304:
                live_count += 1
                results[name] = {"status": "NO_DELTA", "code": 304, "ms": elapsed_ms}
                out.append(f"  304   {name}: no delta")
            elif response.status_code == 400:
                results[name] = {"status": "FIX_URL", "code": 400, "url": request_spec["url"]}
                out.append(f"  400   {name}: URL format wrong — FIX SCRAPER")
            elif response.status_code == 404:
                results[name] = {"status": "MOVED", "code": 404, "url": request_spec["url"]}
                out.append(f"  404   {name}: endpoint moved — UPDATE URL")
            elif response.status_code == 410:
                results[name] = {"status": "GONE", "code": 410, "url": request_spec["url"]}
                out.append(f"  410   {name}: endpoint gone — FIND ALTERNATIVE")
            else:
                results[name] = {"status": f"HTTP_{response.status_code}", "code": response.status_code}
                out.append(f"  {response.status_code}  {name}: unexpected")
        except requests.Timeout:
            results[name] = {"status": "TIMEOUT"}
            out.append(f"  TIME  {name}: timeout")
        except Exception as exc:  # explicit capture for scan report
            results[name] = {"status": "ERROR", "error": str(exc)[:200]}
            out.append(f"  ERR   {name}: {str(exc)[:120]}")
        time.sleep(1)

    broken = [key for key, value in results.items() if value.get("status") not in {"LIVE", "NO_DELTA"}]
    out.append("")
    out.append(f"LIVE: {live_count}/{len(urls)} sources reachable")
    out.append(f"BROKEN (need URL fix): {broken}")
    return results, format_lines(out)


def scan_f() -> tuple[dict, str]:
    out: list[str] = [heading("SCAN F: CAPABILITY GAPS").rstrip()]
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

    search_roots = [
        ROOT / "backend",
        ROOT / "api",
        ROOT / "impl_v1",
        ROOT / "HUMANOID_HUNTER",
        ROOT / "training_controller.py",
    ]
    py_candidates: list[Path] = []
    for root in search_roots:
        if root.is_dir():
            py_candidates.extend([p for p in root.rglob("*.py") if "__pycache__" not in p.parts])
        elif root.exists():
            py_candidates.append(root)

    results: dict = {}
    for capability, patterns in capabilities.items():
        found_in: list[str] = []
        for file_path in py_candidates:
            content = safe_read(file_path)
            if any(pattern in content for pattern in patterns):
                if file_path.name.startswith("test_"):
                    continue
                found_in.append(rel(file_path))
        unique = sorted(set(found_in))
        status = "IMPLEMENTED" if unique else "MISSING"
        results[capability] = {"status": status, "files": unique[:3]}
        icon = "✓" if status == "IMPLEMENTED" else "✗"
        out.append(f"  {icon} {capability}: {status}")
        for filename in unique[:2]:
            out.append(f"    → {filename}")

    missing = [key for key, value in results.items() if value["status"] == "MISSING"]
    out.append("")
    out.append(f"MISSING CAPABILITIES: {len(missing)}/{len(capabilities)}")
    out.append("These must be implemented:")
    for capability in missing:
        out.append(f"  ❌ {capability}")
    return results, format_lines(out)


def scan_g() -> tuple[dict, str]:
    out: list[str] = [heading("SCAN G: SSD MIGRATION STATUS").rstrip()]
    hdd_patterns = [r"D:\\", r"/hdd/", r"/mnt/hdd", r"hdd_drive", r"\.tmp_hdd", r"HDD_PATH", r"hdd_path", r"D:/ygb_data"]
    hdd_refs: list[dict] = []
    for path in iter_py_files():
        content = safe_read(path)
        for pattern in hdd_patterns:
            regex = re.compile(pattern)
            for line_no, line in enumerate(content.splitlines(), start=1):
                if regex.search(line):
                    hdd_refs.append(
                        {
                            "file": rel(path),
                            "line": f"{line_no}:{line.strip()[:200]}",
                            "pattern": pattern,
                        }
                    )

    out.append(f"HDD path references found: {len(hdd_refs)}")
    for ref_item in hdd_refs[:20]:
        out.append(f"  {ref_item['file']}: {ref_item['line']}")

    ssd_indicators = ["ssd", "SSD", "/fast/", "/nvme/", "training/features_safetensors"]
    ssd_refs: list[str] = []
    for path in iter_py_files():
        content = safe_read(path)
        for line_no, line in enumerate(content.splitlines(), start=1):
            if any(token in line for token in ssd_indicators):
                ssd_refs.append(f"{rel(path)}:{line_no}:{line.strip()[:200]}")

    out.append("")
    out.append(f"SSD path references: {len(ssd_refs)}")
    for item in ssd_refs[:10]:
        out.append(f"  {item[:150]}")

    data_sizes: dict = {}
    for dirname in ["data", "training/features_safetensors", "checkpoints"]:
        path = ROOT / dirname
        if not path.exists():
            continue
        total_bytes = 0
        file_count = 0
        for file_path in path.rglob("*"):
            if file_path.is_file():
                file_count += 1
                total_bytes += file_path.stat().st_size
        data_sizes[dirname] = {
            "bytes": total_bytes,
            "files": file_count,
            "mb": round(total_bytes / 1024 / 1024, 1),
        }
        out.append("")
        out.append(f"{dirname}/: {file_count} files, {total_bytes / 1024 / 1024:.1f}MB")

    payload = {"hdd_refs": hdd_refs, "ssd_refs": len(ssd_refs), "data_sizes": data_sizes}
    return payload, format_lines(out)


def main() -> int:
    scan_a_payload, scan_a_text = scan_a()
    write_json(REPORT_DIR / "planned_not_implemented.json", scan_a_payload)
    write_text(REPORT_DIR / "scan_a.txt", scan_a_text)
    print_console(scan_a_text)

    scan_b_payload, scan_b_text = scan_b()
    write_json(REPORT_DIR / "mock_violations.json", scan_b_payload)
    write_text(REPORT_DIR / "scan_b.txt", scan_b_text)
    print_console(scan_b_text)

    scan_c_payload, scan_c_text = scan_c()
    write_json(REPORT_DIR / "wiring_status.json", scan_c_payload)
    write_text(REPORT_DIR / "scan_c.txt", scan_c_text)
    print_console(scan_c_text)

    scan_d_payload, scan_d_text = scan_d()
    write_json(REPORT_DIR / "gpu_utilization.json", scan_d_payload)
    write_text(REPORT_DIR / "scan_d.txt", scan_d_text)
    print_console(scan_d_text)

    scan_e_payload, scan_e_text = scan_e()
    write_json(REPORT_DIR / "scraper_health.json", scan_e_payload)
    write_text(REPORT_DIR / "scan_e.txt", scan_e_text)
    print_console(scan_e_text)

    scan_f_payload, scan_f_text = scan_f()
    write_json(REPORT_DIR / "capability_gaps.json", scan_f_payload)
    write_text(REPORT_DIR / "scan_f.txt", scan_f_text)
    print_console(scan_f_text)

    scan_g_payload, scan_g_text = scan_g()
    write_json(REPORT_DIR / "ssd_migration.json", scan_g_payload)
    write_text(REPORT_DIR / "scan_g.txt", scan_g_text)
    print_console(scan_g_text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
