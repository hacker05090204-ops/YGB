# Phase 0B Silent Handler Inventory

- Total remaining hits: 22
- Production hits: 5
- Tests-only hits: 17
- training_controller.py remaining hits: 0
- Raw inventory JSON: .tmp_hdd_drive/phase0b_silent_handler_inventory.json
- Summary JSON: .tmp_hdd_drive/phase0b_silent_handler_summary.json

## File-by-file counts
- backend/tests/test_coverage_boost11.py — 2 hit(s) [tests] :: tests-only / intentionally suppressing in tests=2
- backend/tests/test_coverage_boost12.py — 1 hit(s) [tests] :: tests-only / intentionally suppressing in tests=1
- backend/tests/test_coverage_boost7_real.py — 2 hit(s) [tests] :: tests-only / intentionally suppressing in tests=2
- backend/tests/test_coverage_boost9.py — 5 hit(s) [tests] :: tests-only / intentionally suppressing in tests=5
- backend/tests/test_coverage_boost_2.py — 1 hit(s) [tests] :: tests-only / intentionally suppressing in tests=1
- backend/tests/test_coverage_zero_modules.py — 2 hit(s) [tests] :: tests-only / intentionally suppressing in tests=2
- backend/tests/test_governance_guards.py — 1 hit(s) [tests] :: tests-only / intentionally suppressing in tests=1
- backend/tests/test_production_readiness.py — 1 hit(s) [tests] :: tests-only / intentionally suppressing in tests=1
- backend/tests/test_scope_normalization.py — 1 hit(s) [tests] :: tests-only / intentionally suppressing in tests=1
- impl_v1/governance/evolution_test.py — 1 hit(s) [tests] :: tests-only / intentionally suppressing in tests=1
- scripts/ci_security_scan.py — 1 hit(s) [production] :: likely bug / error masking=1
- scripts/fast_bridge_ingest.py — 1 hit(s) [production] :: likely bug / error masking=1
- scripts/ingestion_bootstrap.py — 1 hit(s) [production] :: likely bug / error masking=1
- scripts/migrate_pt_to_safetensors.py — 1 hit(s) [production] :: likely bug / error masking=1
- scripts/remediation_scan.py — 1 hit(s) [production] :: likely bug / error masking=1

## Category counts
- likely bug / error masking: 5
- tests-only / intentionally suppressing in tests: 17

## Top production files for Phase 0C
- 1. scripts/ci_security_scan.py — 1 hit(s) :: likely bug / error masking=1
- 2. scripts/fast_bridge_ingest.py — 1 hit(s) :: likely bug / error masking=1
- 3. scripts/ingestion_bootstrap.py — 1 hit(s) :: likely bug / error masking=1
- 4. scripts/migrate_pt_to_safetensors.py — 1 hit(s) :: likely bug / error masking=1
- 5. scripts/remediation_scan.py — 1 hit(s) :: likely bug / error masking=1

## Recommended batching plan for Phase 0C
- Batch 1 - top production files with highest operational value:
  - scripts/ci_security_scan.py
  - scripts/fast_bridge_ingest.py
  - scripts/ingestion_bootstrap.py
  - scripts/migrate_pt_to_safetensors.py
  - scripts/remediation_scan.py
- Batch 3 - tests-only suppressions after production cleanup:
  - backend/tests/test_coverage_boost11.py
  - backend/tests/test_coverage_boost12.py
  - backend/tests/test_coverage_boost7_real.py
  - backend/tests/test_coverage_boost9.py
  - backend/tests/test_coverage_boost_2.py
  - backend/tests/test_coverage_zero_modules.py
  - backend/tests/test_governance_guards.py
  - backend/tests/test_production_readiness.py
  - backend/tests/test_scope_normalization.py
  - impl_v1/governance/evolution_test.py

## Complete inventory
### backend/tests/test_coverage_boost11.py
- L142: except ...: pass [(ImportError, AttributeError)] | tests | tests-only / intentionally suppressing in tests | except (ImportError, AttributeError):
- L151: except ...: pass [(ImportError, AttributeError)] | tests | tests-only / intentionally suppressing in tests | except (ImportError, AttributeError):
### backend/tests/test_coverage_boost12.py
- L109: except ...: pass [(ImportError, AttributeError)] | tests | tests-only / intentionally suppressing in tests | except (ImportError, AttributeError):
### backend/tests/test_coverage_boost7_real.py
- L490: except ...: pass [sqlite3.OperationalError] | tests | tests-only / intentionally suppressing in tests | except sqlite3.OperationalError:
- L503: except ...: pass [(ImportError, TypeError)] | tests | tests-only / intentionally suppressing in tests | except (ImportError, TypeError):
### backend/tests/test_coverage_boost9.py
- L335: except ...: pass [ImportError] | tests | tests-only / intentionally suppressing in tests | except ImportError:
- L343: except ...: pass [ImportError] | tests | tests-only / intentionally suppressing in tests | except ImportError:
- L352: except ...: pass [ImportError] | tests | tests-only / intentionally suppressing in tests | except ImportError:
- L367: except ...: pass [ImportError] | tests | tests-only / intentionally suppressing in tests | except ImportError:
- L387: except ...: pass [(ImportError, AttributeError)] | tests | tests-only / intentionally suppressing in tests | except (ImportError, AttributeError):
### backend/tests/test_coverage_boost_2.py
- L328: except ...: pass [Exception] | tests | tests-only / intentionally suppressing in tests | except Exception:
### backend/tests/test_coverage_zero_modules.py
- L506: except ...: pass [RuntimeError] | tests | tests-only / intentionally suppressing in tests | except RuntimeError:
- L692: except ...: pass [ValueError] | tests | tests-only / intentionally suppressing in tests | except ValueError:
### backend/tests/test_governance_guards.py
- L118: except ...: pass [(AttributeError, TypeError)] | tests | tests-only / intentionally suppressing in tests | except (AttributeError, TypeError):
### backend/tests/test_production_readiness.py
- L326: except ...: pass [OSError] | tests | tests-only / intentionally suppressing in tests | except OSError:
### backend/tests/test_scope_normalization.py
- L95: except ...: pass [ValueError] | tests | tests-only / intentionally suppressing in tests | except ValueError:
### impl_v1/governance/evolution_test.py
- L190: except ...: pass [Exception] | tests | tests-only / intentionally suppressing in tests | except Exception:
### scripts/ci_security_scan.py
- L169: except ...: pass [Exception] | production | likely bug / error masking | except Exception:
### scripts/fast_bridge_ingest.py
- L56: except ...: pass [AttributeError] | production | likely bug / error masking | except AttributeError:
### scripts/ingestion_bootstrap.py
- L81: except ...: pass [Exception] | production | likely bug / error masking | except Exception:
### scripts/migrate_pt_to_safetensors.py
- L143: except ...: pass [OSError] | production | likely bug / error masking | except OSError:
### scripts/remediation_scan.py
- L283: except ...: pass [Exception] | production | likely bug / error masking | except Exception:
