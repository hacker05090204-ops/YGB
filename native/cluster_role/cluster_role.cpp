/**
 * cluster_role.cpp — Storage Node Role Enforcement (Phase 3)
 *
 * Enforces role-based access control for storage operations:
 *   - WORKER  → All storage requests DENIED
 *   - AUTHORITY → Read-only storage access
 *   - STORAGE → Full read/write access
 *
 * C++ handles runtime/security. No external bypass.
 */

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace cluster_role {

// =========================================================================
// ROLE DEFINITIONS
// =========================================================================

enum class NodeRole : uint8_t {
  UNKNOWN = 0,
  WORKER = 1,
  AUTHORITY = 2,
  STORAGE = 3,
};

enum class StoragePermission : uint8_t {
  DENIED = 0,
  READ_ONLY = 1,
  READ_WRITE = 2,
};

static const char *role_name(NodeRole r) {
  switch (r) {
  case NodeRole::WORKER:
    return "WORKER";
  case NodeRole::AUTHORITY:
    return "AUTHORITY";
  case NodeRole::STORAGE:
    return "STORAGE";
  default:
    return "UNKNOWN";
  }
}

static const char *permission_name(StoragePermission p) {
  switch (p) {
  case StoragePermission::DENIED:
    return "DENIED";
  case StoragePermission::READ_ONLY:
    return "READ_ONLY";
  case StoragePermission::READ_WRITE:
    return "READ_WRITE";
  default:
    return "UNKNOWN";
  }
}

// =========================================================================
// ROLE RESOLUTION
// =========================================================================

static NodeRole parse_role(const char *role_str) {
  if (!role_str)
    return NodeRole::UNKNOWN;
  if (std::strcmp(role_str, "WORKER") == 0)
    return NodeRole::WORKER;
  if (std::strcmp(role_str, "AUTHORITY") == 0)
    return NodeRole::AUTHORITY;
  if (std::strcmp(role_str, "STORAGE") == 0)
    return NodeRole::STORAGE;
  return NodeRole::UNKNOWN;
}

static NodeRole get_node_role() {
  const char *role_env = std::getenv("YGB_NODE_ROLE");
  return parse_role(role_env);
}

// =========================================================================
// PERMISSION ENFORCEMENT
// =========================================================================

static StoragePermission get_storage_permission(NodeRole role) {
  switch (role) {
  case NodeRole::STORAGE:
    return StoragePermission::READ_WRITE;
  case NodeRole::AUTHORITY:
    return StoragePermission::READ_ONLY;
  case NodeRole::WORKER:
    return StoragePermission::DENIED;
  default:
    return StoragePermission::DENIED;
  }
}

static bool can_read(NodeRole role) {
  StoragePermission perm = get_storage_permission(role);
  return perm == StoragePermission::READ_ONLY ||
         perm == StoragePermission::READ_WRITE;
}

static bool can_write(NodeRole role) {
  return get_storage_permission(role) == StoragePermission::READ_WRITE;
}

static bool can_host_storage(NodeRole role) {
  return role == NodeRole::STORAGE;
}

// =========================================================================
// SELF-TEST
// =========================================================================

#ifdef RUN_SELF_TEST
static int self_test() {
  int pass = 0, fail = 0;
  auto check = [&](bool cond, const char *msg) {
    if (cond) {
      ++pass;
    } else {
      ++fail;
      std::fprintf(stderr, "FAIL: %s\n", msg);
    }
  };

  check(can_read(NodeRole::STORAGE), "STORAGE can read");
  check(can_write(NodeRole::STORAGE), "STORAGE can write");
  check(can_host_storage(NodeRole::STORAGE), "STORAGE can host");

  check(can_read(NodeRole::AUTHORITY), "AUTHORITY can read");
  check(!can_write(NodeRole::AUTHORITY), "AUTHORITY cannot write");
  check(!can_host_storage(NodeRole::AUTHORITY), "AUTHORITY cannot host");

  check(!can_read(NodeRole::WORKER), "WORKER cannot read");
  check(!can_write(NodeRole::WORKER), "WORKER cannot write");
  check(!can_host_storage(NodeRole::WORKER), "WORKER cannot host");

  check(parse_role("STORAGE") == NodeRole::STORAGE, "Parse STORAGE");
  check(parse_role("WORKER") == NodeRole::WORKER, "Parse WORKER");
  check(parse_role(nullptr) == NodeRole::UNKNOWN, "Parse null");

  std::printf("cluster_role self-test: %d passed, %d failed\n", pass, fail);
  return fail == 0 ? 0 : 1;
}
#endif

} // namespace cluster_role
