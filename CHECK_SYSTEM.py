#!/usr/bin/env python3
"""
YBG System Health Check
Run this to verify system status before training.
"""

import os
import sys
from pathlib import Path

def print_header(text):
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70)

def check_mark(condition):
    return "✅" if condition else "❌"

def main():
    print_header("YBG SYSTEM HEALTH CHECK")
    
    issues = []
    warnings = []
    
    # 1. Check MoE implementation
    print("\n1. MoE Architecture")
    moe_path = Path("impl_v1/phase49/moe/__init__.py")
    moe_exists = moe_path.exists()
    print(f"   {check_mark(moe_exists)} MoE module: {moe_path}")
    
    if moe_exists:
        try:
            from impl_v1.phase49.moe import MoEClassifier, EXPERT_FIELDS
            print(f"   ✅ MoEClassifier importable")
            print(f"   ✅ {len(EXPERT_FIELDS)} expert fields defined")
        except Exception as e:
            print(f"   ❌ Import failed: {e}")
            issues.append("MoE import failed")
    else:
        issues.append("MoE module missing")
    
    # 2. Check training controller
    print("\n2. Training Controller")
    tc_path = Path("training_controller.py")
    tc_exists = tc_path.exists()
    print(f"   {check_mark(tc_exists)} training_controller.py exists")
    
    if tc_exists:
        try:
            content = tc_path.read_text(encoding='utf-8', errors='ignore')
            has_moe_ref = 'MoEClassifier' in content
            has_build_fn = '_build_configured_model' in content
            print(f"   {check_mark(has_moe_ref)} MoE references found")
            print(f"   {check_mark(has_build_fn)} _build_configured_model found")
        except Exception as e:
            print(f"   ⚠️  Could not read file: {e}")
            warnings.append("Could not verify training_controller")
    
    # 3. Check scrapers
    print("\n3. Data Pipeline")
    scraper_dir = Path("backend/ingestion/scrapers")
    if scraper_dir.exists():
        scrapers = [f.stem for f in scraper_dir.glob("*.py") 
                   if f.stem not in ('__init__', 'base_scraper')]
        print(f"   ✅ {len(scrapers)} scrapers found:")
        for s in scrapers:
            print(f"      • {s}")
    else:
        print(f"   ❌ Scraper directory missing")
        issues.append("Scrapers missing")
    
    # 4. Check security
    print("\n4. Security")
    auth_path = Path("backend/auth/auth_guard.py")
    if auth_path.exists():
        try:
            content = auth_path.read_text(encoding='utf-8', errors='ignore')
            has_bypass = 'is_temporary_auth_bypass_enabled' in content
            has_prod_gate = 'YGB_ENV' in content and 'production' in content
            print(f"   {check_mark(has_bypass)} Auth bypass function exists")
            print(f"   {check_mark(has_prod_gate)} Production gate present")
        except Exception as e:
            print(f"   ⚠️  Could not verify: {e}")
            warnings.append("Could not verify auth security")
    else:
        print(f"   ⚠️  auth_guard.py not found")
        warnings.append("Auth guard missing")
    
    # 5. Check environment
    print("\n5. Environment")
    jwt_secret = os.getenv("JWT_SECRET", "")
    use_moe = os.getenv("YGB_USE_MOE", "true")
    env = os.getenv("YGB_ENV", "development")
    
    jwt_ok = len(jwt_secret) >= 32
    print(f"   {check_mark(jwt_ok)} JWT_SECRET: {'set (32+ chars)' if jwt_ok else 'NOT SET or too short'}")
    print(f"   ✅ YGB_USE_MOE: {use_moe}")
    print(f"   ✅ YGB_ENV: {env}")
    
    if not jwt_ok:
        issues.append("JWT_SECRET not set or too short (need 32+ chars)")
    
    # 6. Check device manager
    print("\n6. Device Manager")
    dm_path = Path("scripts/device_manager.py")
    dm_exists = dm_path.exists()
    print(f"   {check_mark(dm_exists)} device_manager.py: {'exists' if dm_exists else 'MISSING'}")
    
    if dm_exists:
        try:
            from scripts.device_manager import get_config
            cfg = get_config()
            print(f"   ✅ Device: {cfg.device_name}")
            print(f"   ✅ VRAM: {cfg.vram_gb:.1f}GB")
            print(f"   ✅ Batch size: {cfg.batch_size}")
            print(f"   ✅ Precision: {cfg.precision}")
        except Exception as e:
            print(f"   ⚠️  Could not get config: {e}")
            warnings.append("Device manager not functional")
    
    # 7. Check documentation
    print("\n7. Documentation")
    docs = {
        "SYSTEM_STATUS.md": "System status report",
        "QUICKSTART.md": "Quick start guide",
        "ORCHESTRATOR_SUMMARY.md": "Orchestration summary",
    }
    for doc, desc in docs.items():
        exists = Path(doc).exists()
        print(f"   {check_mark(exists)} {doc}: {desc}")
    
    # Summary
    print_header("SUMMARY")
    
    if issues:
        print("\n❌ CRITICAL ISSUES:")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")
    
    if warnings:
        print("\n⚠️  WARNINGS:")
        for i, warning in enumerate(warnings, 1):
            print(f"   {i}. {warning}")
    
    if not issues and not warnings:
        print("\n✅ ALL CHECKS PASSED!")
        print("\nSystem is ready for training.")
        print("\nNext steps:")
        print("  1. Review QUICKSTART.md for training examples")
        print("  2. Run: python scripts/device_manager.py")
        print("  3. Start training an expert")
    elif not issues:
        print("\n✅ NO CRITICAL ISSUES")
        print("⚠️  Some warnings present (see above)")
        print("\nSystem is operational but review warnings.")
    else:
        print("\n❌ CRITICAL ISSUES FOUND")
        print("\nFix the issues above before training.")
        return 1
    
    print("\n" + "="*70)
    return 0

if __name__ == "__main__":
    sys.exit(main())
