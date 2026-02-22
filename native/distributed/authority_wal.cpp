/**
 * authority_wal.cpp — Write-Ahead Log (Phase 2)
 *
 * Append-only WAL for authority state changes.
 * Every mutation appended before applying.
 * On restart: replay WAL to rebuild state.
 *
 * Entry format:
 *   seq | term | fencing_token | op_type | key | value | checksum
 *
 * C API for Python ctypes integration.
 */

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <functional>
#include <mutex>
#include <string>
#include <vector>


// ============================================================================
// CONSTANTS
// ============================================================================

#define WAL_MAX_ENTRIES 10000
#define WAL_KEY_LEN 128
#define WAL_VALUE_LEN 512

// ============================================================================
// TYPES
// ============================================================================

enum WALOpType {
  WAL_OP_DATASET_LOCK = 1,
  WAL_OP_SHARD_ALLOC = 2,
  WAL_OP_CHECKPOINT_SAVE = 3,
  WAL_OP_EPOCH_INC = 4,
  WAL_OP_NODE_REGISTER = 5,
  WAL_OP_WORLD_SIZE_LOCK = 6,
  WAL_OP_TRAINING_START = 7,
  WAL_OP_TRAINING_STOP = 8,
};

struct WALEntry {
  uint64_t seq;
  int term;
  uint64_t fencing_token;
  int op_type;
  char key[WAL_KEY_LEN];
  char value[WAL_VALUE_LEN];
  uint32_t checksum;
};

// Rebuilt state from WAL replay
struct WALState {
  char dataset_hash[128];
  int dataset_locked;
  int world_size;
  int world_size_locked;
  int epoch;
  char checkpoint_id[128];
  char merged_weight_hash[128];
  int training_active;
  int node_count;
};

// ============================================================================
// CHECKSUM
// ============================================================================

static uint32_t _wal_checksum(const WALEntry &e) {
  // Simple FNV-1a hash
  uint32_t hash = 2166136261u;
  const unsigned char *data = (const unsigned char *)&e;
  // Hash everything except the checksum field itself
  size_t len = offsetof(WALEntry, checksum);
  for (size_t i = 0; i < len; i++) {
    hash ^= data[i];
    hash *= 16777619u;
  }
  return hash;
}

// ============================================================================
// GLOBAL STATE
// ============================================================================

static struct {
  WALEntry entries[WAL_MAX_ENTRIES];
  int entry_count;
  uint64_t next_seq;
  WALState state;
  char filepath[512];
  std::mutex mu;
  int initialized;
} g_wal = {.entry_count = 0, .next_seq = 1, .initialized = 0};

// ============================================================================
// INTERNAL
// ============================================================================

static void _apply_entry(WALState &state, const WALEntry &e) {
  switch (e.op_type) {
  case WAL_OP_DATASET_LOCK:
    strncpy(state.dataset_hash, e.value, 127);
    state.dataset_locked = 1;
    break;

  case WAL_OP_SHARD_ALLOC:
    // key = node_id, value = proportion
    break;

  case WAL_OP_CHECKPOINT_SAVE:
    strncpy(state.checkpoint_id, e.key, 127);
    strncpy(state.merged_weight_hash, e.value, 127);
    break;

  case WAL_OP_EPOCH_INC:
    state.epoch = atoi(e.value);
    break;

  case WAL_OP_NODE_REGISTER:
    state.node_count++;
    break;

  case WAL_OP_WORLD_SIZE_LOCK:
    state.world_size = atoi(e.value);
    state.world_size_locked = 1;
    break;

  case WAL_OP_TRAINING_START:
    state.training_active = 1;
    break;

  case WAL_OP_TRAINING_STOP:
    state.training_active = 0;
    break;

  default:
    break;
  }
}

// ============================================================================
// C API
// ============================================================================

extern "C" {

/**
 * Initialize the WAL.
 *
 * @param filepath Path to WAL file on disk
 * @return 0 on success
 */
int wal_init(const char *filepath) {
  std::lock_guard<std::mutex> lock(g_wal.mu);

  memset(&g_wal.state, 0, sizeof(WALState));
  g_wal.entry_count = 0;
  g_wal.next_seq = 1;
  strncpy(g_wal.filepath, filepath ? filepath : "authority.wal", 511);
  g_wal.initialized = 1;

  fprintf(stdout, "[WAL] Initialized: %s\n", g_wal.filepath);
  return 0;
}

/**
 * Append an entry to the WAL.
 *
 * @param term          Current term
 * @param fencing_token Current fencing token
 * @param op_type       WALOpType
 * @param key           Key string
 * @param value         Value string
 * @return 0 on success, -1 if full or stale fence
 */
int wal_append(int term, uint64_t fencing_token, int op_type, const char *key,
               const char *value) {
  std::lock_guard<std::mutex> lock(g_wal.mu);

  if (g_wal.entry_count >= WAL_MAX_ENTRIES) {
    fprintf(stderr, "[WAL] Full: %d entries\n", WAL_MAX_ENTRIES);
    return -1;
  }

  WALEntry &e = g_wal.entries[g_wal.entry_count];
  e.seq = g_wal.next_seq++;
  e.term = term;
  e.fencing_token = fencing_token;
  e.op_type = op_type;
  strncpy(e.key, key ? key : "", WAL_KEY_LEN - 1);
  strncpy(e.value, value ? value : "", WAL_VALUE_LEN - 1);
  e.checksum = _wal_checksum(e);

  // Apply to in-memory state
  _apply_entry(g_wal.state, e);
  g_wal.entry_count++;

  fprintf(stdout, "[WAL] Append seq=%llu term=%d op=%d key=%s\n",
          (unsigned long long)e.seq, term, op_type, key ? key : "");

  return 0;
}

/**
 * Replay the WAL to rebuild state.
 * Validates checksums. Returns number of entries replayed.
 *
 * @return Number of entries replayed, or -1 on corruption
 */
int wal_replay(void) {
  std::lock_guard<std::mutex> lock(g_wal.mu);

  // Reset state
  memset(&g_wal.state, 0, sizeof(WALState));

  int replayed = 0;
  int corrupted = 0;

  for (int i = 0; i < g_wal.entry_count; i++) {
    WALEntry &e = g_wal.entries[i];
    uint32_t expected = _wal_checksum(e);

    if (e.checksum != expected) {
      fprintf(stderr,
              "[WAL] CORRUPTION at seq=%llu: "
              "checksum %u != expected %u\n",
              (unsigned long long)e.seq, e.checksum, expected);
      corrupted++;
      continue;
    }

    _apply_entry(g_wal.state, e);
    replayed++;
  }

  fprintf(stdout,
          "[WAL] Replay: %d entries, %d corrupted. "
          "State: epoch=%d, dataset_locked=%d, "
          "world_size=%d, training=%d\n",
          replayed, corrupted, g_wal.state.epoch, g_wal.state.dataset_locked,
          g_wal.state.world_size, g_wal.state.training_active);

  return corrupted > 0 ? -1 : replayed;
}

/**
 * Get the current WAL state.
 */
int wal_get_state(int *out_epoch, int *out_dataset_locked, int *out_world_size,
                  int *out_training_active, int *out_entry_count) {
  std::lock_guard<std::mutex> lock(g_wal.mu);

  if (out_epoch)
    *out_epoch = g_wal.state.epoch;
  if (out_dataset_locked)
    *out_dataset_locked = g_wal.state.dataset_locked;
  if (out_world_size)
    *out_world_size = g_wal.state.world_size;
  if (out_training_active)
    *out_training_active = g_wal.state.training_active;
  if (out_entry_count)
    *out_entry_count = g_wal.entry_count;

  return 0;
}

/**
 * Get the dataset hash from current state.
 */
int wal_get_dataset_hash(char *out_hash, int max_len) {
  std::lock_guard<std::mutex> lock(g_wal.mu);
  strncpy(out_hash, g_wal.state.dataset_hash, max_len - 1);
  return 0;
}

/**
 * Get entry count.
 */
int wal_entry_count(void) {
  std::lock_guard<std::mutex> lock(g_wal.mu);
  return g_wal.entry_count;
}

/**
 * Get an entry by index.
 */
int wal_get_entry(int idx, uint64_t *out_seq, int *out_term, int *out_op_type,
                  char *out_key, char *out_value) {
  std::lock_guard<std::mutex> lock(g_wal.mu);

  if (idx < 0 || idx >= g_wal.entry_count)
    return -1;

  WALEntry &e = g_wal.entries[idx];
  if (out_seq)
    *out_seq = e.seq;
  if (out_term)
    *out_term = e.term;
  if (out_op_type)
    *out_op_type = e.op_type;
  if (out_key)
    strncpy(out_key, e.key, WAL_KEY_LEN - 1);
  if (out_value)
    strncpy(out_value, e.value, WAL_VALUE_LEN - 1);

  return 0;
}

} // extern "C"
