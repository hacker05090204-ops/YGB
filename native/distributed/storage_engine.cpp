/**
 * storage_engine.cpp — Storage Health Monitor (Phase 1)
 *
 * C++ storage health engine:
 * - SMART status check (via system call)
 * - Free space monitoring
 * - Health alerts
 * - Drive classification (SSD vs HDD)
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

#define MAX_DRIVES 8
#define PATH_LEN 256
#define FREE_SPACE_MIN_GB 10 // Alert if < 10GB free
#define HEALTH_CHECK_OK 0
#define HEALTH_CHECK_WARN 1
#define HEALTH_CHECK_FAIL 2

// ============================================================================
// TYPES
// ============================================================================

enum DriveRole {
  DRIVE_ROLE_SSD_ACTIVE = 0,  // C: — active training data
  DRIVE_ROLE_NAS_ARCHIVE = 1, // D: — archive only
  DRIVE_ROLE_UNKNOWN = 2,
};

struct DriveHealth {
  char path[PATH_LEN];
  int role;
  uint64_t total_bytes;
  uint64_t free_bytes;
  float free_pct;
  int smart_ok;      // 1 = healthy, 0 = degraded
  int health_status; // HEALTH_CHECK_OK/WARN/FAIL
  char alert[256];
  long checked_at;
};

// ============================================================================
// GLOBAL STATE
// ============================================================================

static struct {
  DriveHealth drives[MAX_DRIVES];
  int drive_count;
  std::mutex mu;
  int initialized;
} g_storage = {.drive_count = 0, .initialized = 0};

static long _now_epoch() { return (long)time(NULL); }

// ============================================================================
// C API
// ============================================================================

extern "C" {

/**
 * Initialize storage engine.
 */
int storage_init(void) {
  std::lock_guard<std::mutex> lock(g_storage.mu);
  memset(g_storage.drives, 0, sizeof(g_storage.drives));
  g_storage.drive_count = 0;
  g_storage.initialized = 1;
  fprintf(stdout, "[STORAGE] Engine initialized\n");
  return 0;
}

/**
 * Register a drive for monitoring.
 *
 * @param path    Drive path (e.g. "C:\\" or "D:\\")
 * @param role    DriveRole enum
 * @return drive index, or -1 if full
 */
int storage_register_drive(const char *path, int role) {
  std::lock_guard<std::mutex> lock(g_storage.mu);

  if (g_storage.drive_count >= MAX_DRIVES)
    return -1;

  int idx = g_storage.drive_count;
  DriveHealth &d = g_storage.drives[idx];
  strncpy(d.path, path, PATH_LEN - 1);
  d.role = role;
  d.total_bytes = 0;
  d.free_bytes = 0;
  d.free_pct = 0;
  d.smart_ok = 1;
  d.health_status = HEALTH_CHECK_OK;
  memset(d.alert, 0, sizeof(d.alert));
  d.checked_at = 0;

  g_storage.drive_count++;

  fprintf(stdout, "[STORAGE] Registered drive %d: %s role=%d\n", idx, path,
          role);
  return idx;
}

/**
 * Check drive health.
 *
 * @param idx Drive index
 * @param total_bytes Total bytes on drive
 * @param free_bytes Free bytes on drive
 * @param smart_ok SMART health (1=ok, 0=degraded)
 * @return health status code
 */
int storage_check_health(int idx, uint64_t total_bytes, uint64_t free_bytes,
                         int smart_ok) {
  std::lock_guard<std::mutex> lock(g_storage.mu);

  if (idx < 0 || idx >= g_storage.drive_count)
    return -1;

  DriveHealth &d = g_storage.drives[idx];
  d.total_bytes = total_bytes;
  d.free_bytes = free_bytes;
  d.free_pct =
      total_bytes > 0 ? (float)free_bytes / (float)total_bytes * 100.0f : 0.0f;
  d.smart_ok = smart_ok;
  d.checked_at = _now_epoch();

  // Evaluate health
  float free_gb = (float)free_bytes / (1024.0f * 1024.0f * 1024.0f);

  if (!smart_ok) {
    d.health_status = HEALTH_CHECK_FAIL;
    snprintf(d.alert, 255, "CRITICAL: SMART failure on %s", d.path);
  } else if (free_gb < FREE_SPACE_MIN_GB) {
    d.health_status = HEALTH_CHECK_WARN;
    snprintf(d.alert, 255, "WARNING: Low space on %s: %.1f GB free", d.path,
             free_gb);
  } else {
    d.health_status = HEALTH_CHECK_OK;
    d.alert[0] = '\0';
  }

  if (d.alert[0]) {
    fprintf(stderr, "[STORAGE] %s\n", d.alert);
  }

  return d.health_status;
}

/**
 * Validate that no training data exists on NAS drives.
 *
 * @param has_training_data 1 if training data found on NAS, 0 if clean
 * @return 0 if valid (no training data on NAS), -1 if violation
 */
int storage_validate_nas_clean(int drive_idx, int has_training_data) {
  std::lock_guard<std::mutex> lock(g_storage.mu);

  if (drive_idx < 0 || drive_idx >= g_storage.drive_count)
    return -1;

  DriveHealth &d = g_storage.drives[drive_idx];
  if (d.role == DRIVE_ROLE_NAS_ARCHIVE && has_training_data) {
    d.health_status = HEALTH_CHECK_FAIL;
    snprintf(d.alert, 255, "VIOLATION: Training data found on NAS drive %s",
             d.path);
    fprintf(stderr, "[STORAGE] %s\n", d.alert);
    return -1;
  }
  return 0;
}

/**
 * Get drive health info.
 */
int storage_get_health(int idx, char *out_path, int *out_role,
                       uint64_t *out_total, uint64_t *out_free, int *out_smart,
                       int *out_status, char *out_alert) {
  std::lock_guard<std::mutex> lock(g_storage.mu);
  if (idx < 0 || idx >= g_storage.drive_count)
    return -1;

  DriveHealth &d = g_storage.drives[idx];
  if (out_path)
    strncpy(out_path, d.path, PATH_LEN - 1);
  if (out_role)
    *out_role = d.role;
  if (out_total)
    *out_total = d.total_bytes;
  if (out_free)
    *out_free = d.free_bytes;
  if (out_smart)
    *out_smart = d.smart_ok;
  if (out_status)
    *out_status = d.health_status;
  if (out_alert)
    strncpy(out_alert, d.alert, 255);

  return 0;
}

int storage_drive_count(void) {
  std::lock_guard<std::mutex> lock(g_storage.mu);
  return g_storage.drive_count;
}

} // extern "C"
