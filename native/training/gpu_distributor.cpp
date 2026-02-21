/*
 * gpu_distributor.cpp — Multi-GPU Distribution & Verification
 *
 * Detects CUDA GPUs, verifies compute capability, partitions data
 * deterministically, and validates weight hashes across ranks.
 *
 * C++ runtime enforcement — Python governance only.
 */

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>


// =============================================================================
// GPU INFO STRUCTURE
// =============================================================================

struct GpuInfo {
  int device_id;
  char name[256];
  int compute_major;
  int compute_minor;
  uint64_t total_memory_bytes;
  bool is_dedicated; // true if discrete GPU
};

struct DistributionConfig {
  int world_size; // Number of GPUs
  int base_seed;  // Base random seed
  bool nccl_deterministic;
  bool all_same_compute; // All GPUs same compute capability
};

// =============================================================================
// GPU DETECTION (STUB — links with CUDA runtime if available)
// =============================================================================

static std::vector<GpuInfo> g_detected_gpus;
static DistributionConfig g_dist_config = {0, 42, true, true};
static bool g_detection_done = false;

static void detect_gpus() {
  if (g_detection_done)
    return;
  g_detection_done = true;

  /*
   * In production: uses cudaGetDeviceCount() + cudaGetDeviceProperties().
   * This stub provides the interface for Python ctypes binding.
   * Actual CUDA calls are enabled when compiled with nvcc.
   */

#ifdef __CUDACC__
  int count = 0;
  if (cudaGetDeviceCount(&count) != cudaSuccess) {
    std::fprintf(stderr, "[GPU_DIST] No CUDA devices found\n");
    return;
  }

  for (int i = 0; i < count; ++i) {
    cudaDeviceProp props;
    if (cudaGetDeviceProperties(&props, i) != cudaSuccess)
      continue;

    GpuInfo info;
    info.device_id = i;
    std::strncpy(info.name, props.name, sizeof(info.name) - 1);
    info.name[sizeof(info.name) - 1] = '\0';
    info.compute_major = props.major;
    info.compute_minor = props.minor;
    info.total_memory_bytes = props.totalGlobalMem;
    info.is_dedicated = (props.integrated == 0);

    g_detected_gpus.push_back(info);
  }
#else
  // Fallback: report single CPU-only device
  GpuInfo cpu_fallback;
  cpu_fallback.device_id = -1;
  std::strncpy(cpu_fallback.name, "CPU-only (no CUDA)",
               sizeof(cpu_fallback.name) - 1);
  cpu_fallback.name[sizeof(cpu_fallback.name) - 1] = '\0';
  cpu_fallback.compute_major = 0;
  cpu_fallback.compute_minor = 0;
  cpu_fallback.total_memory_bytes = 0;
  cpu_fallback.is_dedicated = false;
  g_detected_gpus.push_back(cpu_fallback);
#endif

  g_dist_config.world_size = 0;
  for (auto &g : g_detected_gpus) {
    if (g.device_id >= 0)
      g_dist_config.world_size++;
  }

  // Verify all GPUs have same compute capability
  if (g_dist_config.world_size > 1) {
    int ref_major = g_detected_gpus[0].compute_major;
    int ref_minor = g_detected_gpus[0].compute_minor;
    g_dist_config.all_same_compute = true;

    for (size_t i = 1; i < g_detected_gpus.size(); ++i) {
      if (g_detected_gpus[i].device_id < 0)
        continue;
      if (g_detected_gpus[i].compute_major != ref_major ||
          g_detected_gpus[i].compute_minor != ref_minor) {
        g_dist_config.all_same_compute = false;
        std::fprintf(
            stderr,
            "[GPU_DIST] WARNING: GPU %d has different compute capability "
            "(%d.%d vs %d.%d) — DDP may be unreliable\n",
            g_detected_gpus[i].device_id, g_detected_gpus[i].compute_major,
            g_detected_gpus[i].compute_minor, ref_major, ref_minor);
        break;
      }
    }
  }

  std::fprintf(stderr, "[GPU_DIST] Detected %d GPU(s), same_compute=%s\n",
               g_dist_config.world_size,
               g_dist_config.all_same_compute ? "true" : "false");
}

// =============================================================================
// DETERMINISTIC PARTITIONING
// =============================================================================

/*
 * Deterministic dataset sharding:
 *   shard_i = dataset[i::world_size]
 *
 * Each GPU rank gets exactly its shard. Seeds are locked per rank:
 *   seed_rank = base_seed + rank
 */

struct ShardSpec {
  int rank;
  int world_size;
  int seed;        // rank-locked seed
  int start_index; // First sample index for this rank
  int stride;      // = world_size
};

static ShardSpec compute_shard(int rank, int base_seed) {
  detect_gpus();

  ShardSpec spec;
  spec.rank = rank;
  spec.world_size = g_dist_config.world_size > 0 ? g_dist_config.world_size : 1;
  spec.seed = base_seed + rank;
  spec.start_index = rank;
  spec.stride = spec.world_size;

  return spec;
}

// =============================================================================
// WEIGHT HASH VERIFICATION
// =============================================================================

/*
 * SHA-256 for weight hash comparison across ranks.
 * Reuses the implementation from secret_vault.cpp.
 */

// Minimal SHA-256 for weight hashing (same as in secret_vault.cpp)
static void sha256_for_weights(const uint8_t *data, size_t len,
                               uint8_t out[32]) {
  // SHA-256 constants
  static const uint32_t K[64] = {
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
      0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
      0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
      0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
      0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
      0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
      0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
      0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
      0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
      0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
      0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  };

  auto rotr = [](uint32_t x, int n) -> uint32_t {
    return (x >> n) | (x << (32 - n));
  };

  uint32_t h[8] = {
      0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
      0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  };

  // Padding
  size_t orig_len = len;
  size_t padded = ((len + 9 + 63) / 64) * 64;
  std::vector<uint8_t> msg(padded, 0);
  std::memcpy(msg.data(), data, len);
  msg[len] = 0x80;
  uint64_t bit_len = (uint64_t)orig_len * 8;
  for (int i = 0; i < 8; ++i)
    msg[padded - 1 - i] = (uint8_t)(bit_len >> (i * 8));

  // Process blocks
  for (size_t off = 0; off < padded; off += 64) {
    uint32_t w[64];
    for (int i = 0; i < 16; ++i)
      w[i] = ((uint32_t)msg[off + i * 4] << 24) |
             ((uint32_t)msg[off + i * 4 + 1] << 16) |
             ((uint32_t)msg[off + i * 4 + 2] << 8) |
             ((uint32_t)msg[off + i * 4 + 3]);

    for (int i = 16; i < 64; ++i) {
      uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
      uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }

    uint32_t a = h[0], b = h[1], c = h[2], d = h[3];
    uint32_t e = h[4], f = h[5], g = h[6], hh = h[7];

    for (int i = 0; i < 64; ++i) {
      uint32_t S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      uint32_t ch = (e & f) ^ (~e & g);
      uint32_t t1 = hh + S1 + ch + K[i] + w[i];
      uint32_t S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
      uint32_t t2 = S0 + maj;

      hh = g;
      g = f;
      f = e;
      e = d + t1;
      d = c;
      c = b;
      b = a;
      a = t1 + t2;
    }

    h[0] += a;
    h[1] += b;
    h[2] += c;
    h[3] += d;
    h[4] += e;
    h[5] += f;
    h[6] += g;
    h[7] += hh;
  }

  for (int i = 0; i < 8; ++i) {
    out[i * 4] = (uint8_t)(h[i] >> 24);
    out[i * 4 + 1] = (uint8_t)(h[i] >> 16);
    out[i * 4 + 2] = (uint8_t)(h[i] >> 8);
    out[i * 4 + 3] = (uint8_t)(h[i]);
  }
}

static std::string hash_to_hex(const uint8_t hash[32]) {
  static const char hex[] = "0123456789abcdef";
  std::string result(64, '0');
  for (int i = 0; i < 32; ++i) {
    result[i * 2] = hex[hash[i] >> 4];
    result[i * 2 + 1] = hex[hash[i] & 0x0f];
  }
  return result;
}

// =============================================================================
// C EXPORTS (for Python ctypes binding)
// =============================================================================

extern "C" {

int gpu_dist_detect() {
  detect_gpus();
  return g_dist_config.world_size;
}

int gpu_dist_gpu_count() {
  detect_gpus();
  return g_dist_config.world_size;
}

bool gpu_dist_all_same_compute() {
  detect_gpus();
  return g_dist_config.all_same_compute;
}

void gpu_dist_get_shard(int rank, int base_seed, int *out_start,
                        int *out_stride, int *out_seed) {
  ShardSpec spec = compute_shard(rank, base_seed);
  if (out_start)
    *out_start = spec.start_index;
  if (out_stride)
    *out_stride = spec.stride;
  if (out_seed)
    *out_seed = spec.seed;
}

bool gpu_dist_verify_weights(const uint8_t *weights_a, size_t len_a,
                             const uint8_t *weights_b, size_t len_b) {
  if (len_a != len_b) {
    std::fprintf(stderr,
                 "[GPU_DIST] ABORT: Weight length mismatch (%zu vs %zu)\n",
                 len_a, len_b);
    return false;
  }

  uint8_t hash_a[32], hash_b[32];
  sha256_for_weights(weights_a, len_a, hash_a);
  sha256_for_weights(weights_b, len_b, hash_b);

  bool match = (std::memcmp(hash_a, hash_b, 32) == 0);

  if (!match) {
    std::fprintf(stderr,
                 "[GPU_DIST] ABORT: Weight hash mismatch across ranks!\n");
    std::fprintf(stderr, "  Rank A: %s\n", hash_to_hex(hash_a).c_str());
    std::fprintf(stderr, "  Rank B: %s\n", hash_to_hex(hash_b).c_str());
  } else {
    std::fprintf(stderr, "[GPU_DIST] Weight hash verified: %s\n",
                 hash_to_hex(hash_a).c_str());
  }

  return match;
}

const char *gpu_dist_get_gpu_name(int index) {
  detect_gpus();
  if (index < 0 || index >= (int)g_detected_gpus.size())
    return "unknown";
  return g_detected_gpus[index].name;
}

} // extern "C"

// =============================================================================
// SELF-TEST
// =============================================================================

#ifdef GPU_DIST_SELFTEST
int main() {
  std::fprintf(stderr, "[TEST] gpu_distributor self-test\n");

  // Test detection
  int count = gpu_dist_detect();
  std::fprintf(stderr, "  GPU count: %d\n", count);
  std::fprintf(stderr, "  Same compute: %s\n",
               gpu_dist_all_same_compute() ? "yes" : "no");

  // Test sharding
  int start, stride, seed;
  gpu_dist_get_shard(0, 42, &start, &stride, &seed);
  std::fprintf(stderr, "  Rank 0: start=%d, stride=%d, seed=%d\n", start,
               stride, seed);

  // Test weight verification
  const char *w1 = "test_weights_abc";
  const char *w2 = "test_weights_abc";
  const char *w3 = "test_weights_xyz";

  bool match1 = gpu_dist_verify_weights((const uint8_t *)w1, std::strlen(w1),
                                        (const uint8_t *)w2, std::strlen(w2));
  std::fprintf(stderr, "  Same weights match: %s (expected: yes)\n",
               match1 ? "yes" : "no");

  bool match2 = gpu_dist_verify_weights((const uint8_t *)w1, std::strlen(w1),
                                        (const uint8_t *)w3, std::strlen(w3));
  std::fprintf(stderr, "  Diff weights match: %s (expected: no)\n",
               match2 ? "yes" : "no");

  bool passed = match1 && !match2;
  std::fprintf(stderr, "[TEST] %s\n", passed ? "ALL PASSED" : "FAILED");
  return passed ? 0 : 1;
}
#endif
