# Phase 0 Prioritized Work Order

## Scan summary

- [`report/phase0_scan/scan_b.txt`](report/phase0_scan/scan_b.txt) found 118 critical mock/fake findings and 50 high-severity incomplete-exception findings, but many are in audit helpers and gate scripts rather than production runtime paths.
- [`report/phase0_scan/scan_c.txt`](report/phase0_scan/scan_c.txt) found 10 wiring gaps and 5 missing files/directories, including critical gaps in [`backend/training/auto_train_controller.py`](backend/training/auto_train_controller.py), [`backend/ingestion/autograbber.py`](backend/ingestion/autograbber.py), and missing [`backend/intelligence`](backend/intelligence).
- [`report/phase0_scan/scan_d.txt`](report/phase0_scan/scan_d.txt) confirmed a live GPU: RTX 2050, 4.3 GB VRAM, CUDA 12.1. GPU-first fixes must target low-VRAM operation.
- [`report/phase0_scan/scan_e.txt`](report/phase0_scan/scan_e.txt) showed 6/12 live sources. Broken sources: OSV request format, Red Hat URL, Snyk path, PacketStorm reachability, Alpine URL, Debian timeout.
- [`report/phase0_scan/scan_f.txt`](report/phase0_scan/scan_f.txt) showed missing security-intelligence capabilities, most importantly scanner and report-generation gaps.
- [`report/phase0_scan/scan_g.txt`](report/phase0_scan/scan_g.txt) found active HDD defaults in [`api/database.py`](api/database.py), [`storage_backend.py`](storage_backend.py), multiple [`backend/sync`](backend/sync) modules, and [`native/hdd_engine/hdd_engine.py`](native/hdd_engine/hdd_engine.py).

## Priority 0 — production blockers before any broader rebuild

1. **SSD-first storage and DB path correction**
   - Replace HDD defaults in [`api/database.py`](api/database.py), [`backend/config/config_validator.py`](backend/config/config_validator.py), [`backend/storage/tiered_storage.py`](backend/storage/tiered_storage.py), and follow-up references from [`report/phase0_scan/ssd_migration.json`](report/phase0_scan/ssd_migration.json).
   - Add shared storage constants in [`config/storage_config.py`](config/storage_config.py).

2. **Database connection safety**
   - Harden [`api/database.py`](api/database.py) around [`get_db()`](api/database.py:60) with SSD-optimized connection setup, concurrency-safe lifecycle, and explicit PRAGMAs.

3. **Governance hard-fail enforcement**
   - Audit [`impl_v1/training/data/governance_pipeline.py`](impl_v1/training/data/governance_pipeline.py) for import soft-skips and swallowed audit failures.

4. **Nonce persistence**
   - Replace in-memory nonce tracking inside [`HUMANOID_HUNTER`](HUMANOID_HUNTER) with SQLite-backed persistence on SSD storage.

5. **Broken scraper repair for minimum live-source floor**
   - Fix OSV, Red Hat, Snyk, Alpine, Debian handling and add missing [`backend/ingestion/scrapers/exploit_db_scraper.py`](backend/ingestion/scrapers/exploit_db_scraper.py) and [`backend/ingestion/scrapers/vendor_advisory_scraper.py`](backend/ingestion/scrapers/vendor_advisory_scraper.py).

## Priority 1 — critical wiring and GPU-first execution

1. Wire MoE into [`backend/training/auto_train_controller.py`](backend/training/auto_train_controller.py).
2. Add explicit GPU placement in [`impl_v1/phase49/moe/__init__.py`](impl_v1/phase49/moe/__init__.py) and verify low-VRAM support for RTX 2050.
3. Add GPU-aware logic and monitoring in [`backend/training/auto_train_controller.py`](backend/training/auto_train_controller.py).
4. Repair [`val_f1`](backend/training/incremental_trainer.py:1) checkpoint references in [`backend/training/incremental_trainer.py`](backend/training/incremental_trainer.py).

## Priority 2 — ingestion pipeline throughput and integrity

1. Add missing [`DedupStore`](backend/ingestion/autograbber.py:1) wiring in [`backend/ingestion/autograbber.py`](backend/ingestion/autograbber.py).
2. Convert source orchestration in [`backend/ingestion/autograbber.py`](backend/ingestion/autograbber.py) to [`asyncio`](backend/ingestion/autograbber.py:1)-based I/O.
3. Ensure SSD-aware storage writes and realistic rate-limited retries.

## Priority 3 — remove production fake data and exception swallowing

1. Review production-only entries from [`report/phase0_scan/mock_violations.json`](report/phase0_scan/mock_violations.json) and separate audit/test-only noise from runtime paths.
2. Eliminate bare exception swallows in production modules.
3. Replace simulated production API responses with DB-backed or explicit failure responses.

## Priority 4 — intelligence and reporting layer completion

1. Create missing [`backend/intelligence`](backend/intelligence) package with vulnerability detection, evidence capture, and scope validation.
2. Create missing [`backend/scanner`](backend/scanner) package for passive scan orchestration.
3. Verify report generation uses real evidence and SSD-backed storage.

## Priority 5 — final optimization and verification

1. Finish status-cache background refresh in [`backend/api/system_status.py`](backend/api/system_status.py).
2. Use real byte-size accounting in [`backend/training/compression_engine.py`](backend/training/compression_engine.py).
3. Re-run wiring, mock, and SSD scans after implementation phases.
4. Run gates and final full-suite verification.

## Immediate execution order

1. Read and patch [`api/database.py`](api/database.py), [`backend/config/config_validator.py`](backend/config/config_validator.py), and [`backend/storage/tiered_storage.py`](backend/storage/tiered_storage.py).
2. Read and patch [`impl_v1/training/data/governance_pipeline.py`](impl_v1/training/data/governance_pipeline.py).
3. Read nonce management files under [`HUMANOID_HUNTER`](HUMANOID_HUNTER).
4. Read broken scraper modules under [`backend/ingestion/scrapers`](backend/ingestion/scrapers).
5. Sweep production bare-except findings after the above structural fixes.
