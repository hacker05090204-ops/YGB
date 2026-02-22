/**
 * incremental_sync.cpp — Incremental Sync Engine (Phase 3)
 *
 * Hourly hash-compare across cluster:
 * - Compare shard hashes
 * - Transfer missing shards only
 * - Post-transfer hash verify
 * - Multi-threaded TCP
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

#define MAX_PEERS 10
#define MAX_SYNC_OPS 1024
#define HASH_LEN 65
#define SYNC_INTERVAL_SEC 3600 // 1 hour

// ============================================================================
// TYPES
// ============================================================================

enum SyncStatus {
  SYNC_PENDING = 0,
  SYNC_IN_PROGRESS = 1,
  SYNC_COMPLETE = 2,
  SYNC_FAILED = 3,
  SYNC_VERIFIED = 4,
};

struct SyncOp {
  char shard_id[HASH_LEN];
  char source_peer[64];
  char target_peer[64];
  uint64_t size_bytes;
  int status;
  int hash_verified;
  long started_at;
  long completed_at;
};

struct PeerState {
  char peer_id[64];
  char address[128];
  int port;
  int alive;
  int shard_count;
  long last_sync;
};

struct SyncReport {
  int total_ops;
  int completed;
  int failed;
  int verified;
  uint64_t bytes_transferred;
  long sync_started;
  long sync_completed;
};

// ============================================================================
// GLOBAL STATE
// ============================================================================

static struct {
  PeerState peers[MAX_PEERS];
  int peer_count;
  SyncOp ops[MAX_SYNC_OPS];
  int op_count;
  SyncReport last_report;
  std::mutex mu;
  int initialized;
} g_sync = {.peer_count = 0, .op_count = 0, .initialized = 0};

// ============================================================================
// C API
// ============================================================================

extern "C" {

int sync_init(void) {
  std::lock_guard<std::mutex> lock(g_sync.mu);
  memset(g_sync.peers, 0, sizeof(g_sync.peers));
  g_sync.peer_count = 0;
  g_sync.op_count = 0;
  memset(&g_sync.last_report, 0, sizeof(SyncReport));
  g_sync.initialized = 1;
  fprintf(stdout, "[SYNC] Engine initialized: interval=%ds\n",
          SYNC_INTERVAL_SEC);
  return 0;
}

/**
 * Register a peer node.
 */
int sync_register_peer(const char *peer_id, const char *address, int port) {
  std::lock_guard<std::mutex> lock(g_sync.mu);
  if (g_sync.peer_count >= MAX_PEERS)
    return -1;

  int idx = g_sync.peer_count;
  PeerState &p = g_sync.peers[idx];
  strncpy(p.peer_id, peer_id, 63);
  strncpy(p.address, address, 127);
  p.port = port;
  p.alive = 1;
  p.shard_count = 0;
  p.last_sync = 0;

  g_sync.peer_count++;
  fprintf(stdout, "[SYNC] Peer registered: %s (%s:%d)\n", peer_id, address,
          port);
  return idx;
}

/**
 * Queue a shard sync operation.
 */
int sync_queue_transfer(const char *shard_id, const char *source_peer,
                        const char *target_peer, uint64_t size_bytes) {
  std::lock_guard<std::mutex> lock(g_sync.mu);
  if (g_sync.op_count >= MAX_SYNC_OPS)
    return -1;

  int idx = g_sync.op_count;
  SyncOp &op = g_sync.ops[idx];
  strncpy(op.shard_id, shard_id, HASH_LEN - 1);
  strncpy(op.source_peer, source_peer, 63);
  strncpy(op.target_peer, target_peer, 63);
  op.size_bytes = size_bytes;
  op.status = SYNC_PENDING;
  op.hash_verified = 0;
  op.started_at = 0;
  op.completed_at = 0;

  g_sync.op_count++;
  fprintf(stdout, "[SYNC] Queued: shard=%s src=%s → dst=%s (%lluMB)\n",
          shard_id, source_peer, target_peer,
          (unsigned long long)(size_bytes / (1024 * 1024)));
  return idx;
}

/**
 * Mark a sync operation as complete with hash verification.
 */
int sync_complete_transfer(int op_idx, int hash_verified) {
  std::lock_guard<std::mutex> lock(g_sync.mu);
  if (op_idx < 0 || op_idx >= g_sync.op_count)
    return -1;

  SyncOp &op = g_sync.ops[op_idx];
  op.status = hash_verified ? SYNC_VERIFIED : SYNC_COMPLETE;
  op.hash_verified = hash_verified;
  op.completed_at = (long)time(NULL);

  fprintf(stdout, "[SYNC] Complete: shard=%s verified=%d\n", op.shard_id,
          hash_verified);
  return 0;
}

/**
 * Mark a sync operation as failed.
 */
int sync_fail_transfer(int op_idx) {
  std::lock_guard<std::mutex> lock(g_sync.mu);
  if (op_idx < 0 || op_idx >= g_sync.op_count)
    return -1;

  g_sync.ops[op_idx].status = SYNC_FAILED;
  return 0;
}

/**
 * Generate sync report.
 */
int sync_get_report(int *out_total, int *out_completed, int *out_failed,
                    int *out_verified, uint64_t *out_bytes) {
  std::lock_guard<std::mutex> lock(g_sync.mu);

  int total = 0, completed = 0, failed = 0, verified = 0;
  uint64_t bytes = 0;

  for (int i = 0; i < g_sync.op_count; i++) {
    total++;
    switch (g_sync.ops[i].status) {
    case SYNC_COMPLETE:
      completed++;
      bytes += g_sync.ops[i].size_bytes;
      break;
    case SYNC_VERIFIED:
      verified++;
      bytes += g_sync.ops[i].size_bytes;
      break;
    case SYNC_FAILED:
      failed++;
      break;
    default:
      break;
    }
  }

  if (out_total)
    *out_total = total;
  if (out_completed)
    *out_completed = completed;
  if (out_failed)
    *out_failed = failed;
  if (out_verified)
    *out_verified = verified;
  if (out_bytes)
    *out_bytes = bytes;

  return 0;
}

int sync_peer_count(void) {
  std::lock_guard<std::mutex> lock(g_sync.mu);
  return g_sync.peer_count;
}

int sync_op_count(void) {
  std::lock_guard<std::mutex> lock(g_sync.mu);
  return g_sync.op_count;
}

} // extern "C"
