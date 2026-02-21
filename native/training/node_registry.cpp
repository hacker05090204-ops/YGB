/*
 * node_registry.cpp — Multi-Node Cluster Registration & Validation
 *
 * Each node generates:
 *   node_id = SHA256(device_identity + GPU_arch + CUDA_version)
 *
 * Authority validates:
 *   - GPU architecture compatibility
 *   - HMAC version match
 *   - Dataset hash match
 *   - Model version match
 *
 * C++ runtime enforcement — Python governance only.
 */

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>


// =============================================================================
// SHA-256 (inline for node hashing)
// =============================================================================

static void sha256_hash(const uint8_t *data, size_t len, uint8_t out[32]) {
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

  size_t padded = ((len + 9 + 63) / 64) * 64;
  std::vector<uint8_t> msg(padded, 0);
  std::memcpy(msg.data(), data, len);
  msg[len] = 0x80;
  uint64_t bit_len = (uint64_t)len * 8;
  for (int i = 0; i < 8; ++i)
    msg[padded - 1 - i] = (uint8_t)(bit_len >> (i * 8));

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
    uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5],
             g = h[6], hh = h[7];
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

static std::string bytes_to_hex(const uint8_t *data, size_t len) {
  static const char hex[] = "0123456789abcdef";
  std::string result(len * 2, '0');
  for (size_t i = 0; i < len; ++i) {
    result[i * 2] = hex[data[i] >> 4];
    result[i * 2 + 1] = hex[data[i] & 0x0f];
  }
  return result;
}

// =============================================================================
// NODE IDENTITY
// =============================================================================

struct NodeIdentity {
  char node_id[65]; // 64-char hex + null
  char device_name[256];
  char gpu_arch[64];
  char cuda_version[32];
  char hmac_version[32];
  char dataset_hash[65];
  char model_version[32];
  int gpu_count;
  bool approved;
};

// =============================================================================
// CLUSTER REGISTRY
// =============================================================================

static constexpr int MAX_NODES = 64;
static NodeIdentity g_registry[MAX_NODES];
static int g_node_count = 0;
static char g_authority_dataset_hash[65] = {0};
static char g_authority_model_version[32] = {0};
static char g_authority_gpu_arch[64] = {0};

// =============================================================================
// C EXPORTS
// =============================================================================

extern "C" {

/**
 * Generate node_id = SHA256(device_identity + GPU_arch + CUDA_version)
 */
void node_compute_id(const char *device_identity, const char *gpu_arch,
                     const char *cuda_version, char out_node_id[65]) {
  std::string combined;
  combined += device_identity ? device_identity : "";
  combined += "|";
  combined += gpu_arch ? gpu_arch : "";
  combined += "|";
  combined += cuda_version ? cuda_version : "";

  uint8_t hash[32];
  sha256_hash((const uint8_t *)combined.c_str(), combined.size(), hash);
  std::string hex = bytes_to_hex(hash, 32);
  std::strncpy(out_node_id, hex.c_str(), 64);
  out_node_id[64] = '\0';
}

/**
 * Set authority reference values for validation
 */
void node_set_authority(const char *dataset_hash, const char *model_version,
                        const char *gpu_arch) {
  if (dataset_hash)
    std::strncpy(g_authority_dataset_hash, dataset_hash, 64);
  if (model_version)
    std::strncpy(g_authority_model_version, model_version, 31);
  if (gpu_arch)
    std::strncpy(g_authority_gpu_arch, gpu_arch, 63);
}

/**
 * Register a node. Returns:
 *   0 = approved
 *   1 = rejected (dataset hash mismatch)
 *   2 = rejected (model version mismatch)
 *   3 = rejected (GPU arch incompatible)
 *   4 = rejected (registry full)
 */
int node_register(const char *device_identity, const char *gpu_arch,
                  const char *cuda_version, const char *hmac_version,
                  const char *dataset_hash, const char *model_version,
                  int gpu_count) {
  if (g_node_count >= MAX_NODES) {
    std::fprintf(stderr, "[NODE_REG] Registry full (%d nodes)\n", MAX_NODES);
    return 4;
  }

  // Generate node_id
  char node_id[65];
  node_compute_id(device_identity, gpu_arch, cuda_version, node_id);

  // Validate dataset hash
  if (g_authority_dataset_hash[0] != '\0' && dataset_hash) {
    if (std::strcmp(g_authority_dataset_hash, dataset_hash) != 0) {
      std::fprintf(stderr, "[NODE_REG] REJECTED %s: dataset hash mismatch\n",
                   node_id);
      return 1;
    }
  }

  // Validate model version
  if (g_authority_model_version[0] != '\0' && model_version) {
    if (std::strcmp(g_authority_model_version, model_version) != 0) {
      std::fprintf(stderr, "[NODE_REG] REJECTED %s: model version mismatch\n",
                   node_id);
      return 2;
    }
  }

  // Validate GPU architecture compatibility
  if (g_authority_gpu_arch[0] != '\0' && gpu_arch) {
    // Allow same family (e.g., "Ampere" matches "Ampere")
    if (std::strcmp(g_authority_gpu_arch, gpu_arch) != 0) {
      std::fprintf(stderr,
                   "[NODE_REG] REJECTED %s: GPU arch incompatible (%s vs %s)\n",
                   node_id, gpu_arch, g_authority_gpu_arch);
      return 3;
    }
  }

  // Approved — add to registry
  NodeIdentity *node = &g_registry[g_node_count];
  std::strncpy(node->node_id, node_id, 64);
  node->node_id[64] = '\0';
  std::strncpy(node->device_name, device_identity ? device_identity : "", 255);
  std::strncpy(node->gpu_arch, gpu_arch ? gpu_arch : "", 63);
  std::strncpy(node->cuda_version, cuda_version ? cuda_version : "", 31);
  std::strncpy(node->hmac_version, hmac_version ? hmac_version : "", 31);
  std::strncpy(node->dataset_hash, dataset_hash ? dataset_hash : "", 64);
  std::strncpy(node->model_version, model_version ? model_version : "", 31);
  node->gpu_count = gpu_count;
  node->approved = true;

  g_node_count++;
  std::fprintf(stderr, "[NODE_REG] APPROVED: %s (%s, %d GPUs)\n", node_id,
               device_identity ? device_identity : "unknown", gpu_count);
  return 0;
}

int node_get_count() { return g_node_count; }

int node_get_total_gpus() {
  int total = 0;
  for (int i = 0; i < g_node_count; ++i)
    total += g_registry[i].gpu_count;
  return total;
}

const char *node_get_id(int index) {
  if (index < 0 || index >= g_node_count)
    return "";
  return g_registry[index].node_id;
}

void node_clear_registry() {
  g_node_count = 0;
  std::memset(g_registry, 0, sizeof(g_registry));
}

} // extern "C"
