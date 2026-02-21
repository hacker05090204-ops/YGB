/*
 * node_discovery.cpp — Multi-Node Cluster TCP Discovery Service
 *
 * Authority node:
 *   - Runs TCP listener on fixed port (YGB_CLUSTER_PORT, default 9742)
 *   - Accepts join requests
 *   - Validates: device cert, HMAC version, dataset hash, model version, CUDA
 * compat
 *   - Adds approved nodes to cluster registry
 *
 * Worker node:
 *   - Detects GPU, computes node_id = SHA256(device + GPU_arch + CUDA)
 *   - Sends join request to authority
 *   - Receives approval/rejection
 *
 * Wire protocol (simple binary):
 *   [4 bytes: msg_type][4 bytes: payload_len][payload]
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


#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "Ws2_32.lib")
typedef int socklen_t;
#define CLOSE_SOCKET closesocket
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#define CLOSE_SOCKET close
typedef int SOCKET;
#define INVALID_SOCKET (-1)
#define SOCKET_ERROR (-1)
#endif

// =============================================================================
// CONSTANTS
// =============================================================================

static constexpr int DEFAULT_PORT = 9742;
static constexpr int MAX_CLUSTER_NODES = 64;
static constexpr int MAX_PAYLOAD = 4096;

// Message types
static constexpr uint32_t MSG_JOIN_REQUEST = 0x01;
static constexpr uint32_t MSG_JOIN_RESPONSE = 0x02;
static constexpr uint32_t MSG_HASH_REPORT = 0x03;
static constexpr uint32_t MSG_HASH_VERIFY = 0x04;
static constexpr uint32_t MSG_HEARTBEAT = 0x05;
static constexpr uint32_t MSG_ABORT = 0xFF;

// Join response codes
static constexpr uint32_t JOIN_APPROVED = 0x00;
static constexpr uint32_t JOIN_REJECTED_HASH = 0x01;
static constexpr uint32_t JOIN_REJECTED_MODEL = 0x02;
static constexpr uint32_t JOIN_REJECTED_GPU = 0x03;
static constexpr uint32_t JOIN_REJECTED_FULL = 0x04;

// =============================================================================
// SHA-256 (inline)
// =============================================================================

static void sha256_compute(const uint8_t *data, size_t len, uint8_t out[32]) {
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

static std::string to_hex(const uint8_t *d, size_t n) {
  static const char hx[] = "0123456789abcdef";
  std::string r(n * 2, '0');
  for (size_t i = 0; i < n; ++i) {
    r[i * 2] = hx[d[i] >> 4];
    r[i * 2 + 1] = hx[d[i] & 0xf];
  }
  return r;
}

// =============================================================================
// JOIN REQUEST / RESPONSE STRUCTURES
// =============================================================================

#pragma pack(push, 1)
struct JoinRequest {
  char node_id[65];
  char device_identity[128];
  char gpu_arch[64];
  char cuda_version[32];
  char hmac_version[32];
  char dataset_hash[65];
  char model_version[32];
  int32_t gpu_count;
  int32_t vram_total_mb;
};

struct JoinResponse {
  uint32_t result_code; // JOIN_APPROVED / JOIN_REJECTED_*
  int32_t assigned_rank;
  int32_t world_size;
  char authority_hash[65];
};

struct HashReport {
  char node_id[65];
  char weight_hash[65];
  int32_t epoch;
};
#pragma pack(pop)

// =============================================================================
// CLUSTER STATE
// =============================================================================

struct ClusterNode {
  char node_id[65];
  char device_identity[128];
  char gpu_arch[64];
  int32_t gpu_count;
  int32_t vram_total_mb;
  int32_t optimal_batch;
  int32_t rank;
  bool active;
};

static ClusterNode g_cluster[MAX_CLUSTER_NODES];
static int g_cluster_count = 0;
static char g_authority_hash[65] = {0};
static char g_authority_model[32] = {0};
static int g_authority_port = DEFAULT_PORT;
static bool g_wsa_init = false;

// =============================================================================
// PLATFORM INIT
// =============================================================================

static bool init_network() {
#ifdef _WIN32
  if (!g_wsa_init) {
    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
      std::fprintf(stderr, "[DISCOVER] WSAStartup failed\n");
      return false;
    }
    g_wsa_init = true;
  }
#endif
  return true;
}

// =============================================================================
// C EXPORTS
// =============================================================================

extern "C" {

/**
 * Compute node_id from device identity components.
 */
void discovery_compute_node_id(const char *device_identity,
                               const char *gpu_arch, const char *cuda_version,
                               char out_id[65]) {
  std::string combined;
  combined += device_identity ? device_identity : "";
  combined += "|";
  combined += gpu_arch ? gpu_arch : "";
  combined += "|";
  combined += cuda_version ? cuda_version : "";

  uint8_t hash[32];
  sha256_compute((const uint8_t *)combined.c_str(), combined.size(), hash);
  std::string hex = to_hex(hash, 32);
  std::strncpy(out_id, hex.c_str(), 64);
  out_id[64] = '\0';
}

/**
 * Set authority reference for validation.
 */
void discovery_set_authority(const char *dataset_hash,
                             const char *model_version, int port) {
  if (dataset_hash)
    std::strncpy(g_authority_hash, dataset_hash, 64);
  if (model_version)
    std::strncpy(g_authority_model, model_version, 31);
  g_authority_port = port > 0 ? port : DEFAULT_PORT;
}

/**
 * Validate a join request against authority references.
 * Returns JOIN_APPROVED or rejection code.
 */
uint32_t discovery_validate_join(const JoinRequest *req) {
  if (g_cluster_count >= MAX_CLUSTER_NODES)
    return JOIN_REJECTED_FULL;

  if (g_authority_hash[0] &&
      std::strcmp(g_authority_hash, req->dataset_hash) != 0) {
    std::fprintf(stderr, "[DISCOVER] REJECTED %s: dataset hash mismatch\n",
                 req->node_id);
    return JOIN_REJECTED_HASH;
  }

  if (g_authority_model[0] &&
      std::strcmp(g_authority_model, req->model_version) != 0) {
    std::fprintf(stderr, "[DISCOVER] REJECTED %s: model version mismatch\n",
                 req->node_id);
    return JOIN_REJECTED_MODEL;
  }

  return JOIN_APPROVED;
}

/**
 * Register an approved node.
 */
int discovery_register_node(const JoinRequest *req) {
  if (g_cluster_count >= MAX_CLUSTER_NODES)
    return -1;

  ClusterNode *node = &g_cluster[g_cluster_count];
  std::strncpy(node->node_id, req->node_id, 64);
  std::strncpy(node->device_identity, req->device_identity, 127);
  std::strncpy(node->gpu_arch, req->gpu_arch, 63);
  node->gpu_count = req->gpu_count;
  node->vram_total_mb = req->vram_total_mb;
  node->optimal_batch = 1024; // Default, updated later
  node->rank = g_cluster_count;
  node->active = true;

  int rank = g_cluster_count;
  g_cluster_count++;

  std::fprintf(stderr, "[DISCOVER] APPROVED rank=%d: %s (%s, %d GPUs)\n", rank,
               req->node_id, req->device_identity, req->gpu_count);
  return rank;
}

int discovery_get_cluster_size() { return g_cluster_count; }

int discovery_get_total_gpus() {
  int total = 0;
  for (int i = 0; i < g_cluster_count; ++i)
    if (g_cluster[i].active)
      total += g_cluster[i].gpu_count;
  return total;
}

int discovery_get_global_batch() {
  int total = 0;
  for (int i = 0; i < g_cluster_count; ++i)
    if (g_cluster[i].active)
      total += g_cluster[i].optimal_batch;
  return total;
}

void discovery_set_node_batch(int rank, int batch_size) {
  if (rank >= 0 && rank < g_cluster_count)
    g_cluster[rank].optimal_batch = batch_size;
}

const char *discovery_get_node_id(int rank) {
  if (rank < 0 || rank >= g_cluster_count)
    return "";
  return g_cluster[rank].node_id;
}

void discovery_clear() {
  g_cluster_count = 0;
  std::memset(g_cluster, 0, sizeof(g_cluster));
}

/**
 * Start authority TCP listener (blocking).
 * Called from Python in a thread.
 */
int discovery_start_authority(int port) {
  if (!init_network())
    return -1;
  g_authority_port = port > 0 ? port : DEFAULT_PORT;

  SOCKET srv = socket(AF_INET, SOCK_STREAM, 0);
  if (srv == INVALID_SOCKET) {
    std::fprintf(stderr, "[DISCOVER] Socket creation failed\n");
    return -1;
  }

  int opt = 1;
  setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, (const char *)&opt, sizeof(opt));

  struct sockaddr_in addr;
  std::memset(&addr, 0, sizeof(addr));
  addr.sin_family = AF_INET;
  addr.sin_addr.s_addr = INADDR_ANY;
  addr.sin_port = htons((uint16_t)g_authority_port);

  if (bind(srv, (struct sockaddr *)&addr, sizeof(addr)) == SOCKET_ERROR) {
    std::fprintf(stderr, "[DISCOVER] Bind failed on port %d\n",
                 g_authority_port);
    CLOSE_SOCKET(srv);
    return -1;
  }

  if (listen(srv, 16) == SOCKET_ERROR) {
    std::fprintf(stderr, "[DISCOVER] Listen failed\n");
    CLOSE_SOCKET(srv);
    return -1;
  }

  std::fprintf(stderr, "[DISCOVER] Authority listening on port %d\n",
               g_authority_port);

  // Accept loop (single-threaded for simplicity)
  while (g_cluster_count < MAX_CLUSTER_NODES) {
    struct sockaddr_in client_addr;
    socklen_t client_len = sizeof(client_addr);
    SOCKET client = accept(srv, (struct sockaddr *)&client_addr, &client_len);
    if (client == INVALID_SOCKET)
      continue;

    // Read message header
    uint32_t msg_type = 0, payload_len = 0;
    if (recv(client, (char *)&msg_type, 4, 0) != 4 ||
        recv(client, (char *)&payload_len, 4, 0) != 4) {
      CLOSE_SOCKET(client);
      continue;
    }

    if (msg_type == MSG_JOIN_REQUEST && payload_len == sizeof(JoinRequest)) {
      JoinRequest req;
      if (recv(client, (char *)&req, sizeof(req), 0) == sizeof(req)) {
        uint32_t result = discovery_validate_join(&req);

        JoinResponse resp;
        std::memset(&resp, 0, sizeof(resp));
        resp.result_code = result;

        if (result == JOIN_APPROVED) {
          resp.assigned_rank = discovery_register_node(&req);
          resp.world_size = g_cluster_count;
        }
        std::strncpy(resp.authority_hash, g_authority_hash, 64);

        uint32_t resp_type = MSG_JOIN_RESPONSE;
        uint32_t resp_len = sizeof(resp);
        send(client, (const char *)&resp_type, 4, 0);
        send(client, (const char *)&resp_len, 4, 0);
        send(client, (const char *)&resp, sizeof(resp), 0);
      }
    }

    CLOSE_SOCKET(client);
  }

  CLOSE_SOCKET(srv);
  return 0;
}

/**
 * Worker: attempt to join a cluster authority.
 * Returns assigned rank, or -1 if rejected/unreachable.
 */
int discovery_join_cluster(const char *authority_addr, int port,
                           const char *device_identity, const char *gpu_arch,
                           const char *cuda_version, const char *hmac_version,
                           const char *dataset_hash, const char *model_version,
                           int gpu_count, int vram_total_mb) {
  if (!init_network())
    return -1;

  SOCKET sock = socket(AF_INET, SOCK_STREAM, 0);
  if (sock == INVALID_SOCKET)
    return -1;

  struct sockaddr_in addr;
  std::memset(&addr, 0, sizeof(addr));
  addr.sin_family = AF_INET;
  addr.sin_port = htons((uint16_t)(port > 0 ? port : DEFAULT_PORT));
  inet_pton(AF_INET, authority_addr ? authority_addr : "127.0.0.1",
            &addr.sin_addr);

  if (connect(sock, (struct sockaddr *)&addr, sizeof(addr)) == SOCKET_ERROR) {
    CLOSE_SOCKET(sock);
    return -1; // Authority unreachable
  }

  // Build join request
  JoinRequest req;
  std::memset(&req, 0, sizeof(req));
  discovery_compute_node_id(device_identity, gpu_arch, cuda_version,
                            req.node_id);
  if (device_identity)
    std::strncpy(req.device_identity, device_identity, 127);
  if (gpu_arch)
    std::strncpy(req.gpu_arch, gpu_arch, 63);
  if (cuda_version)
    std::strncpy(req.cuda_version, cuda_version, 31);
  if (hmac_version)
    std::strncpy(req.hmac_version, hmac_version, 31);
  if (dataset_hash)
    std::strncpy(req.dataset_hash, dataset_hash, 64);
  if (model_version)
    std::strncpy(req.model_version, model_version, 31);
  req.gpu_count = gpu_count;
  req.vram_total_mb = vram_total_mb;

  // Send
  uint32_t msg_type = MSG_JOIN_REQUEST;
  uint32_t payload_len = sizeof(req);
  send(sock, (const char *)&msg_type, 4, 0);
  send(sock, (const char *)&payload_len, 4, 0);
  send(sock, (const char *)&req, sizeof(req), 0);

  // Receive response
  uint32_t resp_type = 0, resp_len = 0;
  if (recv(sock, (char *)&resp_type, 4, 0) != 4 ||
      recv(sock, (char *)&resp_len, 4, 0) != 4) {
    CLOSE_SOCKET(sock);
    return -1;
  }

  JoinResponse resp;
  if (resp_type == MSG_JOIN_RESPONSE && resp_len == sizeof(resp)) {
    if (recv(sock, (char *)&resp, sizeof(resp), 0) == sizeof(resp)) {
      CLOSE_SOCKET(sock);

      if (resp.result_code == JOIN_APPROVED) {
        std::fprintf(stderr, "[DISCOVER] Joined cluster: rank=%d, world=%d\n",
                     resp.assigned_rank, resp.world_size);
        return resp.assigned_rank;
      } else {
        std::fprintf(stderr, "[DISCOVER] Join rejected: code=%u\n",
                     resp.result_code);
        return -1;
      }
    }
  }

  CLOSE_SOCKET(sock);
  return -1;
}

} // extern "C"
