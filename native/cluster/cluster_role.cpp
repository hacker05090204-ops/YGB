/**
 * cluster_role.cpp — Cluster Role Assignment System
 *
 * Each node is assigned one of:
 *   AUTHORITY — handles pairing, device registry, root cert
 *   STORAGE   — hosts secure_storage, replicates to other STORAGE nodes
 *   WORKER    — training compute only, no admin authority
 *
 * Persisted to config/cluster_role.json.
 * NO single point of failure — multiple AUTHORITY nodes allowed.
 */

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>

namespace cluster_role {

// =========================================================================
// ROLE TYPES
// =========================================================================

enum class Role : uint8_t {
  AUTHORITY = 0,
  STORAGE = 1,
  WORKER = 2,
  UNASSIGNED = 255,
};

static const char *role_name(Role r) {
  switch (r) {
  case Role::AUTHORITY:
    return "AUTHORITY";
  case Role::STORAGE:
    return "STORAGE";
  case Role::WORKER:
    return "WORKER";
  case Role::UNASSIGNED:
    return "UNASSIGNED";
  default:
    return "UNKNOWN";
  }
}

static Role parse_role(const char *name) {
  if (!name)
    return Role::UNASSIGNED;
  if (std::strcmp(name, "AUTHORITY") == 0)
    return Role::AUTHORITY;
  if (std::strcmp(name, "STORAGE") == 0)
    return Role::STORAGE;
  if (std::strcmp(name, "WORKER") == 0)
    return Role::WORKER;
  return Role::UNASSIGNED;
}

// =========================================================================
// ROLE PERMISSIONS
// =========================================================================

struct RolePermissions {
  bool can_pair;            // Issue pairing tokens
  bool can_manage_registry; // Add/revoke devices
  bool can_store;           // Host secure_storage
  bool can_replicate;       // Replicate data to peers
  bool can_train;           // Execute training compute
};

static RolePermissions get_permissions(Role r) {
  switch (r) {
  case Role::AUTHORITY:
    return {true, true, false, false, false};
  case Role::STORAGE:
    return {false, false, true, true, false};
  case Role::WORKER:
    return {false, false, false, false, true};
  default:
    return {false, false, false, false, false};
  }
}

// =========================================================================
// NODE ROLE STATE
// =========================================================================

static constexpr char ROLE_PATH[] = "config/cluster_role.json";

struct NodeRoleState {
  Role role;
  char device_id[65];
  char mesh_ip[46];
  uint64_t assigned_at;
  bool loaded;
};

static NodeRoleState g_node_role = {Role::UNASSIGNED, {}, {}, 0, false};

// =========================================================================
// PERSISTENCE
// =========================================================================

static bool save_role(const NodeRoleState &state) {
  FILE *f = std::fopen(ROLE_PATH, "w");
  if (!f)
    return false;
  std::fprintf(f,
               "{\n"
               "  \"role\": \"%s\",\n"
               "  \"device_id\": \"%s\",\n"
               "  \"mesh_ip\": \"%s\",\n"
               "  \"assigned_at\": %llu\n"
               "}\n",
               role_name(state.role), state.device_id, state.mesh_ip,
               static_cast<unsigned long long>(state.assigned_at));
  std::fclose(f);
  return true;
}

static bool load_role(NodeRoleState &state) {
  FILE *f = std::fopen(ROLE_PATH, "r");
  if (!f)
    return false;

  char buf[1024];
  std::memset(buf, 0, sizeof(buf));
  std::fread(buf, 1, sizeof(buf) - 1, f);
  std::fclose(f);

  // Parse role
  const char *rp = std::strstr(buf, "\"role\"");
  if (!rp)
    return false;
  const char *q1 = std::strchr(rp + 6, '"');
  if (!q1)
    return false;
  q1++;
  const char *q2 = std::strchr(q1, '"');
  if (!q2)
    return false;
  char role_str[32] = {};
  size_t len = static_cast<size_t>(q2 - q1);
  if (len >= sizeof(role_str))
    return false;
  std::memcpy(role_str, q1, len);
  state.role = parse_role(role_str);
  state.loaded = true;
  return true;
}

// =========================================================================
// PUBLIC API
// =========================================================================

static bool assign_role(Role role, const char *device_id, const char *mesh_ip) {
  g_node_role.role = role;
  std::strncpy(g_node_role.device_id, device_id ? device_id : "", 64);
  g_node_role.device_id[64] = '\0';
  std::strncpy(g_node_role.mesh_ip, mesh_ip ? mesh_ip : "", 45);
  g_node_role.mesh_ip[45] = '\0';
  g_node_role.assigned_at = static_cast<uint64_t>(std::time(nullptr));
  g_node_role.loaded = true;
  return save_role(g_node_role);
}

static Role get_role() {
  if (!g_node_role.loaded) {
    load_role(g_node_role);
  }
  return g_node_role.role;
}

static bool can_pair() { return get_permissions(get_role()).can_pair; }
static bool can_train() { return get_permissions(get_role()).can_train; }
static bool can_store() { return get_permissions(get_role()).can_store; }

// =========================================================================
// CLUSTER QUORUM CHECK
// =========================================================================

struct ClusterQuorum {
  int authority_count;
  int storage_count;
  int worker_count;
  bool has_quorum;
};

// Call with device registry roles to check quorum
static ClusterQuorum check_quorum(const Role *roles, int count) {
  ClusterQuorum q = {0, 0, 0, false};
  for (int i = 0; i < count; ++i) {
    switch (roles[i]) {
    case Role::AUTHORITY:
      q.authority_count++;
      break;
    case Role::STORAGE:
      q.storage_count++;
      break;
    case Role::WORKER:
      q.worker_count++;
      break;
    default:
      break;
    }
  }
  q.has_quorum = (q.authority_count >= 1) && (q.storage_count >= 1) &&
                 (q.worker_count >= 1);
  return q;
}

// =========================================================================
// REPLICATION TRIGGER (for STORAGE nodes)
// =========================================================================

struct ReplicationState {
  uint64_t last_replicated;
  int replication_count;
  bool active;
};

static ReplicationState g_replication = {0, 0, false};
static constexpr int REPLICATION_INTERVAL_SEC = 60;

// Returns true if replication should trigger
static bool should_replicate() {
  if (get_role() != Role::STORAGE)
    return false;
  uint64_t now = static_cast<uint64_t>(std::time(nullptr));
  return (now - g_replication.last_replicated) >= REPLICATION_INTERVAL_SEC;
}

static void mark_replicated() {
  g_replication.last_replicated = static_cast<uint64_t>(std::time(nullptr));
  g_replication.replication_count++;
  g_replication.active = true;
}

// =========================================================================
// SELF-TEST
// =========================================================================

#ifdef RUN_SELF_TEST
static int self_test() {
  int pass = 0, fail = 0;

  // Test permissions
  auto ap = get_permissions(Role::AUTHORITY);
  if (ap.can_pair && ap.can_manage_registry && !ap.can_train) {
    ++pass;
  } else {
    ++fail;
  }

  auto sp = get_permissions(Role::STORAGE);
  if (sp.can_store && sp.can_replicate && !sp.can_pair) {
    ++pass;
  } else {
    ++fail;
  }

  auto wp = get_permissions(Role::WORKER);
  if (wp.can_train && !wp.can_pair && !wp.can_store) {
    ++pass;
  } else {
    ++fail;
  }

  // Test quorum
  Role roles1[] = {Role::AUTHORITY, Role::STORAGE, Role::WORKER};
  auto q1 = check_quorum(roles1, 3);
  if (q1.has_quorum) {
    ++pass;
  } else {
    ++fail;
  }

  Role roles2[] = {Role::WORKER, Role::WORKER};
  auto q2 = check_quorum(roles2, 2);
  if (!q2.has_quorum) {
    ++pass;
  } else {
    ++fail;
  }

  // Test role parse
  if (parse_role("AUTHORITY") == Role::AUTHORITY) {
    ++pass;
  } else {
    ++fail;
  }
  if (parse_role("WORKER") == Role::WORKER) {
    ++pass;
  } else {
    ++fail;
  }
  if (parse_role("INVALID") == Role::UNASSIGNED) {
    ++pass;
  } else {
    ++fail;
  }

  std::printf("cluster_role self-test: %d passed, %d failed\n", pass, fail);
  return fail == 0 ? 0 : 1;
}
#endif

} // namespace cluster_role
