"""
HDD Engine — Full Test Suite
Tests all CRUD operations, caching, lifecycle, and performance on D:\ygb_hdd
"""

import sys
import uuid
import time

sys.path.insert(0, "c:/Users/Unkno/YGB")

from native.hdd_engine.hdd_engine import HDDEngine, LifecycleState

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print("[PASS] " + name + ("  (" + detail + ")" if detail else ""))
    else:
        failed += 1
        print("[FAIL] " + name + ("  (" + detail + ")" if detail else ""))

print("=" * 60)
print("HDD ENGINE FULL TEST SUITE")
print("=" * 60)
print()

# 1. Initialize
e = HDDEngine("E:/ygb_hdd")
ok = e.initialize()
check("Initialize", ok, "root=" + str(e.root))

# 2. Get stats
stats = e.get_stats()
check("Get stats", stats["initialized"], "disk_used=" + str(stats["disk_usage"]["percent_used"]) + "%")

# 3. Create user
uid = str(uuid.uuid4())[:8]
user_id = "test-" + uid
try:
    user = e.create_entity("users", user_id, {"name": "Full Test", "email": uid + "@ygb.dev", "role": "hunter"})
    check("Create user", user is not None, "id=" + user_id)
except Exception as ex:
    check("Create user", False, str(ex))
    user = None

# 4. Read entity
entity = e.read_entity("users", user_id)
check("Read entity", entity is not None and entity["latest"]["name"] == "Full Test",
      "records=" + str(len(entity["records"])) if entity else "None")

# 5. Cache read (should be fast)
t0 = time.perf_counter()
entity2 = e.read_entity("users", user_id)
t1 = time.perf_counter()
cache_ms = (t1 - t0) * 1000
check("Cache read", cache_ms < 5, "%.2fms" % cache_ms)

# 6. Append record
try:
    rec = e.append_record("users", user_id, {"action": "login", "ip": "127.0.0.1"})
    check("Append record", rec["op"] == "UPDATE", "op=" + rec["op"])
except Exception as ex:
    check("Append record", False, str(ex))

# 7. Read after append
entity3 = e.read_entity("users", user_id)
check("Read after append", entity3 is not None and len(entity3["records"]) == 2,
      "records=" + str(len(entity3["records"])) if entity3 else "None")

# 8. List entities
listed = e.list_entities("users")
check("List entities", len(listed) >= 1, "count=" + str(len(listed)))

# 9. Count entities (cached)
t0 = time.perf_counter()
count = e.count_entities("users")
t1 = time.perf_counter()
check("Count entities", count >= 1, "count=%d, %.2fms" % (count, (t1 - t0) * 1000))

# 10. Lifecycle: ACTIVE
ok = e.update_lifecycle("users", user_id, LifecycleState.ACTIVE)
check("Lifecycle -> ACTIVE", ok)

# 11. Lifecycle: COMPLETED
ok = e.update_lifecycle("users", user_id, LifecycleState.COMPLETED)
check("Lifecycle -> COMPLETED", ok)

# 12. Read metadata (from cache)
meta = e.read_metadata("users", user_id)
check("Read metadata", meta is not None and meta["lifecycle_state"] == "COMPLETED",
      "state=" + meta["lifecycle_state"] if meta else "None")

# 13. Cache invalidation + re-read
e.invalidate_cache()
meta2 = e.read_metadata("users", user_id)
check("Post-invalidation read", meta2 is not None and meta2["lifecycle_state"] == "COMPLETED")

# 14. Create target
tid = str(uuid.uuid4())[:8]
target_id = "tgt-" + tid
try:
    target = e.create_entity("targets", target_id, {"program_name": "TestCorp", "scope": "*.testcorp.com", "payout_tier": "high"})
    check("Create target", target is not None, "id=" + target_id)
except Exception as ex:
    check("Create target", False, str(ex))

# 15. Cross-entity counts
user_count = e.count_entities("users")
target_count = e.count_entities("targets")
check("Cross-entity counts", user_count >= 1 and target_count >= 1,
      "users=%d, targets=%d" % (user_count, target_count))

# 16. Disk usage
disk = e._get_disk_usage()
total_gb = disk["total_bytes"] // (1024**3)
free_gb = disk["free_bytes"] // (1024**3)
check("Disk usage", disk["total_bytes"] > 0,
      "total=%dGB, free=%dGB, used=%.1f%%" % (total_gb, free_gb, disk["percent_used"]))

# Final
final_stats = e.get_stats()
print()
print("=" * 60)
print("FINAL STATS")
print("  Writes : %d" % final_stats["total_writes"])
print("  Reads  : %d" % final_stats["total_reads"])
print("  Entities: %d" % final_stats["total_entities"])
print("  Bytes  : %d" % final_stats["total_bytes_written"])
print("=" * 60)
print()
print("RESULTS: %d passed, %d failed" % (passed, failed))
if failed == 0:
    print("ALL TESTS PASSED")
else:
    print("SOME TESTS FAILED")
    sys.exit(1)
