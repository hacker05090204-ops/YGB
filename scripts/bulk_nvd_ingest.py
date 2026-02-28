"""
bulk_nvd_ingest.py — High-throughput NVD → Bridge ingestion.

Fetches real CVE records from NVD API v2 in batches, maps to bridge fields,
and calls bridge_ingest_sample via ctypes until target is reached.

Non-negotiable:
  - Real NVD data only. No mocks.
  - Truthful counters from bridge DLL.
  - Stops only when bridge_get_verified_count() >= target.

Usage:
    python scripts/bulk_nvd_ingest.py [target=125000]
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
BATCH_SIZE = 2000  # NVD max per page
NVD_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"
HEADERS = {"User-Agent": "YGB-CVE-Pipeline/2.0"}
RETRY_WAIT = 6  # NVD rate limit wait
MAX_RETRIES = 5

# Load bridge
BRIDGE_DIR = os.path.join(os.path.dirname(__file__), "..", "native", "distributed")
DLL_PATH = os.path.join(BRIDGE_DIR, "ingestion_bridge.dll")

if not os.path.exists(DLL_PATH):
    print(f"FATAL: DLL not found at {DLL_PATH}")
    sys.exit(1)

lib = ctypes.CDLL(DLL_PATH)
lib.bridge_get_count.restype = ctypes.c_int
lib.bridge_get_verified_count.restype = ctypes.c_int
lib.bridge_ingest_sample.restype = ctypes.c_int
lib.bridge_ingest_sample.argtypes = [
    ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
    ctypes.c_char_p, ctypes.c_char_p, ctypes.c_double,
]

seen_keys = set()
total_ingested = 0
total_dropped = 0
total_deduped = 0
t_start = time.time()


def fetch_batch(start_index: int) -> dict:
    """Fetch a batch of CVEs from NVD API with retry."""
    url = f"{NVD_BASE}?startIndex={start_index}&resultsPerPage={BATCH_SIZE}"
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 403 or e.code == 429:
                wait = RETRY_WAIT * (attempt + 1)
                print(f"  Rate limited ({e.code}), waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"  HTTP {e.code}, retry {attempt+1}/{MAX_RETRIES}")
                time.sleep(RETRY_WAIT)
        except Exception as e:
            print(f"  Fetch error: {e}, retry {attempt+1}/{MAX_RETRIES}")
            time.sleep(RETRY_WAIT)
    return {}


def extract_fields(vuln: dict) -> tuple:
    """Extract bridge fields from NVD vulnerability object. Returns (fields_dict, reliability)."""
    cve = vuln.get("cve", {})
    cve_id = cve.get("id", "")
    if not cve_id:
        return None, 0.0

    # Description
    descs = cve.get("descriptions", [])
    desc = ""
    for d in descs:
        if d.get("lang") == "en":
            desc = d.get("value", "")
            break
    if not desc and descs:
        desc = descs[0].get("value", "")

    # Impact / CVSS
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

    # Products (CPE)
    configs = cve.get("configurations", [])
    products = []
    for cfg in configs[:3]:
        for node in cfg.get("nodes", [])[:3]:
            for match in node.get("cpeMatch", [])[:5]:
                products.append(match.get("criteria", ""))
    products_str = "|".join(products[:10]) if products else "N/A"

    # Source tag
    source_tag = f"NVD|{cve.get('sourceIdentifier', 'nvd')}"

    # Reliability: NVD is a high-trust source
    reliability = 0.90
    if cvss_score >= 7.0:
        reliability = 0.95
    elif cvss_score == 0.0:
        reliability = 0.70

    return {
        "endpoint": cve_id,
        "parameters": products_str[:511],
        "exploit_vector": desc[:511],
        "impact": impact[:511],
        "source_tag": source_tag[:511],
    }, reliability


def idempotency_key(endpoint: str, exploit_vector: str) -> str:
    h = hashlib.sha256(f"{endpoint}::{exploit_vector}".encode()).hexdigest()[:32]
    return h


def ingest_batch(vulnerabilities: list) -> int:
    """Ingest a batch of NVD vulns into the bridge. Returns count ingested."""
    global total_ingested, total_dropped, total_deduped, seen_keys
    batch_ingested = 0

    for vuln in vulnerabilities:
        fields, reliability = extract_fields(vuln)
        if not fields:
            total_dropped += 1
            continue

        ik = idempotency_key(fields["endpoint"], fields["exploit_vector"])
        if ik in seen_keys:
            total_deduped += 1
            continue

        rc = lib.bridge_ingest_sample(
            fields["endpoint"].encode("utf-8"),
            fields["parameters"].encode("utf-8"),
            fields["exploit_vector"].encode("utf-8"),
            fields["impact"].encode("utf-8"),
            fields["source_tag"].encode("utf-8"),
            reliability,
        )

        if rc == 0:
            batch_ingested += 1
            total_ingested += 1
            seen_keys.add(ik)
        elif rc == -3:
            total_deduped += 1
            seen_keys.add(ik)
        else:
            total_dropped += 1

    return batch_ingested


# =========================================================================
# MAIN LOOP
# =========================================================================

print("=" * 60)
print(f"  NVD → Bridge Bulk Ingestion")
print(f"  Target: {TARGET:,} verified samples")
print("=" * 60)

start_index = 0
batch_num = 0

while True:
    current_verified = lib.bridge_get_verified_count()
    current_count = lib.bridge_get_count()

    if current_verified >= TARGET:
        print(f"\n✓ TARGET REACHED: {current_verified:,} >= {TARGET:,}")
        break

    batch_num += 1
    elapsed = time.time() - t_start
    rate = total_ingested / max(elapsed, 0.1)
    deficit = TARGET - current_verified
    eta_sec = deficit / max(rate, 1)

    print(f"\n[Batch {batch_num}] startIndex={start_index} | "
          f"bridge={current_count:,} verified={current_verified:,} "
          f"deficit={deficit:,} | rate={rate:.0f}/s ETA={eta_sec:.0f}s")

    data = fetch_batch(start_index)
    if not data:
        print("  FETCH FAILED — retrying from same index")
        time.sleep(10)
        continue

    vulns = data.get("vulnerabilities", [])
    total_results = data.get("totalResults", 0)

    if not vulns:
        print(f"  No vulnerabilities in response (total_results={total_results})")
        if start_index >= total_results:
            print("  All NVD records exhausted.")
            break
        start_index += BATCH_SIZE
        continue

    batch_ok = ingest_batch(vulns)
    print(f"  Fetched {len(vulns)}, ingested {batch_ok}, "
          f"dropped {total_dropped}, deduped {total_deduped}")

    start_index += BATCH_SIZE

    # Respect NVD rate limit (rolling window)
    time.sleep(RETRY_WAIT)

# =========================================================================
# FINAL REPORT
# =========================================================================

elapsed = time.time() - t_start
final_count = lib.bridge_get_count()
final_verified = lib.bridge_get_verified_count()
deficit = max(0, TARGET - final_verified)
go = "GO" if deficit == 0 else "NO_GO"

print("\n" + "=" * 60)
print(f"  INGESTION COMPLETE")
print(f"  bridge_count:          {final_count:,}")
print(f"  bridge_verified_count: {final_verified:,}")
print(f"  target:                {TARGET:,}")
print(f"  deficit:               {deficit:,}")
print(f"  total_ingested:        {total_ingested:,}")
print(f"  total_dropped:         {total_dropped:,}")
print(f"  total_deduped:         {total_deduped:,}")
print(f"  elapsed:               {elapsed:.1f}s")
print(f"  throughput:            {total_ingested/max(elapsed,1):.1f} samples/s")
print(f"  status:                {go}")
print("=" * 60)

# Write result to JSON
result = {
    "bridge_count": final_count,
    "bridge_verified_count": final_verified,
    "target": TARGET,
    "deficit": deficit,
    "total_ingested": total_ingested,
    "total_dropped": total_dropped,
    "total_deduped": total_deduped,
    "elapsed_seconds": round(elapsed, 1),
    "throughput_per_sec": round(total_ingested / max(elapsed, 1), 1),
    "status": go,
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
out_path = os.path.join(os.path.dirname(__file__), "..", "reports", "ingest_result.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w") as f:
    json.dump(result, f, indent=2)
print(f"\nResult saved to {out_path}")
