/**
 * nas_service.cpp — NAS Service Mode (Phase 4)
 *
 * D-drive as secure archive server:
 * - Only archive shards + videos
 * - No active training shards
 * - TLS-ready config
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

#define NAS_MAX_FILES 10000
#define NAS_PATH_LEN 512
#define NAS_PORT_DEFAULT 8443

// ============================================================================
// TYPES
// ============================================================================

enum NASFileType {
  NAS_ARCHIVE_SHARD = 0,
  NAS_VIDEO = 1,
  NAS_REPORT = 2,
  NAS_BACKUP = 3,
  NAS_FORBIDDEN = 99, // Active training data
};

struct NASFile {
  char path[NAS_PATH_LEN];
  int file_type;
  uint64_t size_bytes;
  char shard_id[65]; // If archive shard
  long added_at;
};

struct NASConfig {
  char root_path[NAS_PATH_LEN];
  int port;
  int tls_enabled;
  uint64_t max_capacity_bytes;
  uint64_t used_bytes;
  int file_count;
};

// ============================================================================
// GLOBAL STATE
// ============================================================================

static struct {
  NASConfig config;
  NASFile files[NAS_MAX_FILES];
  int file_count;
  std::mutex mu;
  int initialized;
} g_nas = {.file_count = 0, .initialized = 0};

// ============================================================================
// C API
// ============================================================================

extern "C" {

int nas_init(const char *root_path, int port, uint64_t max_capacity_gb) {
  std::lock_guard<std::mutex> lock(g_nas.mu);

  strncpy(g_nas.config.root_path, root_path ? root_path : "D:\\",
          NAS_PATH_LEN - 1);
  g_nas.config.port = port > 0 ? port : NAS_PORT_DEFAULT;
  g_nas.config.tls_enabled = 1;
  g_nas.config.max_capacity_bytes = max_capacity_gb * 1024ULL * 1024 * 1024;
  g_nas.config.used_bytes = 0;
  g_nas.config.file_count = 0;
  g_nas.file_count = 0;
  g_nas.initialized = 1;

  fprintf(stdout, "[NAS] Initialized: %s port=%d tls=%d max=%lluGB\n",
          g_nas.config.root_path, g_nas.config.port, g_nas.config.tls_enabled,
          (unsigned long long)max_capacity_gb);
  return 0;
}

/**
 * Validate if a file type is allowed on NAS.
 * Returns 0 if allowed, -1 if forbidden.
 */
int nas_validate_file_type(int file_type) {
  if (file_type == NAS_FORBIDDEN) {
    fprintf(stderr, "[NAS] BLOCKED: Active training data not allowed\n");
    return -1;
  }
  return 0;
}

/**
 * Add a file to NAS storage.
 */
int nas_add_file(const char *path, int file_type, uint64_t size_bytes,
                 const char *shard_id) {
  std::lock_guard<std::mutex> lock(g_nas.mu);

  if (file_type == NAS_FORBIDDEN) {
    fprintf(stderr, "[NAS] BLOCKED: Cannot store active training data\n");
    return -1;
  }

  if (g_nas.file_count >= NAS_MAX_FILES) {
    fprintf(stderr, "[NAS] Full: %d files\n", NAS_MAX_FILES);
    return -1;
  }

  if (g_nas.config.used_bytes + size_bytes > g_nas.config.max_capacity_bytes) {
    fprintf(stderr, "[NAS] Capacity exceeded\n");
    return -2;
  }

  int idx = g_nas.file_count;
  NASFile &f = g_nas.files[idx];
  strncpy(f.path, path, NAS_PATH_LEN - 1);
  f.file_type = file_type;
  f.size_bytes = size_bytes;
  strncpy(f.shard_id, shard_id ? shard_id : "", 64);
  f.added_at = (long)time(NULL);

  g_nas.file_count++;
  g_nas.config.used_bytes += size_bytes;

  fprintf(stdout, "[NAS] Added: %s type=%d size=%lluMB\n", path, file_type,
          (unsigned long long)(size_bytes / (1024 * 1024)));
  return idx;
}

/**
 * Check if a shard exists on NAS.
 */
int nas_has_shard(const char *shard_id) {
  std::lock_guard<std::mutex> lock(g_nas.mu);

  for (int i = 0; i < g_nas.file_count; i++) {
    if (g_nas.files[i].file_type == NAS_ARCHIVE_SHARD &&
        strcmp(g_nas.files[i].shard_id, shard_id) == 0) {
      return 1;
    }
  }
  return 0;
}

int nas_file_count(void) {
  std::lock_guard<std::mutex> lock(g_nas.mu);
  return g_nas.file_count;
}

uint64_t nas_used_bytes(void) {
  std::lock_guard<std::mutex> lock(g_nas.mu);
  return g_nas.config.used_bytes;
}

uint64_t nas_free_bytes(void) {
  std::lock_guard<std::mutex> lock(g_nas.mu);
  return g_nas.config.max_capacity_bytes - g_nas.config.used_bytes;
}

} // extern "C"
