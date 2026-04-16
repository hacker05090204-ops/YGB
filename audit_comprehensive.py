#!/usr/bin/env python3
"""Comprehensive YBG Codebase Reality Audit"""
import os
import sys
import time
import importlib
import traceback
from pathlib import Path
from collections import defaultdict
import json

# Set environment
os.environ.update({
    'YGB_USE_MOE': 'true',
    'YGB_ENV': 'development',
    'JWT_SECRET': 'audit-jwt-secret-32chars-minimum!!',
    'YGB_VIDEO_JWT_SECRET': 'audit-video-jwt-32chars-minimum!!',
    'YGB_LEDGER_KEY': 'audit-ledger-key-development-32c!!',
    'YGB_REQUIRE_ENCRYPTION': 'false',
})

audit_results = {
    'import_tests': {},
    'wiring_checks': {},
    'functional_tests': {},
    'critical_findings': [],
}

print('='*70)
print('YBG COMPLETE CODEBASE REALITY AUDIT')
print('='*70)
print()

# ============================================================================
# PHASE 3: LIVE IMPORT TESTING
# ============================================================================
print('='*70)
print('PHASE 3: LIVE IMPORT TESTING')
print('='*70)

MODULES_TO_TEST = [
    # Core training
    ('training_controller', 'Training controller'),
    ('backend.training.incremental_trainer', 'Incremental trainer'),
    ('backend.training.auto_train_controller', 'Auto train controller'),
    ('backend.training.safetensors_store', 'Safetensors store'),
    ('backend.training.data_purity', 'Data purity enforcer'),
    ('backend.training.rl_feedback', 'RL feedback'),
    ('backend.training.adaptive_learner', 'Adaptive learner'),
    ('backend.training.training_optimizer', 'Training optimizer'),
    ('backend.training.class_balancer', 'Class balancer'),
    ('backend.training.metrics_tracker', 'Metrics tracker'),
    ('backend.training.compression_engine', 'Compression engine'),
    ('backend.training.deep_rl_agent', 'Deep RL agent'),
    # MoE
    ('impl_v1.phase49.moe', 'MoE architecture'),
    # Ingestion
    ('backend.ingestion.autograbber', 'Autograbber'),
    ('backend.ingestion.industrial_autograbber', 'Industrial autograbber'),
    ('backend.ingestion.normalizer', 'Normalizer'),
    ('backend.ingestion.dedup', 'Dedup store'),
    ('backend.ingestion.scrapers.nvd_scraper', 'NVD scraper'),
    ('backend.ingestion.scrapers.cisa_scraper', 'CISA scraper'),
    ('backend.ingestion.scrapers.osv_scraper', 'OSV scraper'),
    ('backend.ingestion.scrapers.github_advisory_scraper', 'GitHub advisory scraper'),
    ('backend.ingestion.scrapers.exploit_db_scraper', 'ExploitDB scraper'),
    ('backend.ingestion.scrapers.vendor_advisory_scraper', 'Vendor advisory scraper'),
    ('backend.ingestion.scrapers.snyk_scraper', 'Snyk scraper'),
    ('backend.ingestion.scrapers.vulnrichment_scraper', 'VulnRichment scraper'),
    ('backend.ingestion.parallel_autograbber', 'Parallel autograbber'),
    # API
    ('backend.api.system_status', 'System status'),
    ('backend.api.runtime_api', 'Runtime API'),
    ('backend.api.report_generator', 'Report generator'),
    # Sync
    ('backend.sync.sync_engine', 'Sync engine'),
    ('backend.sync.peer_transport', 'Peer transport'),
    # Auth/Governance
    ('backend.auth.auth_guard', 'Auth guard'),
    ('backend.governance.authority_lock', 'Authority lock'),
    ('backend.governance.approval_ledger', 'Approval ledger'),
    # Tasks
    ('backend.tasks.industrial_agent', 'Industrial agent'),
    # Assistant
    ('backend.assistant.voice_runtime', 'Voice runtime'),
    ('backend.assistant.query_router', 'Query router'),
    # Reporting
    ('backend.reporting.report_engine', 'Report engine'),
    ('backend.evidence.video_recorder', 'Video recorder'),
    # Scripts
    ('scripts.expert_task_queue', 'Expert task queue'),
    ('scripts.device_manager', 'Device manager'),
    # Distributed
    ('backend.distributed.expert_distributor', 'Expert distributor'),
    # Agent
    ('backend.agent.self_reflection', 'Self reflection'),
    # Testing
    ('backend.testing.field_registry', 'Field registry'),
    # Voice
    ('backend.voice.production_voice', 'Production voice'),
]

passed, failed, missing = [], [], []
for module_path, description in MODULES_TO_TEST:
    try:
        mod = importlib.import_module(module_path)
        passed.append((description, module_path))
        audit_results['import_tests'][module_path] = 'PASS'
        print(f'  ✓ PASS    {description}')
    except ModuleNotFoundError as e:
        missing.append((description, module_path, str(e)))
        audit_results['import_tests'][module_path] = f'MISSING: {str(e)[:60]}'
        print(f'  ✗ MISSING {description}')
        print(f'            {str(e)[:80]}')
    except ImportError as e:
        failed.append((description, module_path, str(e)))
        audit_results['import_tests'][module_path] = f'IMPORT_ERROR: {str(e)[:60]}'
        print(f'  ✗ IMPORT  {description}')
        print(f'            {str(e)[:80]}')
    except Exception as e:
        failed.append((description, module_path, str(e)))
        audit_results['import_tests'][module_path] = f'RUNTIME_ERROR: {str(e)[:60]}'
        print(f'  ✗ RUNTIME {description}')
        print(f'            {type(e).__name__}: {str(e)[:80]}')

print()
print(f'PASSED:  {len(passed)}/{len(MODULES_TO_TEST)}')
print(f'MISSING: {len(missing)}/{len(MODULES_TO_TEST)}')
print(f'FAILED:  {len(failed)}/{len(MODULES_TO_TEST)}')
import_score = len(passed) / len(MODULES_TO_TEST) * 100
print(f'Import health: {import_score:.0f}%')
print()

# ============================================================================
# PHASE 4: FUNCTIONAL TESTING (Key Components)
# ============================================================================
print('='*70)
print('PHASE 4: FUNCTIONAL TESTING')
print('='*70)

def test_result(name, fn):
    """Run a test and record result"""
    t = time.perf_counter()
    try:
        fn()
        ms = (time.perf_counter() - t) * 1000
        audit_results['functional_tests'][name] = {'status': 'PASS', 'ms': round(ms, 1)}
        print(f'  ✓ PASS  {name} ({ms:.0f}ms)')
        return True
    except AssertionError as e:
        ms = (time.perf_counter() - t) * 1000
        audit_results['functional_tests'][name] = {'status': 'FAIL', 'error': str(e), 'ms': round(ms, 1)}
        print(f'  ✗ FAIL  {name}')
        print(f'          {str(e)[:100]}')
        return False
    except Exception as e:
        ms = (time.perf_counter() - t) * 1000
        audit_results['functional_tests'][name] = {'status': 'ERROR', 'error': f'{type(e).__name__}: {str(e)}', 'ms': round(ms, 1)}
        print(f'  ✗ ERROR {name}')
        print(f'          {type(e).__name__}: {str(e)[:100]}')
        return False

# Test MoE Architecture
print()
print('--- MoE Architecture ---')

def test_moe_import():
    from impl_v1.phase49.moe import MoEClassifier
    m = MoEClassifier()
    assert m is not None

def test_moe_params():
    from impl_v1.phase49.moe import MoEClassifier
    m = MoEClassifier()
    params = sum(p.numel() for p in m.parameters())
    assert params > 100_000_000, f'Only {params:,} params — still legacy model'

def test_moe_forward():
    import torch
    from impl_v1.phase49.moe import MoEClassifier
    m = MoEClassifier()
    x = torch.randn(4, 267)
    out = m(x)
    assert out.shape == (4, 5), f'Wrong output shape: {out.shape}'

def test_moe_experts():
    from impl_v1.phase49.moe import MoEClassifier
    m = MoEClassifier()
    n = m.n_experts if hasattr(m, 'n_experts') else len(m.experts) if hasattr(m, 'experts') else 0
    assert n == 23, f'Expected 23 experts, got {n}'

test_result('MoE: importable', test_moe_import)
test_result('MoE: param count > 100M', test_moe_params)
test_result('MoE: forward pass works', test_moe_forward)
test_result('MoE: 23 experts exist', test_moe_experts)

# Test Data Purity
print()
print('--- Data Purity ---')

def test_purity_rejects_short():
    from backend.training.data_purity import DataPurityEnforcer
    sample = {
        'cve_id': 'CVE-2024-0001',
        'description': 'too short',
        'severity': 'HIGH',
        'source_name': 'nvd_web',
        'quality_score': 0.8
    }
    r = DataPurityEnforcer.enforce(sample)
    assert not r.accepted, 'Short description should be rejected'

def test_purity_accepts_good():
    from backend.training.data_purity import DataPurityEnforcer
    sample = {
        'cve_id': 'CVE-2024-99999',
        'severity': 'HIGH',
        'source_name': 'nvd_web',
        'quality_score': 0.8,
        'description': 'A remote code execution vulnerability in the authentication component allows unauthenticated attackers to execute arbitrary code via crafted HTTP requests. This affects version 1.0 through 2.5.'
    }
    r = DataPurityEnforcer.enforce(sample)
    assert r.accepted, f'Good sample rejected: {r.rejection_reason}'

test_result('DataPurity: rejects short desc', test_purity_rejects_short)
test_result('DataPurity: accepts good sample', test_purity_accepts_good)

# Test Expert Task Queue
print()
print('--- Expert Task Queue ---')

def test_queue_has_23():
    from scripts.expert_task_queue import ExpertTaskQueue
    q = ExpertTaskQueue()
    statuses = q.get_status()
    assert len(statuses) == 23, f'Expected 23, got {len(statuses)}'

test_result('ExpertQueue: 23 experts', test_queue_has_23)

# Test Authority Lock
print()
print('--- Authority Lock ---')

def test_authority_lock():
    from backend.governance.authority_lock import AuthorityLock
    r = AuthorityLock.verify_all_locked()
    assert r.get('all_locked') == True, f'NOT LOCKED: {r}'

test_result('Authority lock: all_locked=True', test_authority_lock)

# Test Field Registry
print()
print('--- Field Registry ---')

def test_80_plus_fields():
    from backend.testing.field_registry import ALL_FIELDS, FIELD_COUNT
    assert FIELD_COUNT >= 80, f'Only {FIELD_COUNT} fields — need 80+'

def test_all_experts_covered():
    from backend.testing.field_registry import ALL_FIELDS
    experts_covered = set(f.expert_id for f in ALL_FIELDS)
    for i in range(23):
        assert i in experts_covered, f'Expert {i} has no fields assigned'

test_result('FieldRegistry: 80+ fields defined', test_80_plus_fields)
test_result('FieldRegistry: all 23 experts have fields', test_all_experts_covered)

# ============================================================================
# SUMMARY
# ============================================================================
print()
print('='*70)
print('AUDIT SUMMARY')
print('='*70)

passed_tests = sum(1 for v in audit_results['functional_tests'].values() if v['status'] == 'PASS')
total_tests = len(audit_results['functional_tests'])
functional_score = (passed_tests / total_tests * 100) if total_tests > 0 else 0

print(f'Import Tests:      {len(passed)}/{len(MODULES_TO_TEST)} passed ({import_score:.0f}%)')
print(f'Functional Tests:  {passed_tests}/{total_tests} passed ({functional_score:.0f}%)')
print()

# Save results
with open('audit_results.json', 'w') as f:
    json.dump(audit_results, f, indent=2)
print('Full results saved to: audit_results.json')
