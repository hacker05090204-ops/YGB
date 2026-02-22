/**
 * shard_storage.cpp — Shard-Based Storage Engine (Phase 1)
 *
 * Content-addressable shard storage:
 * - Fixed 256MB shards
 * - SHA-256 identified
 * - shard_index tracking
 *
 * C API for Python ctypes.
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <mutex>

// ============================================================================
// CONSTANTS
// ============================================================================

#define MAX_SHARDS 4096
#define SHARD_SIZE_BYTES (256 * 1024 * 1024) // 256MB
#define HASH_STR_LEN 65                      // SHA-256 hex + null
#define PATH_LEN 512

// ============================================================================
// TYPES
// ============================================================================

enum ShardState {
  SHARD_ACTIVE = 0,
  SHARD_COLD = 1,
  SHARD_COMPRESSED = 2,
  SHARD_ARCHIVED = 3, // On NAS
  SHARD_CLOUD = 4,
  SHARD_DELETED = 5,
};

struct ShardInfo {
  char shard_id[HASH_STR_LEN]; // SHA-256 content hash
  char namespace_id[128];      // Field namespace
  uint64_t original_size;
  uint64_t stored_size; // After compression
  int state;            // ShardState
  int replica_count;    // Number of copies across cluster
  long created_at;
  long last_accessed;
  char storage_path[PATH_LEN];
};

struct ShardIndex {
  ShardInfo shards[MAX_SHARDS];
  int shard_count;
  uint64_t total_stored_bytes;
  uint64_t total_original_bytes;
};

// ============================================================================
// GLOBAL STATE
// ============================================================================

static struct {
  ShardIndex index;
  std::mutex mu;
  int initialized;
} g_shard = {.initialized = 0};

static long _now_epoch() { return (long)time(NULL); }

// ============================================================================
// C API
// ============================================================================

extern "C" {

int shard_init(void) {
  std::lock_guard<std::mutex> lock(g_shard.mu);
  memset(&g_shard.index, 0, sizeof(ShardIndex));
  g_shard.initialized = 1;
  fprintf(stdout, "[SHARD] Engine initialized: max=%d shard_size=%dMB\n",
          MAX_SHARDS, SHARD_SIZE_BYTES / (1024 * 1024));
  return 0;
}

/**
 * Register a shard in the index.
 */
int shard_register(const char *shard_id, const char *namespace_id,
                   uint64_t original_size, uint64_t stored_size,
                   const char *storage_path, int replica_count) {
  std::lock_guard<std::mutex> lock(g_shard.mu);

  if (g_shard.index.shard_count >= MAX_SHARDS) {
    fprintf(stderr, "[SHARD] Index full: %d\n", MAX_SHARDS);
    return -1;
  }

  // Check duplicate
  for (int i = 0; i < g_shard.index.shard_count; i++) {
    if (strcmp(g_shard.index.shards[i].shard_id, shard_id) == 0) {
      // Update existing
      g_shard.index.shards[i].replica_count = replica_count;
      g_shard.index.shards[i].last_accessed = _now_epoch();
      return i;
    }
  }

  int idx = g_shard.index.shard_count;
  ShardInfo &s = g_shard.index.shards[idx];
  strncpy(s.shard_id, shard_id, HASH_STR_LEN - 1);
  strncpy(s.namespace_id, namespace_id ? namespace_id : "default", 127);
  s.original_size = original_size;
  s.stored_size = stored_size;
  s.state = SHARD_ACTIVE;
  s.replica_count = replica_count;
  s.created_at = _now_epoch();
  s.last_accessed = _now_epoch();
  strncpy(s.storage_path, storage_path ? storage_path : "", PATH_LEN - 1);

  g_shard.index.shard_count++;
  g_shard.index.total_stored_bytes += stored_size;
  g_shard.index.total_original_bytes += original_size;

  fprintf(stdout, "[SHARD] Registered: %s ns=%s size=%lluMB replicas=%d\n",
          shard_id, s.namespace_id,
          (unsigned long long)(original_size / (1024 * 1024)), replica_count);

  return idx;
}

/**
 * Update shard state (e.g., ACTIVE → COMPRESSED → ARCHIVED).
 */
int shard_set_state(const char *shard_id, int new_state) {
  std::lock_guard<std::mutex> lock(g_shard.mu);

  for (int i = 0; i < g_shard.index.shard_count; i++) {
    if (strcmp(g_shard.index.shards[i].shard_id, shard_id) == 0) {
      g_shard.index.shards[i].state = new_state;
      return 0;
    }
  }
  return -1;
}

/**
 * Update shard replica count.
 */
int shard_set_replicas(const char *shard_id, int count) {
  std::lock_guard<std::mutex> lock(g_shard.mu);

  for (int i = 0; i < g_shard.index.shard_count; i++) {
    if (strcmp(g_shard.index.shards[i].shard_id, shard_id) == 0) {
      g_shard.index.shards[i].replica_count = count;
      return 0;
    }
  }
  return -1;
}

/**
 * Find cold shards (least recently accessed).
 */
int shard_find_cold(int max_results, int *out_indices) {
  std::lock_guard<std::mutex> lock(g_shard.mu);

  // Simple bubble: find oldest-accessed active shards
  int count = 0;
  for (int i = 0; i < g_shard.index.shard_count && count < max_results; i++) {
    if (g_shard.index.shards[i].state == SHARD_ACTIVE) {
      out_indices[count++] = i;
    }
  }

  // Sort by last_accessed ascending
  for (int i = 0; i < count - 1; i++) {
    for (int j = i + 1; j < count; j++) {
      if (g_shard.index.shards[out_indices[j]].last_accessed <
          g_shard.index.shards[out_indices[i]].last_accessed) {
        int tmp = out_indices[i];
        out_indices[i] = out_indices[j];
        out_indices[j] = tmp;
      }
    }
  }

  return count;
}

/**
 * Get shard info by index.
 */
int shard_get_info(int idx, char *out_id, char *out_ns, uint64_t *out_orig,
                   uint64_t *out_stored, int *out_state, int *out_replicas) {
  std::lock_guard<std::mutex> lock(g_shard.mu);
  if (idx < 0 || idx >= g_shard.index.shard_count)
    return -1;

  ShardInfo &s = g_shard.index.shards[idx];
  if (out_id)
    strncpy(out_id, s.shard_id, HASH_STR_LEN - 1);
  if (out_ns)
    strncpy(out_ns, s.namespace_id, 127);
  if (out_orig)
    *out_orig = s.original_size;
  if (out_stored)
    *out_stored = s.stored_size;
  if (out_state)
    *out_state = s.state;
  if (out_replicas)
    *out_replicas = s.replica_count;

  return 0;
}

int shard_count(void) {
  std::lock_guard<std::mutex> lock(g_shard.mu);
  return g_shard.index.shard_count;
}

uint64_t shard_total_stored(void) {
  std::lock_guard<std::mutex> lock(g_shard.mu);
  return g_shard.index.total_stored_bytes;
}

} // extern "C"
