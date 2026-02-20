/**
 * training_gate.cpp — Training Start Final Check (Phase 8)
 *
 * 8-point preflight before allowing MODE_A:
 *   1. Storage accessible
 *   2. Heartbeat quorum valid
 *   3. WireGuard active
 *   4. Device registered
 *   5. HMAC version correct
 *   6. Disk encryption confirmed
 *   7. CPU/GPU thermal < threshold
 *   8. Governance lock false
 *
 * All checks must pass. Fail-closed on any failure.
 */

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#ifdef _WIN32
#include <io.h>
#define access_check(p, m) _access(p, m)
#define W_OK 2
#else
#include <unistd.h>
#define access_check(p, m) access(p, m)
#endif

namespace training_gate {

static constexpr uint32_t EXPECTED_HMAC_VERSION = 3;
static constexpr double MAX_GPU_TEMP = 90.0;
static constexpr double MAX_CPU_TEMP = 95.0;

struct PreflightResult {
  bool storage_accessible;
  bool heartbeat_quorum;
  bool wireguard_active;
  bool device_registered;
  bool hmac_version_ok;
  bool disk_encrypted;
  bool thermal_ok;
  bool governance_unlocked;

  bool all_passed() const {
    return storage_accessible && heartbeat_quorum && wireguard_active &&
           device_registered && hmac_version_ok && disk_encrypted &&
           thermal_ok && governance_unlocked;
  }
};

// =========================================================================
// INDIVIDUAL CHECKS
// =========================================================================

static bool check_storage_accessible() {
  const char *root = std::getenv("YGB_STORAGE_ROOT");
  if (!root || root[0] == '\0')
    root = "./storage";
  return access_check(root, W_OK) == 0;
}

static bool check_heartbeat_quorum() {
  const char *quorum_file = "reports/heartbeat_quorum.json";
  FILE *f = std::fopen(quorum_file, "r");
  if (f) {
    std::fclose(f);
    return true;
  }
  return false;
}

static bool check_wireguard_active() {
#ifdef _WIN32
  int r = std::system(
      "sc query WireGuardTunnel$wg0 2>nul | findstr /C:\"RUNNING\" >nul 2>&1");
#else
  int r = std::system("wg show wg0 >/dev/null 2>&1");
#endif
  return r == 0;
}

static bool check_device_registered() {
  const char *dev_file = "config/device_identity.json";
  FILE *f = std::fopen(dev_file, "r");
  if (f) {
    std::fclose(f);
    return true;
  }
  return false;
}

static bool check_hmac_version(uint32_t current_version) {
  return current_version == EXPECTED_HMAC_VERSION;
}

static bool check_disk_encryption() {
#ifdef _WIN32
  int r = std::system(
      "manage-bde -status C: 2>nul | findstr /C:\"Protection On\" >nul 2>&1");
#else
  int r = std::system(
      "cryptsetup status $(findmnt -n -o SOURCE /) >/dev/null 2>&1");
#endif
  return r == 0;
}

static bool check_thermal(double gpu_temp, double cpu_temp) {
  return gpu_temp < MAX_GPU_TEMP && cpu_temp < MAX_CPU_TEMP;
}

static bool check_governance_unlocked() {
  const char *lock_file = "config/governance_lock.json";
  FILE *f = std::fopen(lock_file, "r");
  if (!f)
    return true;

  char buf[128] = {0};
  std::fread(buf, 1, sizeof(buf) - 1, f);
  std::fclose(f);

  if (std::strstr(buf, "\"locked\": true") ||
      std::strstr(buf, "\"locked\":true")) {
    return false;
  }
  return true;
}

// =========================================================================
// MAIN PREFLIGHT
// =========================================================================

static PreflightResult run_preflight(uint32_t hmac_version, double gpu_temp,
                                     double cpu_temp) {
  PreflightResult result;
  result.storage_accessible = check_storage_accessible();
  result.heartbeat_quorum = check_heartbeat_quorum();
  result.wireguard_active = check_wireguard_active();
  result.device_registered = check_device_registered();
  result.hmac_version_ok = check_hmac_version(hmac_version);
  result.disk_encrypted = check_disk_encryption();
  result.thermal_ok = check_thermal(gpu_temp, cpu_temp);
  result.governance_unlocked = check_governance_unlocked();
  return result;
}

static void log_preflight(const PreflightResult &r) {
  std::fprintf(stdout, "[TRAINING GATE] Preflight Results:\n");
  std::fprintf(stdout, "  Storage accessible:  %s\n",
               r.storage_accessible ? "PASS" : "FAIL");
  std::fprintf(stdout, "  Heartbeat quorum:    %s\n",
               r.heartbeat_quorum ? "PASS" : "FAIL");
  std::fprintf(stdout, "  WireGuard active:    %s\n",
               r.wireguard_active ? "PASS" : "FAIL");
  std::fprintf(stdout, "  Device registered:   %s\n",
               r.device_registered ? "PASS" : "FAIL");
  std::fprintf(stdout, "  HMAC version:        %s\n",
               r.hmac_version_ok ? "PASS" : "FAIL");
  std::fprintf(stdout, "  Disk encryption:     %s\n",
               r.disk_encrypted ? "PASS" : "FAIL");
  std::fprintf(stdout, "  Thermal limits:      %s\n",
               r.thermal_ok ? "PASS" : "FAIL");
  std::fprintf(stdout, "  Governance unlocked: %s\n",
               r.governance_unlocked ? "PASS" : "FAIL");
  std::fprintf(stdout, "  OVERALL:             %s\n",
               r.all_passed() ? "MODE_A ALLOWED" : "MODE_A BLOCKED");
}

} // namespace training_gate
