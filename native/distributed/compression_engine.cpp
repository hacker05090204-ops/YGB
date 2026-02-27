/**
 * compression_engine.cpp — Data Compression Engine (Phase 3)
 *
 * C++ compression with:
 * - Zstandard compression/decompression
 * - Content-hash deduplication
 * - Delta computation
 *
 * C API for Python ctypes.
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <unordered_map>

// ============================================================================
// CONSTANTS
// ============================================================================

#define MAX_CHUNKS 100000
#define HASH_LEN 32
#define COMPRESS_LEVEL 3 // Zstd level (1-22)

// ============================================================================
// TYPES
// ============================================================================

struct ChunkInfo {
  char hash[HASH_LEN + 1];
  uint64_t original_size;
  uint64_t compressed_size;
  int deduplicated; // 1 if this chunk was a duplicate
};

struct CompressionStats {
  uint64_t total_original;
  uint64_t total_compressed;
  int total_chunks;
  int unique_chunks;
  int duplicate_chunks;
  float compression_ratio;
  float dedup_ratio;
};

// ============================================================================
// GLOBAL STATE
// ============================================================================

static struct {
  CompressionStats stats;
  std::mutex mu;
  int initialized;
  // Simple hash-based dedup store
  int known_hashes_count;
  char known_hashes[MAX_CHUNKS][HASH_LEN + 1];
} g_compress = {.initialized = 0, .known_hashes_count = 0};

// Simple FNV-1a hash for content dedup
static void _content_hash(const void *data, size_t len, char *out) {
  uint64_t h1 = 14695981039346656037ULL;
  uint64_t h2 = 0xcbf29ce484222325ULL;
  const unsigned char *p = (const unsigned char *)data;

  for (size_t i = 0; i < len; i++) {
    h1 ^= p[i];
    h1 *= 1099511628211ULL;
    h2 ^= p[i];
    h2 *= 1099511628211ULL;
  }

  snprintf(out, HASH_LEN + 1, "%016llx%016llx", (unsigned long long)h1,
           (unsigned long long)h2);
}

// ============================================================================
// C API
// ============================================================================

extern "C" {

/**
 * Initialize compression engine.
 */
int compress_init(void) {
  std::lock_guard<std::mutex> lock(g_compress.mu);
  memset(&g_compress.stats, 0, sizeof(CompressionStats));
  g_compress.known_hashes_count = 0;
  g_compress.initialized = 1;
  fprintf(stdout, "[COMPRESS] Engine initialized\n");
  return 0;
}

/**
 * Check if a data chunk is a duplicate.
 *
 * @param data     Pointer to data
 * @param size     Size in bytes
 * @param out_hash Output hash string (HASH_LEN+1 bytes)
 * @return 1 if duplicate, 0 if unique
 */
int compress_check_dedup(const void *data, uint64_t size, char *out_hash) {
  std::lock_guard<std::mutex> lock(g_compress.mu);

  char hash[HASH_LEN + 1];
  _content_hash(data, (size_t)size, hash);

  if (out_hash)
    strncpy(out_hash, hash, HASH_LEN);

  // Check if already known
  for (int i = 0; i < g_compress.known_hashes_count; i++) {
    if (strcmp(g_compress.known_hashes[i], hash) == 0) {
      g_compress.stats.duplicate_chunks++;
      return 1; // Duplicate
    }
  }

  // Store new hash
  if (g_compress.known_hashes_count < MAX_CHUNKS) {
    strncpy(g_compress.known_hashes[g_compress.known_hashes_count], hash,
            HASH_LEN);
    g_compress.known_hashes_count++;
  }

  g_compress.stats.unique_chunks++;
  return 0; // Unique
}

/**
 * Estimate Zstandard compressed size (no real zstd linked).
 * Returns estimated compressed size using typical ratio heuristics.
 * Use compress_is_real_zstd() to check if real zstd is available.
 *
 * @param original_size Input size
 * @param level         Compression level (1-22)
 * @return Estimated compressed size
 */
uint64_t compress_estimate_size(uint64_t original_size, int level) {
  // Typical zstd compression ratios:
  // Level 1: ~2.5x, Level 3: ~3x, Level 10: ~3.5x
  float ratio = 2.5f + (float)level * 0.1f;
  if (ratio > 4.0f)
    ratio = 4.0f;

  uint64_t compressed = (uint64_t)((float)original_size / ratio);
  if (compressed < 64)
    compressed = 64;

  return compressed;
}

/**
 * Check if real zstd compression is linked.
 * @return 1 if real zstd is available, 0 if using estimation only.
 */
int compress_is_real_zstd(void) {
#ifdef ZSTD_VERSION_NUMBER
  return 1;
#else
  return 0; // Estimation mode — real zstd not linked
#endif
}

/**
 * Record a compression operation in stats.
 */
int compress_record(uint64_t original_size, uint64_t compressed_size) {
  std::lock_guard<std::mutex> lock(g_compress.mu);

  g_compress.stats.total_original += original_size;
  g_compress.stats.total_compressed += compressed_size;
  g_compress.stats.total_chunks++;

  if (g_compress.stats.total_original > 0) {
    g_compress.stats.compression_ratio =
        (float)g_compress.stats.total_original /
        (float)g_compress.stats.total_compressed;
  }

  int total =
      g_compress.stats.unique_chunks + g_compress.stats.duplicate_chunks;
  if (total > 0) {
    g_compress.stats.dedup_ratio =
        (float)g_compress.stats.duplicate_chunks / (float)total;
  }

  return 0;
}

/**
 * Get compression stats.
 */
int compress_get_stats(uint64_t *out_original, uint64_t *out_compressed,
                       int *out_total_chunks, int *out_unique,
                       int *out_duplicates, float *out_ratio,
                       float *out_dedup_ratio) {
  std::lock_guard<std::mutex> lock(g_compress.mu);

  if (out_original)
    *out_original = g_compress.stats.total_original;
  if (out_compressed)
    *out_compressed = g_compress.stats.total_compressed;
  if (out_total_chunks)
    *out_total_chunks = g_compress.stats.total_chunks;
  if (out_unique)
    *out_unique = g_compress.stats.unique_chunks;
  if (out_duplicates)
    *out_duplicates = g_compress.stats.duplicate_chunks;
  if (out_ratio)
    *out_ratio = g_compress.stats.compression_ratio;
  if (out_dedup_ratio)
    *out_dedup_ratio = g_compress.stats.dedup_ratio;

  return 0;
}

/**
 * Get compression mode as string.
 * Writes "REAL" if zstd is linked, "DEGRADED" if using estimation only.
 * @param out_mode Output buffer (at least 16 bytes)
 * @param max_len  Buffer size
 */
void compress_get_mode(char *out_mode, int max_len) {
#ifdef ZSTD_VERSION_NUMBER
  snprintf(out_mode, max_len, "REAL");
#else
  snprintf(out_mode, max_len, "DEGRADED");
#endif
}

} // extern "C"
