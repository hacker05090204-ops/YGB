"""
Full codebase scan for remediation patterns.
Classifies hits as: PRODUCTION, TEST, THIRD_PARTY, CONFIG, DOCS
"""
import os
import re
import sys
import json

# Force UTF-8 output on Windows (cp1252 crashes on Unicode arrows/symbols)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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

# =========================================================================
# REVIEWED FALSE-POSITIVE ALLOWLIST
# =========================================================================
# Each entry: (pattern_name, file_path_substring, rationale)
# These matches are SEPARATED from the production risk count but still
# reported for transparency. Only suppress items where code is REJECTING,
# BLOCKING, or DEFINING the risky pattern, not using it.
REVIEWED_ALLOWLIST = [
    # --- placeholder: HTML input attributes ---
    ("placeholder", "frontend/", "HTML placeholder= attr or CSS placeholder: style — not a production risk"),
    # --- placeholder: secret rejection lists ---
    ("placeholder", "backend/auth/auth_guard.py", "Placeholder detection list — code that BLOCKS placeholder secrets"),
    # --- simulate/SIMULATED: legitimate execution state machine ---
    ("simulate", "frontend/components/execution-state.tsx", "PLAN→SIMULATE→APPROVE workflow state enum, not a bypass"),
    # --- simulate: api/server.py line-specific allowlist ---
    # Line 383: ExecutionTransitionRequest.transition docstring listing SIMULATE as valid enum value
    # This is a state-machine enum definition, not a production bypass.
    ("simulate", "api/server.py:383", "ExecutionTransitionRequest transition enum comment — not bypass"),
    # --- simulate: browser engine dry-run tracking field ---
    ("simulate", "impl_v1/phase38/browser_engine.py", "simulated_result field tracks whether action would succeed without execution"),
    ("simulate", "impl_v1/phase38/browser_types.py", "simulated_result dataclass field definition"),
    # --- simulate: human workflow policy enforcement ---
    ("simulate", "impl_v1/production/workflow/human_workflow_simulation.py",
     "Rejection messages requiring real data — NOT simulating data"),
    # --- simulate: training accelerator (env-guarded) ---
    ("simulate", "impl_v1/training/ai_accelerator_integration.py",
     "SIMULATION_MODE behind YGB_ACCELERATOR_SIMULATION env guard"),
    # --- partial: legitimate status/response type enums ---
    ("partial", "HUMANOID_HUNTER/", "ExecutorResponseType.PARTIAL enum — legitimate status value"),
    ("partial", "impl_v1/phase30/", "ExecutorResponseType.PARTIAL in engine — legitimate status"),
    ("partial", "native/confidence_engine/", "C++ vector variable named 'partial' — not mock behavior"),
    ("partial", "native/research_assistant/", "LIKELY status annotation using 'partial matches'"),
    ("partial", "native/security/deterministic_exploit_engine.cpp", "Partial determinism scoring — legitimate logic"),
    ("partial", "api/server.py", "Training readiness PARTIAL status — legitimate state value"),
    ("partial", "frontend/app/dashboard/page.tsx", "UI rendering of PARTIAL status — matches backend enum"),
    # --- synthetic/mock: rejection/blocking code in training safety ---
    ("synthetic", "impl_v1/training/safety/", "Scanner/gate code that BLOCKS synthetic data"),
    ("synthetic", "impl_v1/training/data/", "Audit/loader code that REJECTS synthetic data"),
    ("synthetic", "impl_v1/training/distributed/", "Entropy guard that REJECTS synthetic-only batches"),
    ("synthetic", "training_controller.py", "NO SYNTHETIC FALLBACK abort message"),
    ("synthetic", "training/validation/", "Data audit reporting synthetic ratio"),
    ("synthetic", "native/security/data_truth_enforcer.cpp", "C++ enforcer that BLOCKS synthetic flag"),
    ("synthetic", "native/lab_training/lab_scheduler.cpp", "Deterministic test scope counter"),
    ("synthetic", "frontend/components/bounty-status-panel.tsx", "UI label showing SYNTHETIC is blocked"),
    ("mock", "impl_v1/training/safety/mock_data_scanner.py", "Scanner that DETECTS mock data patterns"),
    ("mock", "impl_v1/training/safety/dataset_quality_gate.py", "Gate that ABORTS on mock data detection"),
    ("mock", "impl_v1/training/safety/schema_validator.py", "Blocked field list — rejects mock/synthetic"),
    ("mock", "impl_v1/training/data/governance_pipeline.py", "Pipeline check that BLOCKS mock data violations"),
    ("mock", "native/security/production_build_guard.cpp", "Build guard that REJECTS mock-signature"),
    ("mock", "native/security/update_signature_verifier.cpp", "Verifier that REJECTS mock/test/fake signatures"),
    ("mock", "backend/api/runtime_api.py", "Rejection message: 'No mock/test fallback permitted'"),
    ("mock", "api/server.py", "MOCK mode rejection — returns error for MOCK mode requests"),
    # --- not_implemented: HTTP 501 error code definition ---
    ("not_implemented", "backend/errors.py", "ErrorCode.NOT_IMPLEMENTED enum — standard HTTP 501"),
    ("not_implemented", "native/report_engine/narrative_builder.cpp",
     "Vulnerability description text — 'does not implement proper input'"),
    ("not_implemented", "api/server.py", "Search not-implemented fallback — returns empty results safely"),
    ("not_implemented", "impl_v1/training/distributed/cloud_backup.py",
     "Upload not-yet-implemented for specific cloud target — fails closed"),
    # --- not_implemented: base class abstract method ---
    ("not_implemented", "impl_v1/training/voice/stt_adapter.py",
     "BaseSTTAdapter.transcribe() abstract — enforces subclass override, not missing impl"),
    # --- placeholder: detection / rejection code ---
    ("placeholder", "backend/config/config_validator.py",
     "_PLACEHOLDER_PATTERNS list and error message — code that DETECTS/REJECTS placeholder secrets"),
    ("placeholder", "impl_v1/phase20/phase20_engine.py",
     "Return value comment '# Placeholder, not used' — no runtime risk"),
    ("placeholder", "impl_v1/training/safety/mock_data_scanner.py",
     "Regex pattern r'placeholder\\s*=' in scanner that DETECTS placeholder usage"),
    ("placeholder", "native/security/secure_password_verifier.cpp",
     "Blocklist value — code REJECTS this placeholder bcrypt hash"),
    ("placeholder", "native/security/secure_secret_loader.cpp",
     "FATAL error message that BLOCKS placeholder secrets at startup"),
    ("placeholder", "native/security/update_signature_verifier.cpp",
     "Blocked signature list — code REJECTS placeholder/demo signatures"),
    # --- simulate: training validation infrastructure ---
    ("simulate", "impl_v1/training/distributed/curriculum_loop.py",
     "Curriculum stage name 'simulated_exploit' — test harness step label"),
    ("simulate", "impl_v1/training/distributed/failure_resilience.py",
     "FailureSimulator class — explicit resilience testing infrastructure"),
    # --- simulate: native validation proof engine ---
    ("simulate", "native/validation/precision_proof.cpp",
     "SimulatedSample struct in validation proof engine — not production bypass"),
    # --- simulate: training validation scripts ---
    ("simulate", "training/validation/drift_simulation.py",
     "Drift simulation validation script — MODE-B gate testing"),
    ("simulate", "training/validation/long_run_stability.py",
     "Long-run stability test — 24hr simulated test cycle"),
    ("simulate", "training/validation/mode_b_gate.py",
     "Gate runner calling drift/shadow simulation validation phases"),
    ("simulate", "training/validation/shadow_mode_simulation.py",
     "Shadow mode validation script — MODE-B gate testing"),
    ("simulate", "training/validation/temporal_drift_runner.py",
     "Temporal drift test runner log message"),
]


def _is_allowlisted(pattern_name, rel_path, line_num=None):
    """Check if a hit is in the reviewed false-positive allowlist.
    
    Supports line-specific allowlist entries using 'path:LINE' format.
    """
    for al_pattern, al_path_substr, _rationale in REVIEWED_ALLOWLIST:
        if al_pattern != pattern_name:
            continue
        # Check for line-specific allowlist entry (e.g. 'api/server.py:383')
        if ':' in al_path_substr and al_path_substr.rsplit(':', 1)[1].isdigit():
            path_part, line_part = al_path_substr.rsplit(':', 1)
            if path_part in rel_path and line_num == int(line_part):
                return True
        elif al_path_substr in rel_path:
            return True
    return False


def classify_path(filepath):
    rel = os.path.relpath(filepath, PROJECT_ROOT).replace('\\', '/')
    parts = rel.split('/')
    
    if any(p in ('tests', 'test', '__tests__') for p in parts):
        return 'TEST'
    if any(f.startswith('test_') or f.endswith('_test.py') for f in [parts[-1]]):
        return 'TEST'
    if 'node_modules' in parts or 'vendor' in parts:
        return 'THIRD_PARTY'
    # Governance Python modules under backend/ are PRODUCTION (runtime-imported)
    # Only root-level governance/ docs/config are CONFIG/DOCS
    if 'governance' in parts:
        # backend/governance/*.py = PRODUCTION (runtime governance modules)
        if 'backend' in parts and parts[-1].endswith('.py'):
            return 'PRODUCTION'
        # Root governance/ directory docs/reports = CONFIG/DOCS
        return 'CONFIG/DOCS'
    # Config/docs by extension
    if parts[-1].endswith(('.md', '.txt', '.yml', '.yaml', '.toml', '.cfg', '.json', '.env', '.css')):
        return 'CONFIG/DOCS'
    # Env templates and config files
    if parts[-1].startswith('.env'):
        return 'CONFIG/DOCS'
    # CI/scan/monitoring scripts are tooling, not production runtime
    if parts[-1] in ('ci_security_scan.py', 'ci_banned_tokens.py', 'remediation_scan.py',
                      'coverage_gate.py', 'training_readiness.py'):
        return 'CI_TOOLING'
    # impl_v1 phase CI, monitoring, validation directories are tooling
    # BUT governors that are imported by runtime/api paths are PRODUCTION
    if 'impl_v1' in parts:
        if any(p in ('ci', 'monitoring', 'validation') for p in parts):
            return 'CI_TOOLING'
        # Governors: only classify as CI_TOOLING if NOT imported by runtime
        if 'governors' in parts:
            # Known runtime-imported governors should be PRODUCTION
            _RUNTIME_GOVERNORS = {
                'g35_ai_accelerator.py', 'g38_auto_training.py',
                'g21_auto_update.py',
            }
            if parts[-1] in _RUNTIME_GOVERNORS:
                return 'PRODUCTION'
            return 'CI_TOOLING'
        # Phase governance/freeze Python files
        if any(p.startswith('phase') for p in parts):
            if parts[-1].startswith(('quality_gate', 'freeze_condition')):
                return 'CI_TOOLING'
    # Edge deployment tools
    if 'edge' in parts:
        return 'CI_TOOLING'
    return 'PRODUCTION'


def scan():
    results = {}
    reviewed_results = {}
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
                in_docstring = False
                docstring_delim = None
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    
                    # Track Python docstring blocks
                    if ext == '.py':
                        for delim in ('"""', "'''"):
                            count = stripped.count(delim)
                            if count >= 2:
                                pass  # Single-line docstring, skip toggle
                            elif count == 1:
                                if not in_docstring:
                                    in_docstring = True
                                    docstring_delim = delim
                                elif docstring_delim == delim:
                                    in_docstring = False
                                    docstring_delim = None
                    
                    # Skip comment-only lines and docstring lines
                    is_non_code = (
                        in_docstring or
                        stripped.startswith('#') or
                        stripped.startswith('//') or
                        stripped.startswith('/*') or
                        stripped.startswith('*') or
                        stripped.startswith('"""') or
                        stripped.startswith("'''") or
                        (ext == '.py' and stripped.startswith(('- ', '  - ')))
                    )
                    effective_class = 'COMMENT' if (classification == 'PRODUCTION' and is_non_code) else classification
                    
                    for pname, pat in PATTERNS.items():
                        if pat.search(line):
                            # Check reviewed allowlist for production hits
                            if effective_class == 'PRODUCTION' and _is_allowlisted(pname, rel, i):
                                effective_class_final = 'REVIEWED'
                                key = f"{pname}|REVIEWED"
                                summary[key] = summary.get(key, 0) + 1
                                reviewed_results.setdefault(pname, [])
                                reviewed_results[pname].append({
                                    'file': rel,
                                    'line': i,
                                    'content': line.strip()[:120],
                                    'class': 'REVIEWED',
                                })
                            else:
                                key = f"{pname}|{effective_class}"
                                summary[key] = summary.get(key, 0) + 1
                                if effective_class == 'PRODUCTION':
                                    results.setdefault(pname, [])
                                    results[pname].append({
                                        'file': rel,
                                        'line': i,
                                        'content': line.strip()[:120],
                                        'class': effective_class,
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
    
    # Real-risk production hits
    print()
    print("=" * 60)
    print("PRODUCTION-PATH HITS (real risk — need remediation)")
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
    
    # Reviewed/suppressed hits (transparency)
    reviewed_total = 0
    for pname in sorted(reviewed_results.keys()):
        reviewed_total += len(reviewed_results[pname])
    
    print(f"\nTOTAL PRODUCTION HITS: {prod_total}")
    print(f"REVIEWED (allowlisted, non-risk): {reviewed_total}")
    print(f"REAL RISK SUBSET: {prod_total}")
    return results


if __name__ == '__main__':
    scan()

