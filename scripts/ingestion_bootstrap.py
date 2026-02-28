"""
Ingestion Bootstrap — Feeds real data into the C++ ingestion bridge.

Reads from available data sources (CVE pipeline, storage) and
calls bridge_ingest_sample() for each record. Updates the
dataset_manifest.json after ingestion.

Usage:
    python scripts/ingestion_bootstrap.py [--max-samples N]
"""

import ctypes
import json
import logging
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger("ingestion_bootstrap")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

# Bridge paths
_BRIDGE_DIR = PROJECT_ROOT / "native" / "distributed"
_BRIDGE_LIB = "ingestion_bridge.dll" if os.name == "nt" else "libingestion_bridge.so"


def load_bridge():
    """Load the ingestion bridge DLL and configure function signatures."""
    lib_path = _BRIDGE_DIR / _BRIDGE_LIB
    if not lib_path.exists():
        raise FileNotFoundError(f"Bridge DLL not found: {lib_path}")

    lib = ctypes.CDLL(str(lib_path))

    lib.bridge_init.restype = ctypes.c_int
    lib.bridge_init.argtypes = []

    lib.bridge_get_count.restype = ctypes.c_int
    lib.bridge_get_count.argtypes = []

    lib.bridge_get_verified_count.restype = ctypes.c_int
    lib.bridge_get_verified_count.argtypes = []

    lib.bridge_ingest_sample.restype = ctypes.c_int
    lib.bridge_ingest_sample.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_double,
    ]

    return lib


def ingest_from_cve_pipeline(lib, max_samples: int = 0) -> int:
    """
    Read CVE records from the pipeline and ingest into bridge.

    Returns number of successfully ingested samples.
    """
    ingested = 0
    try:
        from backend.cve.cve_pipeline import get_pipeline
        pipeline = get_pipeline()
        status = pipeline.get_pipeline_status()
        total = status.get("total_records", 0)
        logger.info(f"[CVE] Pipeline has {total} records")

        if total == 0:
            logger.warning("[CVE] No records in pipeline — skipping")
            return 0

        # Search with broad query to get all records
        records = []
        for query in ["CVE-202", "CVE-201", "vulnerability", "exploit"]:
            try:
                results = pipeline.search(query)
                records.extend(results)
            except Exception:
                pass

        # Deduplicate by CVE ID
        seen = set()
        unique_records = []
        for r in records:
            cve_id = r.get("cve_id", r.get("id", ""))
            if cve_id and cve_id not in seen:
                seen.add(cve_id)
                unique_records.append(r)

        logger.info(f"[CVE] {len(unique_records)} unique records to ingest")

        for record in unique_records:
            if max_samples and ingested >= max_samples:
                break

            endpoint = record.get("cve_id", record.get("id", "unknown"))
            parameters = json.dumps(record.get("affected_products", [])
                                    if isinstance(record.get("affected_products"), list)
                                    else [])[:511]
            exploit_vector = record.get("description", record.get("summary", ""))[:511]
            impact = record.get("severity", record.get("cvss_score", "MEDIUM"))
            if isinstance(impact, (int, float)):
                impact = f"CVSS:{impact}"
            source_tag = record.get("source", "CVE_PIPELINE")
            reliability = 0.8  # CVE records from canonical feeds are high reliability

            rc = lib.bridge_ingest_sample(
                endpoint.encode("utf-8"),
                parameters.encode("utf-8"),
                exploit_vector.encode("utf-8"),
                str(impact).encode("utf-8"),
                source_tag.encode("utf-8"),
                reliability,
            )
            if rc == 0:
                ingested += 1
            elif rc == -3:
                pass  # duplicate, expected

    except ImportError:
        logger.warning("[CVE] CVE pipeline not available — skipping")
    except Exception as e:
        logger.error(f"[CVE] Error during ingestion: {e}")

    return ingested


def ingest_from_storage(lib, max_samples: int = 0) -> int:
    """
    Read bounty/target records from HDD storage and ingest into bridge.

    Returns number of successfully ingested samples.
    """
    ingested = 0
    try:
        from backend.storage.storage_bridge import get_all_targets, get_all_bounties

        targets = get_all_targets()
        logger.info(f"[STORAGE] {len(targets)} targets available")

        for target in targets:
            if max_samples and ingested >= max_samples:
                break

            endpoint = target.get("program_name", target.get("id", "unknown"))
            parameters = target.get("scope", "")[:511]
            exploit_vector = f"target:{endpoint}|scope:{parameters}"
            impact = target.get("payout_tier", "MEDIUM")
            source_tag = "STORAGE_TARGETS"
            reliability = 0.75

            rc = lib.bridge_ingest_sample(
                endpoint.encode("utf-8"),
                parameters.encode("utf-8"),
                exploit_vector.encode("utf-8"),
                str(impact).encode("utf-8"),
                source_tag.encode("utf-8"),
                reliability,
            )
            if rc == 0:
                ingested += 1

        bounties = get_all_bounties()
        logger.info(f"[STORAGE] {len(bounties)} bounties available")

        for bounty in bounties:
            if max_samples and ingested >= max_samples:
                break

            endpoint = bounty.get("title", bounty.get("id", "unknown"))
            parameters = bounty.get("description", "")[:511]
            exploit_vector = f"bounty:{endpoint}"
            impact = bounty.get("severity", "MEDIUM")
            source_tag = "STORAGE_BOUNTIES"
            reliability = 0.7

            rc = lib.bridge_ingest_sample(
                endpoint.encode("utf-8"),
                parameters.encode("utf-8"),
                exploit_vector.encode("utf-8"),
                str(impact).encode("utf-8"),
                source_tag.encode("utf-8"),
                reliability,
            )
            if rc == 0:
                ingested += 1

    except ImportError:
        logger.warning("[STORAGE] Storage bridge not available — skipping")
    except Exception as e:
        logger.error(f"[STORAGE] Error during ingestion: {e}")

    return ingested


def update_manifest(lib):
    """Regenerate the dataset manifest after ingestion."""
    try:
        from impl_v1.training.data.real_dataset_loader import generate_dataset_manifest
        result = generate_dataset_manifest()
        if result["success"]:
            logger.info(f"[MANIFEST] Written to {result['path']}")
            manifest = result["manifest"]
            logger.info(
                f"[MANIFEST] total_samples={manifest['total_samples']}, "
                f"verified={manifest['verified_samples']}, "
                f"deficit={manifest['deficit']}, "
                f"ready={manifest['ready']}"
            )
            if manifest.get("per_field_counts"):
                logger.info(f"[MANIFEST] per_field_counts={json.dumps(manifest['per_field_counts'])}")
            if manifest.get("per_field_deficits"):
                for field, deficit in manifest["per_field_deficits"].items():
                    if deficit > 0:
                        logger.info(f"[MANIFEST] DEFICIT {field}: needs {deficit} more samples")

            # Also write to data/dataset_manifest.json for easy access
            data_manifest_path = PROJECT_ROOT / "data" / "dataset_manifest.json"
            data_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(data_manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)
            logger.info(f"[MANIFEST] Also written to {data_manifest_path}")
        else:
            logger.error(f"[MANIFEST] Failed: {result['error']}")
    except Exception as e:
        logger.error(f"[MANIFEST] Error: {e}")


def report_only():
    """Show current ingestion status without modifying data."""
    lib = load_bridge()

    count = lib.bridge_get_count()
    verified = lib.bridge_get_verified_count()

    logger.info("=" * 60)
    logger.info("INGESTION REPORT — Read-Only")
    logger.info("=" * 60)
    logger.info(f"  Bridge total count:    {count}")
    logger.info(f"  Bridge verified count: {verified}")

    try:
        from impl_v1.training.data.real_dataset_loader import (
            get_per_field_report, YGB_MIN_REAL_SAMPLES,
        )
        report = get_per_field_report()
        logger.info(f"  Threshold:             {YGB_MIN_REAL_SAMPLES}")
        logger.info(f"  Status:                {report['status']}")
        logger.info(f"  Reason:                {report['reason']}")
        logger.info(f"  Overall deficit:       {report['deficit']}")

        if report.get("per_field_counts"):
            logger.info("  Per-field counts:")
            for field, cnt in sorted(report["per_field_counts"].items()):
                deficit = report.get("per_field_deficits", {}).get(field, 0)
                status = "OK" if deficit == 0 else f"DEFICIT={deficit}"
                logger.info(f"    {field}: {cnt} [{status}]")
        else:
            logger.info("  Per-field counts: (none — no verified samples)")

        if report.get("manifest_exists"):
            logger.info(f"  Manifest exists: YES")
        else:
            logger.info(f"  Manifest exists: NO")

    except Exception as e:
        logger.error(f"  Report error: {e}")

    logger.info("=" * 60)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Ingestion Bootstrap")
    parser.add_argument("--max-samples", type=int, default=0,
                        help="Max samples to ingest (0=unlimited)")
    parser.add_argument("--init", action="store_true",
                        help="Call bridge_init() before ingestion (WIPES existing data)")
    parser.add_argument("--report-only", action="store_true",
                        help="Show current status without modifying data")
    args = parser.parse_args()

    if args.report_only:
        report_only()
        return

    logger.info("=" * 60)
    logger.info("INGESTION BOOTSTRAP — Starting")
    logger.info("=" * 60)

    lib = load_bridge()

    # Show pre-ingestion state
    pre_count = lib.bridge_get_count()
    pre_verified = lib.bridge_get_verified_count()
    logger.info(f"[PRE] Bridge count={pre_count}, verified={pre_verified}")

    if args.init:
        logger.info("[INIT] Calling bridge_init() — this WIPES existing data")
        lib.bridge_init()

    # Ingest from all sources
    t0 = time.time()
    total_ingested = 0

    cve_count = ingest_from_cve_pipeline(lib, args.max_samples)
    total_ingested += cve_count
    logger.info(f"[CVE] Ingested {cve_count} samples")

    remaining = (args.max_samples - total_ingested) if args.max_samples else 0
    storage_count = ingest_from_storage(lib, remaining if args.max_samples else 0)
    total_ingested += storage_count
    logger.info(f"[STORAGE] Ingested {storage_count} samples")

    elapsed = time.time() - t0

    # Show post-ingestion state
    post_count = lib.bridge_get_count()
    post_verified = lib.bridge_get_verified_count()
    logger.info(f"[POST] Bridge count={post_count}, verified={post_verified}")
    logger.info(f"[POST] New samples: {total_ingested} in {elapsed:.1f}s")

    # Update manifest
    update_manifest(lib)

    logger.info("=" * 60)
    logger.info("INGESTION BOOTSTRAP — Complete")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

