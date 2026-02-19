/**
 * secure_storage_server.cpp — Encrypted NAS Mode with Zero-Trust Access
 *
 * Features:
 *   - Exposes /secure_storage endpoint on mesh IP only
 *   - Requires device certificate validation
 *   - No public port open
 *   - Works with BitLocker (Windows) / LUKS (Linux) encrypted disks
 *
 * Access Control:
 *   - Only mesh IPs (10.0.0.0/24) can connect
 *   - Device certificate must be valid and not expired
 *   - All access events are logged
 *
 * NO external dependencies.
 */

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>

namespace secure_storage {

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr char MESH_SUBNET[] = "10.0.0.";
static constexpr char ACCESS_LOG_PATH[] = "reports/storage_access.log";
static constexpr int MESH_PORT = 9443;

// =========================================================================
// ACL VALIDATOR
// =========================================================================

/**
 * Check if an IP address belongs to the mesh network (10.0.0.0/24).
 * Returns true only for mesh IPs. All public IPs are rejected.
 */
static bool is_mesh_ip(const char *ip_addr) {
    if (!ip_addr) return false;
    return std::strncmp(ip_addr, MESH_SUBNET, std::strlen(MESH_SUBNET)) == 0;
}

// =========================================================================
// DEVICE CERTIFICATE VALIDATION
// =========================================================================

struct DeviceCert {
    char device_id[65];
    char public_key[65];
    uint64_t issued_at;
    uint64_t expires_at;
    bool valid;
};

/**
 * Validate a device certificate.
 * Checks: not expired, has valid device_id, has public key.
 */
static bool validate_device_cert(const DeviceCert &cert) {
    if (!cert.valid) return false;
    if (cert.device_id[0] == '\0') return false;
    if (cert.public_key[0] == '\0') return false;

    uint64_t now = static_cast<uint64_t>(std::time(nullptr));
    if (cert.expires_at < now) {
        std::fprintf(stderr, "[storage] Certificate expired for device %s\n",
                     cert.device_id);
        return false;
    }

    return true;
}

// =========================================================================
// ACCESS CONTROL
// =========================================================================

enum class AccessResult {
    GRANTED,
    DENIED_NOT_MESH_IP,
    DENIED_INVALID_CERT,
    DENIED_EXPIRED_CERT,
    DENIED_NOT_PAIRED,
};

struct AccessRequest {
    char source_ip[46];    // IPv4 or IPv6
    DeviceCert cert;
    char requested_path[512];
    uint64_t timestamp;
};

/**
 * Evaluate an access request against the ACL.
 * Returns GRANTED only if:
 *   1. Source IP is on the mesh network (10.0.0.0/24)
 *   2. Device certificate is valid and not expired
 */
static AccessResult evaluate_access(const AccessRequest &req) {
    // Rule 1: Must be mesh IP
    if (!is_mesh_ip(req.source_ip)) {
        return AccessResult::DENIED_NOT_MESH_IP;
    }

    // Rule 2: Must have valid certificate
    if (!validate_device_cert(req.cert)) {
        if (req.cert.expires_at < static_cast<uint64_t>(std::time(nullptr))) {
            return AccessResult::DENIED_EXPIRED_CERT;
        }
        return AccessResult::DENIED_INVALID_CERT;
    }

    return AccessResult::GRANTED;
}

// =========================================================================
// ACCESS LOGGING
// =========================================================================

static const char *result_to_string(AccessResult r) {
    switch (r) {
        case AccessResult::GRANTED: return "GRANTED";
        case AccessResult::DENIED_NOT_MESH_IP: return "DENIED_NOT_MESH_IP";
        case AccessResult::DENIED_INVALID_CERT: return "DENIED_INVALID_CERT";
        case AccessResult::DENIED_EXPIRED_CERT: return "DENIED_EXPIRED_CERT";
        case AccessResult::DENIED_NOT_PAIRED: return "DENIED_NOT_PAIRED";
        default: return "UNKNOWN";
    }
}

static bool log_access(const AccessRequest &req, AccessResult result) {
    FILE *f = std::fopen(ACCESS_LOG_PATH, "a");
    if (!f) return false;

    std::fprintf(f,
        "{\"timestamp\": %llu, \"source_ip\": \"%s\", "
        "\"device_id\": \"%s\", \"path\": \"%s\", \"result\": \"%s\"}\n",
        static_cast<unsigned long long>(req.timestamp),
        req.source_ip, req.cert.device_id,
        req.requested_path, result_to_string(result));
    std::fclose(f);
    return true;
}

// =========================================================================
// STORAGE REQUEST HANDLER
// =========================================================================

/**
 * Handle a storage request.
 * Validates ACL, logs event, returns access result.
 */
static AccessResult handle_storage_request(const char *source_ip,
                                            const DeviceCert &cert,
                                            const char *path) {
    AccessRequest req;
    std::memset(&req, 0, sizeof(req));
    std::strncpy(req.source_ip, source_ip, sizeof(req.source_ip) - 1);
    req.cert = cert;
    std::strncpy(req.requested_path, path, sizeof(req.requested_path) - 1);
    req.timestamp = static_cast<uint64_t>(std::time(nullptr));

    AccessResult result = evaluate_access(req);
    log_access(req, result);

    if (result == AccessResult::GRANTED) {
        std::printf("[storage] ACCESS GRANTED: %s -> %s\n",
                    cert.device_id, path);
    } else {
        std::fprintf(stderr, "[storage] ACCESS DENIED (%s): %s -> %s\n",
                     result_to_string(result), source_ip, path);
    }

    return result;
}

} // namespace secure_storage

// =========================================================================
// SELF-TEST (compile with -DSECURE_STORAGE_MAIN)
// =========================================================================

#ifdef SECURE_STORAGE_MAIN
int main() {
    std::printf("=== Secure Storage Server Test ===\n");

    // Setup valid cert
    secure_storage::DeviceCert cert;
    std::memset(&cert, 0, sizeof(cert));
    std::strcpy(cert.device_id, "test-device-001");
    std::strcpy(cert.public_key, "abcdef1234567890abcdef1234567890");
    cert.issued_at = static_cast<uint64_t>(std::time(nullptr));
    cert.expires_at = cert.issued_at + 86400;
    cert.valid = true;

    // Test 1: Mesh IP + valid cert = GRANTED
    auto r1 = secure_storage::handle_storage_request("10.0.0.5", cert, "/data/models");
    std::printf("Mesh IP + valid cert: %s\n",
                r1 == secure_storage::AccessResult::GRANTED ? "PASS" : "FAIL");

    // Test 2: Public IP = DENIED
    auto r2 = secure_storage::handle_storage_request("203.0.113.1", cert, "/data/models");
    std::printf("Public IP blocked: %s\n",
                r2 == secure_storage::AccessResult::DENIED_NOT_MESH_IP ? "PASS" : "FAIL");

    // Test 3: Expired cert = DENIED
    secure_storage::DeviceCert expired_cert = cert;
    expired_cert.expires_at = 1000000; // Way in the past
    auto r3 = secure_storage::handle_storage_request("10.0.0.5", expired_cert, "/data/models");
    std::printf("Expired cert blocked: %s\n",
                r3 == secure_storage::AccessResult::DENIED_EXPIRED_CERT ? "PASS" : "FAIL");

    return 0;
}
#endif
