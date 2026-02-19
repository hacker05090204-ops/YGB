/**
 * device_registry.cpp — Scalable Device Registry (100+ devices)
 *
 * Features:
 *   - MAX_DEVICES = 128
 *   - Manages config/devices.json registry
 *   - On pairing: add entry, reject if over limit
 *   - Device status tracking (online/offline/revoked)
 *   - Persistence: atomic write to JSON file
 *
 * NO cloud. NO auto-registration. Pairing required.
 */

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>

namespace device_registry {

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int MAX_DEVICES = 128;
static constexpr char REGISTRY_PATH[] = "config/devices.json";
static constexpr char REGISTRY_TMP[] = "config/devices.json.tmp";

// =========================================================================
// DEVICE STATUS
// =========================================================================

enum class DeviceStatus : uint8_t {
  ONLINE = 0,
  OFFLINE = 1,
  REVOKED = 2,
};

static const char *status_name(DeviceStatus s) {
  switch (s) {
  case DeviceStatus::ONLINE:
    return "online";
  case DeviceStatus::OFFLINE:
    return "offline";
  case DeviceStatus::REVOKED:
    return "revoked";
  default:
    return "unknown";
  }
}

// =========================================================================
// DEVICE ENTRY
// =========================================================================

struct DeviceEntry {
  char device_id[65]; // SHA-256 hex
  char hostname[64];
  char mesh_ip[46];      // WireGuard IP
  char certificate[129]; // Issued on pairing
  uint64_t paired_at;
  uint64_t last_seen;
  DeviceStatus status;
  bool active;
};

// =========================================================================
// REGISTRY
// =========================================================================

class DeviceRegistry {
public:
  DeviceRegistry() : count_(0) { std::memset(devices_, 0, sizeof(devices_)); }

  // Register a new device
  // Returns slot index, or -1 on failure
  int register_device(const char *device_id, const char *hostname,
                      const char *mesh_ip, const char *certificate) {
    if (count_ >= MAX_DEVICES) {
      std::fprintf(stderr, "REGISTRY: MAX_DEVICES (%d) reached\n", MAX_DEVICES);
      return -1;
    }

    // Check for duplicate
    for (int i = 0; i < count_; ++i) {
      if (devices_[i].active &&
          std::strcmp(devices_[i].device_id, device_id) == 0) {
        // Already registered — update last_seen
        devices_[i].last_seen = static_cast<uint64_t>(std::time(nullptr));
        devices_[i].status = DeviceStatus::ONLINE;
        return i;
      }
    }

    DeviceEntry &d = devices_[count_];
    std::strncpy(d.device_id, device_id, 64);
    d.device_id[64] = '\0';
    std::strncpy(d.hostname, hostname ? hostname : "", 63);
    d.hostname[63] = '\0';
    std::strncpy(d.mesh_ip, mesh_ip ? mesh_ip : "", 45);
    d.mesh_ip[45] = '\0';
    std::strncpy(d.certificate, certificate ? certificate : "", 128);
    d.certificate[128] = '\0';
    d.paired_at = static_cast<uint64_t>(std::time(nullptr));
    d.last_seen = d.paired_at;
    d.status = DeviceStatus::ONLINE;
    d.active = true;

    return count_++;
  }

  // Revoke a device
  bool revoke_device(const char *device_id) {
    for (int i = 0; i < count_; ++i) {
      if (devices_[i].active &&
          std::strcmp(devices_[i].device_id, device_id) == 0) {
        devices_[i].status = DeviceStatus::REVOKED;
        return true;
      }
    }
    return false;
  }

  // Update last_seen timestamp
  bool heartbeat(const char *device_id) {
    for (int i = 0; i < count_; ++i) {
      if (devices_[i].active &&
          std::strcmp(devices_[i].device_id, device_id) == 0) {
        devices_[i].last_seen = static_cast<uint64_t>(std::time(nullptr));
        devices_[i].status = DeviceStatus::ONLINE;
        return true;
      }
    }
    return false;
  }

  // Check if device is registered and not revoked
  bool is_allowed(const char *device_id) const {
    for (int i = 0; i < count_; ++i) {
      if (devices_[i].active &&
          std::strcmp(devices_[i].device_id, device_id) == 0 &&
          devices_[i].status != DeviceStatus::REVOKED) {
        return true;
      }
    }
    return false;
  }

  int count() const { return count_; }
  int active_count() const {
    int c = 0;
    for (int i = 0; i < count_; ++i)
      if (devices_[i].active && devices_[i].status != DeviceStatus::REVOKED)
        ++c;
    return c;
  }

  const DeviceEntry *get(int idx) const {
    if (idx < 0 || idx >= count_)
      return nullptr;
    return &devices_[idx];
  }

  // Persist to JSON
  bool save() const {
    FILE *f = std::fopen(REGISTRY_TMP, "w");
    if (!f)
      return false;

    std::fprintf(f, "{\n  \"devices\": [\n");
    for (int i = 0; i < count_; ++i) {
      const DeviceEntry &d = devices_[i];
      if (!d.active)
        continue;
      std::fprintf(f,
                   "    {\n"
                   "      \"device_id\": \"%s\",\n"
                   "      \"hostname\": \"%s\",\n"
                   "      \"mesh_ip\": \"%s\",\n"
                   "      \"status\": \"%s\",\n"
                   "      \"paired_at\": %llu,\n"
                   "      \"last_seen\": %llu\n"
                   "    }%s\n",
                   d.device_id, d.hostname, d.mesh_ip, status_name(d.status),
                   static_cast<unsigned long long>(d.paired_at),
                   static_cast<unsigned long long>(d.last_seen),
                   (i < count_ - 1) ? "," : "");
    }
    std::fprintf(f, "  ]\n}\n");
    std::fclose(f);

    std::remove(REGISTRY_PATH);
    return std::rename(REGISTRY_TMP, REGISTRY_PATH) == 0;
  }

private:
  DeviceEntry devices_[MAX_DEVICES];
  int count_;
};

// =========================================================================
// SELF-TEST
// =========================================================================

#ifdef RUN_SELF_TEST
static int self_test() {
  int pass = 0, fail = 0;
  DeviceRegistry reg;

  // Test 1: Register device
  int idx = reg.register_device("aabbccdd", "laptop1", "10.0.0.1", "cert1");
  if (idx == 0) {
    ++pass;
  } else {
    ++fail;
  }

  // Test 2: Count
  if (reg.count() == 1) {
    ++pass;
  } else {
    ++fail;
  }

  // Test 3: Device is allowed
  if (reg.is_allowed("aabbccdd")) {
    ++pass;
  } else {
    ++fail;
  }

  // Test 4: Unknown device not allowed
  if (!reg.is_allowed("unknown")) {
    ++pass;
  } else {
    ++fail;
  }

  // Test 5: Heartbeat
  if (reg.heartbeat("aabbccdd")) {
    ++pass;
  } else {
    ++fail;
  }

  // Test 6: Revoke
  if (reg.revoke_device("aabbccdd")) {
    ++pass;
  } else {
    ++fail;
  }

  // Test 7: Revoked device not allowed
  if (!reg.is_allowed("aabbccdd")) {
    ++pass;
  } else {
    ++fail;
  }

  // Test 8: Active count after revoke
  if (reg.active_count() == 0) {
    ++pass;
  } else {
    ++fail;
  }

  // Test 9: Register up to limit
  DeviceRegistry big;
  bool all_ok = true;
  for (int i = 0; i < MAX_DEVICES; ++i) {
    char id[65];
    std::snprintf(id, sizeof(id), "device_%04d", i);
    if (big.register_device(id, "host", "10.0.0.1", "cert") < 0) {
      all_ok = false;
      break;
    }
  }
  if (all_ok && big.count() == MAX_DEVICES) {
    ++pass;
  } else {
    ++fail;
  }

  // Test 10: Reject over limit
  int over = big.register_device("overflow", "host", "10.0.0.1", "cert");
  if (over < 0) {
    ++pass;
  } else {
    ++fail;
  }

  std::printf("device_registry self-test: %d passed, %d failed\n", pass, fail);
  return fail == 0 ? 0 : 1;
}
#endif

} // namespace device_registry
