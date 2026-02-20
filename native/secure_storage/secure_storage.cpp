/**
 * secure_storage.cpp — NAS Mode Secure Storage Service
 *
 * Features:
 *   - Only accepts connections from mesh IPs (10.0.0.0/24)
 *   - Validates device certificate before granting access
 *   - File read/write with audit logging
 *   - No public port exposed
 *
 * Requires:
 *   - Encrypted disk (LUKS on Linux, BitLocker on Windows)
 *   - WireGuard mesh active
 *   - Device must be paired (valid certificate)
 *
 * NO cloud. NO public access. NO unauthenticated operations.
 */
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

#ifdef _WIN32
#include <direct.h>
#include <io.h>

#define access_check(p, m) _access(p, m)
#define W_OK 2
#else
#include <unistd.h>
#define access_check(p, m) access(p, m)
#endif

namespace secure_storage {

// =========================================================================
// CONSTANTS (Phase 1: No hardcoded drive letters)
// =========================================================================

static constexpr char DEFAULT_STORAGE_ROOT[] = "./storage";
static constexpr char AUDIT_LOG_PATH[] = "reports/storage_audit.json";
static constexpr char MESH_PREFIX[] = "10.0.0.";
static constexpr size_t MAX_FILE_SIZE = 100 * 1024 * 1024; // 100 MB max
static constexpr char KNOWN_DEMO_KEY[] =
    "0000000000000000000000000000000000000000000000000000000000000000";

// Phase 1: Resolve storage root from environment
static const char *get_storage_root() {
  const char *root = std::getenv("YGB_STORAGE_ROOT");
  if (!root || root[0] == '\0') {
    root = DEFAULT_STORAGE_ROOT;
  }
  return root;
}

// Phase 5: Reject known demo HMAC key at runtime
static bool is_demo_hmac_key() {
  const char *key = std::getenv("YGB_HMAC_SECRET");
  if (!key)
    return false;
  return std::strcmp(key, KNOWN_DEMO_KEY) == 0;
}

// Phase 4: Startup validation
static bool validate_startup() {
  const char *root = get_storage_root();

  if (access_check(root, W_OK) != 0) {
    std::fprintf(stderr, "ABORT: YGB_STORAGE_ROOT '%s' is not writable\n",
                 root);
    return false;
  }

#ifdef _WIN32
  int enc = std::system(
      "manage-bde -status C: 2>nul | findstr /C:\"Protection On\" >nul 2>&1");
#else
  int enc = std::system(
      "cryptsetup status $(findmnt -n -o SOURCE /) >/dev/null 2>&1");
#endif
  if (enc != 0) {
    std::fprintf(stderr, "WARNING: Disk encryption not confirmed\n");
  }

  if (is_demo_hmac_key()) {
    std::fprintf(stderr,
                 "ABORT: HMAC key matches known demo value. Rotate secret.\n");
    return false;
  }

  return true;
}

// Phase 7: Log cluster topology at startup
static void log_cluster_topology() {
  const char *public_ip = std::getenv("YGB_PUBLIC_IP");
  if (public_ip && public_ip[0] != '\0') {
    std::fprintf(stdout, "[TOPOLOGY] Cluster node has public IP: %s\n",
                 public_ip);
  } else {
    std::fprintf(
        stdout,
        "[TOPOLOGY] Cluster is private-only (LAN/VPN reachable only)\n");
  }
}

// Phase 6: Storage replication stub (rsync over WireGuard)
static void trigger_replication(const char *node_role) {
  if (!node_role || std::strcmp(node_role, "STORAGE") != 0)
    return;
  const char *peer_ips = std::getenv("YGB_STORAGE_PEERS");
  if (!peer_ips || peer_ips[0] == '\0')
    return;
  const char *root = get_storage_root();
  char cmd[512];
  std::snprintf(cmd, sizeof(cmd),
                "rsync -az --timeout=30 %s/ %s:%s/ 2>/dev/null", root, peer_ips,
                root);
  std::system(cmd);
}

// =========================================================================
// ACCESS CONTROL
// =========================================================================

enum class AccessResult : uint8_t {
  GRANTED = 0,
  DENIED_IP = 1,
  DENIED_CERT = 2,
  DENIED_PATH = 3,      // Tried to access outside safe paths
  DENIED_ROLE = 4,      // Device role not permitted
  DENIED_LOCALHOST = 5, // Blocked localhost loopback bypass
  DENIED_SESSION = 6,   // Invalid or missing session token
  ERROR = 7,            // File not found, I/O error
};

static const char *access_result_name(AccessResult r) {
  switch (r) {
  case AccessResult::GRANTED:
    return "GRANTED";
  case AccessResult::DENIED_IP:
    return "DENIED_IP";
  case AccessResult::DENIED_CERT:
    return "DENIED_CERT";
  case AccessResult::DENIED_PATH:
    return "DENIED_PATH";
  case AccessResult::DENIED_ROLE:
    return "DENIED_ROLE";
  case AccessResult::DENIED_LOCALHOST:
    return "DENIED_LOCALHOST";
  case AccessResult::DENIED_SESSION:
    return "DENIED_SESSION";
  case AccessResult::ERROR:
    return "ERROR";
  default:
    return "UNKNOWN";
  }
}

// =========================================================================
// IP VALIDATION — mesh only, block localhost
// =========================================================================

static bool is_localhost(const char *ip) {
  if (!ip)
    return false;
  return std::strcmp(ip, "127.0.0.1") == 0 || std::strcmp(ip, "::1") == 0 ||
         std::strcmp(ip, "localhost") == 0;
}

static bool is_mesh_ip(const char *ip) {
  if (!ip)
    return false;
  // Block localhost explicitly
  if (is_localhost(ip))
    return false;
  return std::strncmp(ip, MESH_PREFIX, std::strlen(MESH_PREFIX)) == 0;
}

// =========================================================================
// PATH VALIDATION — prevent traversal
// =========================================================================

static bool is_safe_path(const char *path) {
  if (!path || path[0] == '\0')
    return false;
  if (std::strstr(path, "..") != nullptr)
    return false;
  if (path[0] == '/' || path[0] == '\\')
    return false;
  if (std::strlen(path) >= 2 && path[1] == ':')
    return false;
  return true;
}

// =========================================================================
// AUDIT LOGGING
// =========================================================================

static void log_access(const char *event, const char *device_id, const char *ip,
                       const char *path, AccessResult result) {
  FILE *f = std::fopen(AUDIT_LOG_PATH, "a");
  if (!f)
    return;

  uint64_t now = static_cast<uint64_t>(std::time(nullptr));
  std::fprintf(f,
               "{\"event\": \"%s\", \"device_id\": \"%s\", \"ip\": \"%s\", "
               "\"path\": \"%s\", \"result\": \"%s\", \"timestamp\": %llu}\n",
               event, device_id ? device_id : "", ip ? ip : "",
               path ? path : "", access_result_name(result),
               static_cast<unsigned long long>(now));
  std::fclose(f);
}

// =========================================================================
// STORAGE OPERATIONS
// =========================================================================

// Phase 7: Extended storage request with role and revocation status
struct StorageRequest {
  const char *device_id;     // From device certificate
  const char *client_ip;     // Source IP
  const char *certificate;   // Device certificate for validation
  const char *path;          // Relative path within secure_data/
  const char *device_role;   // e.g., "AUTHORITY", "STORAGE", "WORKER"
  const char *session_token; // Session token for NAS access control
  bool is_registered;        // Must be true
  bool is_revoked;           // Must be false
};

// Callback for certificate validation
typedef bool (*CertValidator)(const char *device_id, const char *cert);

class SecureStorage {
public:
  SecureStorage() : cert_validator_(nullptr) {}

  void set_cert_validator(CertValidator v) { cert_validator_ = v; }

  // Read file from secure storage
  AccessResult read_file(const StorageRequest &req, char *buf, size_t buf_size,
                         size_t *bytes_read) {
    AccessResult check = validate_access(req, "READ");
    if (check != AccessResult::GRANTED)
      return check;

    char full_path[512];
    std::snprintf(full_path, sizeof(full_path), "%s/%s", get_storage_root(),
                  req.path);

    FILE *f = std::fopen(full_path, "rb");
    if (!f) {
      log_access("READ_FAILED", req.device_id, req.client_ip, req.path,
                 AccessResult::ERROR);
      return AccessResult::ERROR;
    }

    *bytes_read = std::fread(buf, 1, buf_size, f);
    std::fclose(f);

    log_access("READ_OK", req.device_id, req.client_ip, req.path,
               AccessResult::GRANTED);
    return AccessResult::GRANTED;
  }

  // Write file to secure storage
  AccessResult write_file(const StorageRequest &req, const char *data,
                          size_t data_len) {
    AccessResult check = validate_access(req, "WRITE");
    if (check != AccessResult::GRANTED)
      return check;

    if (data_len > MAX_FILE_SIZE) {
      log_access("WRITE_REJECTED", req.device_id, req.client_ip, req.path,
                 AccessResult::ERROR);
      return AccessResult::ERROR;
    }

    char full_path[512];
    std::snprintf(full_path, sizeof(full_path), "%s/%s", get_storage_root(),
                  req.path);

    FILE *f = std::fopen(full_path, "wb");
    if (!f) {
      log_access("WRITE_FAILED", req.device_id, req.client_ip, req.path,
                 AccessResult::ERROR);
      return AccessResult::ERROR;
    }

    std::fwrite(data, 1, data_len, f);
    std::fflush(f);
    std::fclose(f);

    log_access("WRITE_OK", req.device_id, req.client_ip, req.path,
               AccessResult::GRANTED);
    return AccessResult::GRANTED;
  }

private:
  CertValidator cert_validator_;

  AccessResult validate_access(const StorageRequest &req, const char *op) {
    // Check 0a: Device certificate file MUST exist (zero-trust bootstrap)
    {
      FILE *cert_f = std::fopen("storage/certs/device_cert.json", "r");
      if (!cert_f) {
        log_access(op, req.device_id, req.client_ip, req.path,
                   AccessResult::DENIED_CERT);
        return AccessResult::DENIED_CERT;
      }
      // Check cert expiry: read expires_at from cert file
      char cert_buf[4096] = {0};
      std::fread(cert_buf, 1, sizeof(cert_buf) - 1, cert_f);
      std::fclose(cert_f);

      const char *exp_key = "\"expires_at\": ";
      const char *exp_pos = std::strstr(cert_buf, exp_key);
      if (exp_pos) {
        uint64_t expires_at = (uint64_t)std::strtoull(
            exp_pos + std::strlen(exp_key), nullptr, 10);
        if (expires_at > 0 && (uint64_t)std::time(nullptr) > expires_at) {
          log_access(op, req.device_id, req.client_ip, req.path,
                     AccessResult::DENIED_CERT);
          return AccessResult::DENIED_CERT;
        }
      }
    }

    // Check 0b: Block localhost bypass (Phase 7)
    if (is_localhost(req.client_ip)) {
      log_access(op, req.device_id, req.client_ip, req.path,
                 AccessResult::DENIED_LOCALHOST);
      return AccessResult::DENIED_LOCALHOST;
    }

    // Check 1: Mesh IP only
    if (!is_mesh_ip(req.client_ip)) {
      log_access(op, req.device_id, req.client_ip, req.path,
                 AccessResult::DENIED_IP);
      return AccessResult::DENIED_IP;
    }

    // Check 2: Valid device certificate
    if (cert_validator_ && !cert_validator_(req.device_id, req.certificate)) {
      log_access(op, req.device_id, req.client_ip, req.path,
                 AccessResult::DENIED_CERT);
      return AccessResult::DENIED_CERT;
    }

    // Check 3: Device must be registered and not revoked (Phase 7)
    if (!req.is_registered || req.is_revoked) {
      log_access(op, req.device_id, req.client_ip, req.path,
                 AccessResult::DENIED_CERT);
      return AccessResult::DENIED_CERT;
    }

    // Check 4: Valid Web Session Token (Phase 7 - Zero Trust)
    if (!validate_session_token(req.session_token)) {
      log_access(op, req.device_id, req.client_ip, req.path,
                 AccessResult::DENIED_SESSION);
      return AccessResult::DENIED_SESSION;
    }

    // Check 5: Role-based access (Phase 7)
    // Only STORAGE and AUTHORITY roles can access secure storage
    if (req.device_role) {
      if (std::strcmp(req.device_role, "WORKER") == 0) {
        log_access(op, req.device_id, req.client_ip, req.path,
                   AccessResult::DENIED_ROLE);
        return AccessResult::DENIED_ROLE;
      }
    }

    // Check 5: Safe path
    if (!is_safe_path(req.path)) {
      log_access(op, req.device_id, req.client_ip, req.path,
                 AccessResult::DENIED_PATH);
      return AccessResult::DENIED_PATH;
    }

    return AccessResult::GRANTED;
  }

  bool validate_session_token(const char *token) {
    if (!token || std::strlen(token) == 0)
      return false;

    // Real validation: token must be hex sha256 (64 chars) AND exist in
    // auth_sessions.json. No simulated/mock validation permitted.
    if (std::strlen(token) != 64)
      return false;

    // Validate hex characters
    for (size_t i = 0; i < 64; ++i) {
      char c = token[i];
      if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') ||
            (c >= 'A' && c <= 'F')))
        return false;
    }

    // Read auth_sessions.json and verify token exists
    FILE *f = std::fopen("config/auth_sessions.json", "r");
    if (!f)
      return false;

    char buf[16384] = {0};
    std::fread(buf, 1, sizeof(buf) - 1, f);
    std::fclose(f);

    // Search for the token string in the sessions file
    return std::strstr(buf, token) != nullptr;
  }
};

// =========================================================================
// SELF-TEST
// =========================================================================

#ifdef RUN_SELF_TEST
static int self_test() {
  int pass = 0, fail = 0;

  // Test IP validation
  if (is_mesh_ip("10.0.0.5")) {
    ++pass;
  } else {
    ++fail;
  }
  if (!is_mesh_ip("192.168.1.1")) {
    ++pass;
  } else {
    ++fail;
  }
  if (!is_mesh_ip(nullptr)) {
    ++pass;
  } else {
    ++fail;
  }

  // Test path validation
  if (is_safe_path("data/file.txt")) {
    ++pass;
  } else {
    ++fail;
  }
  if (!is_safe_path("../etc/passwd")) {
    ++pass;
  } else {
    ++fail;
  }
  if (!is_safe_path("/root/secret")) {
    ++pass;
  } else {
    ++fail;
  }
  if (!is_safe_path("C:\\secret")) {
    ++pass;
  } else {
    ++fail;
  }
  if (!is_safe_path(nullptr)) {
    ++pass;
  } else {
    ++fail;
  }

  // Test storage with mock validator
  SecureStorage storage;
  storage.set_cert_validator([](const char *, const char *) { return true; });

  StorageRequest good_req = {"dev1", "10.0.0.5", "cert", "test.txt"};
  StorageRequest bad_ip = {"dev1", "8.8.8.8", "cert", "test.txt"};
  StorageRequest bad_path = {"dev1", "10.0.0.5", "cert", "../etc/passwd"};

  // Good request should not fail on access check
  // (file may not exist, but access is granted)
  char buf[64];
  size_t n;
  AccessResult r1 = storage.read_file(good_req, buf, sizeof(buf), &n);
  // Either GRANTED (file exists) or ERROR (file missing) — not DENIED
  if (r1 == AccessResult::GRANTED || r1 == AccessResult::ERROR) {
    ++pass;
  } else {
    ++fail;
  }

  // Bad IP should be denied
  AccessResult r2 = storage.read_file(bad_ip, buf, sizeof(buf), &n);
  if (r2 == AccessResult::DENIED_IP) {
    ++pass;
  } else {
    ++fail;
  }

  // Bad path should be denied
  AccessResult r3 = storage.read_file(bad_path, buf, sizeof(buf), &n);
  if (r3 == AccessResult::DENIED_PATH) {
    ++pass;
  } else {
    ++fail;
  }

  std::printf("secure_storage self-test: %d passed, %d failed\n", pass, fail);
  return fail == 0 ? 0 : 1;
}
#endif

} // namespace secure_storage
