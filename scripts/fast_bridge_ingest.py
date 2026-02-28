"""
fast_bridge_ingest.py — Single-process NVD → Bridge bulk ingest + manifest + readiness verification.

Runs in one process so bridge DLL counters persist across the entire ingestion lifecycle.
Uses batched NVD fetches with aggressive retry+backoff. Writes manifest at end.
Reports truthful GO/NO_GO with exact deficit.

Usage: python scripts/fast_bridge_ingest.py [target]
"""

import ctypes
import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.error

TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 125_000
BATCH_SIZE = 2000
NVD_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"
HEADERS = {"User-Agent": "YGB-CVE-Pipeline/2.0"}
RETRY_WAIT = 6
MAX_RETRIES = 5

# Paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DLL_PATH = os.path.join(PROJECT_ROOT, "native", "distributed", "ingestion_bridge.dll")
MANIFEST_PATH = os.path.join(PROJECT_ROOT, "secure_data", "dataset_manifest.json")
REPORT_PATH = os.path.join(PROJECT_ROOT, "reports", "ingest_result.json")

# Load bridge
lib = ctypes.CDLL(DLL_PATH)
lib.bridge_get_count.restype = ctypes.c_int
lib.bridge_get_verified_count.restype = ctypes.c_int
lib.bridge_ingest_sample.restype = ctypes.c_int
lib.bridge_ingest_sample.argtypes = [
    ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
    ctypes.c_char_p, ctypes.c_char_p, ctypes.c_double,
]

# Try bridge_init if available
try:
    lib.bridge_init.restype = ctypes.c_int
    lib.bridge_init()
    print("[BRIDGE] bridge_init() called")
except:
    pass

seen = set()
stats = {"ingested": 0, "dropped": 0, "deduped": 0, "fetch_errors": 0}
t_start = time.time()


def fetch_batch(start_index):
    url = f"{NVD_BASE}?startIndex={start_index}&resultsPerPage={BATCH_SIZE}"
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read())
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            code = getattr(e, 'code', 0)
            wait = RETRY_WAIT * (attempt + 1)
            print(f"    API {code or 'ERR'}, wait {wait}s (attempt {attempt+1})")
            time.sleep(wait)
        except Exception as e:
            time.sleep(RETRY_WAIT)
    stats["fetch_errors"] += 1
    return {}


def extract_and_ingest(vuln):
    cve = vuln.get("cve", {})
    cve_id = cve.get("id", "")
    if not cve_id:
        stats["dropped"] += 1
        return 0

    descs = cve.get("descriptions", [])
    desc = next((d["value"] for d in descs if d.get("lang") == "en"), "")
    if not desc and descs:
        desc = descs[0].get("value", "")

    metrics = cve.get("metrics", {})
    cvss_score = 0.0
    severity = "UNKNOWN"
    for key in ["cvssMetricV31", "cvssMetricV30", "cvssMetricV2"]:
        mlist = metrics.get(key, [])
        if mlist:
            cvss = mlist[0].get("cvssData", {})
            cvss_score = cvss.get("baseScore", 0.0)
            severity = cvss.get("baseSeverity", "UNKNOWN")
            break

    impact = f"CVSS:{cvss_score}|{severity}"
    configs = cve.get("configurations", [])
    products = []
    for c in configs[:3]:
        for n in c.get("nodes", [])[:3]:
            for m in n.get("cpeMatch", [])[:5]:
                products.append(m.get("criteria", ""))
    params = "|".join(products[:10]) or "N/A"
    source = f"NVD|{cve.get('sourceIdentifier', 'nvd')}"

    ik = hashlib.sha256(f"{cve_id}::{desc[:200]}".encode()).hexdigest()[:32]
    if ik in seen:
        stats["deduped"] += 1
        return 0
    
    reliability = 0.95 if cvss_score >= 7.0 else (0.90 if cvss_score > 0 else 0.70)

    rc = lib.bridge_ingest_sample(
        cve_id.encode()[:511], params.encode()[:511],
        desc.encode()[:511], impact.encode()[:511],
        source.encode()[:511], reliability
    )
    if rc == 0:
        stats["ingested"] += 1
        seen.add(ik)
        return 1
    elif rc == -3:
        stats["deduped"] += 1
        seen.add(ik)
    else:
        stats["dropped"] += 1
    return 0


def write_manifest():
    count = lib.bridge_get_count()
    verified = lib.bridge_get_verified_count()
    manifest = {
        "version": "2.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "NVD_API_v2_bulk_ingest",
        "sample_count": count,
        "verified_count": verified,
        "field_schema": ["endpoint", "parameters", "exploit_vector", "impact", "source_tag", "reliability"],
        "strict_real_mode": True,
        "threshold": TARGET,
        "deficit": max(0, TARGET - verified),
        "go_no_go": "GO" if verified >= TARGET else "NO_GO",
    }
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"  Manifest written: {MANIFEST_PATH}")
    return manifest


# =========================================================================
# MAIN
# =========================================================================
print("=" * 60)
print(f"  NVD → Bridge Bulk Ingest (target: {TARGET:,})")
print("=" * 60)

idx = 0
batch_num = 0

while True:
    verified = lib.bridge_get_verified_count()
    if verified >= TARGET:
        print(f"\n*** TARGET REACHED: {verified:,} >= {TARGET:,} ***")
        break

    batch_num += 1
    elapsed = time.time() - t_start
    rate = stats["ingested"] / max(elapsed, 0.1)
    deficit = TARGET - verified
    eta = deficit / max(rate, 1)

    print(f"[B{batch_num:03d}] idx={idx} count={lib.bridge_get_count():,} "
          f"verified={verified:,} deficit={deficit:,} "
          f"rate={rate:.0f}/s eta={eta:.0f}s")

    data = fetch_batch(idx)
    vulns = data.get("vulnerabilities", [])
    total_nvd = data.get("totalResults", 0)

    if not vulns:
        if idx >= total_nvd and total_nvd > 0:
            print("  ALL NVD RECORDS EXHAUSTED")
            break
        idx += BATCH_SIZE
        time.sleep(RETRY_WAIT)
        continue

    batch_ok = sum(extract_and_ingest(v) for v in vulns)
    print(f"  +{batch_ok} ingested ({len(vulns)} fetched, "
          f"total={stats['ingested']:,} drop={stats['dropped']} dedup={stats['deduped']})")
    
    idx += BATCH_SIZE
    time.sleep(RETRY_WAIT)  # NVD rate limit

# Final manifest + report
elapsed = time.time() - t_start
final_count = lib.bridge_get_count()
final_verified = lib.bridge_get_verified_count()
deficit = max(0, TARGET - final_verified)
go = "GO" if deficit == 0 else "NO_GO"

manifest = write_manifest()

report = {
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "bridge_count": final_count,
    "bridge_verified_count": final_verified,
    "target": TARGET,
    "deficit": deficit,
    "status": go,
    **stats,
    "elapsed_seconds": round(elapsed, 1),
    "throughput_per_sec": round(stats["ingested"] / max(elapsed, 1), 1),
}
os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
with open(REPORT_PATH, "w") as f:
    json.dump(report, f, indent=2)

print(f"\n{'='*60}")
print(f"  FINAL: count={final_count:,} verified={final_verified:,}")
print(f"  TARGET={TARGET:,} DEFICIT={deficit:,} STATUS={go}")
print(f"  Elapsed: {elapsed:.1f}s | Rate: {report['throughput_per_sec']}/s")
print(f"  Report: {REPORT_PATH}")
print(f"{'='*60}")
