/*
 * deterministic_sync_validator.cpp — Deterministic Sync Validator (Phase 0)
 *
 * Cross-node weight hash verification.
 * Ensure all nodes have identical model weights.
 * Reject training if hash mismatch detected.
 *
 * C API for Python bridge.
 */

#include <cstdint>
#include <cstring>

#ifdef __cplusplus
extern "C" {
#endif

#define MAX_NODES 32
#define HASH_LEN 65

typedef struct {
  int node_id;
  char weight_hash[HASH_LEN];
  long timestamp;
  int synced;
} NodeState;

typedef struct {
  int total_nodes;
  int synced_nodes;
  int mismatched;
  int deterministic; /* 1 if all match */
  char master_hash[HASH_LEN];
} SyncReport;

/* Globals */
static NodeState g_nodes[MAX_NODES];
static int g_node_count = 0;
static char g_master_hash[HASH_LEN];

static void compute_hash(const char *data, int len, char *out) {
  unsigned long h1 = 5381, h2 = 0x9e3779b9;
  for (int i = 0; i < len; i++) {
    h1 = ((h1 << 5) + h1) + (unsigned char)data[i];
    h2 ^= ((h2 << 6) + (h2 >> 2) + (unsigned char)data[i]);
  }
  snprintf(out, HASH_LEN, "%016lx%016lx%016lx%016lx", h1, h2, h1 ^ h2, h1 + h2);
}

/* ---- Public API ---- */

int dsv_init(void) {
  memset(g_nodes, 0, sizeof(g_nodes));
  memset(g_master_hash, 0, sizeof(g_master_hash));
  g_node_count = 0;
  return 0;
}

int dsv_register_node(int node_id, const char *weight_data, int data_len) {
  if (g_node_count >= MAX_NODES)
    return -1;
  NodeState *n = &g_nodes[g_node_count];
  n->node_id = node_id;
  compute_hash(weight_data, data_len, n->weight_hash);
  n->synced = 0;
  g_node_count++;

  /* First node sets master hash */
  if (g_node_count == 1) {
    strncpy(g_master_hash, n->weight_hash, HASH_LEN - 1);
  }
  return 0;
}

SyncReport dsv_validate(void) {
  SyncReport r;
  memset(&r, 0, sizeof(r));
  r.total_nodes = g_node_count;
  strncpy(r.master_hash, g_master_hash, HASH_LEN - 1);

  if (g_node_count == 0)
    return r;

  int synced = 0;
  for (int i = 0; i < g_node_count; i++) {
    if (strcmp(g_nodes[i].weight_hash, g_master_hash) == 0) {
      g_nodes[i].synced = 1;
      synced++;
    }
  }

  r.synced_nodes = synced;
  r.mismatched = g_node_count - synced;
  r.deterministic = (r.mismatched == 0) ? 1 : 0;
  return r;
}

int dsv_get_node_count(void) { return g_node_count; }
int dsv_is_deterministic(void) { return dsv_validate().deterministic; }

#ifdef __cplusplus
}
#endif
