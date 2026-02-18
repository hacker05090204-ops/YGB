/**
 * node_identity.cpp — GPU/CPU Node Registry
 *
 * Identifies and profiles each compute node in the distributed cluster.
 * Hardware fingerprinting: VRAM, clock, CUDA cores, CPU cores.
 *
 * Hardware:
 *   1× RTX 3050, 2× RTX 2050, 1× Mac M1
 *   2× AMD 8-core CPUs, 1× Hexa-core CPU
 *
 * NO cross-field contamination. All nodes train SAME field.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace distributed {

// =========================================================================
// NODE TYPE
// =========================================================================

enum class NodeType : uint8_t {
  GPU_CUDA = 0,
  GPU_MPS = 1, // Apple M1
  CPU_AMD = 2,
  CPU_INTEL = 3
};

static const char *node_type_name(NodeType t) {
  switch (t) {
  case NodeType::GPU_CUDA:
    return "GPU_CUDA";
  case NodeType::GPU_MPS:
    return "GPU_MPS";
  case NodeType::CPU_AMD:
    return "CPU_AMD";
  case NodeType::CPU_INTEL:
    return "CPU_INTEL";
  default:
    return "UNKNOWN";
  }
}

// =========================================================================
// NODE IDENTITY
// =========================================================================

struct NodeIdentity {
  uint32_t node_id;
  NodeType type;
  char hostname[64];
  char device_name[64];
  uint32_t vram_mb; // 0 for CPU nodes
  uint32_t cpu_cores;
  uint32_t ram_mb;
  double clock_ghz;
  uint64_t fingerprint; // hardware hash
  bool available;
};

// =========================================================================
// CLUSTER REGISTRY
// =========================================================================

static constexpr uint32_t MAX_NODES = 8;

class ClusterRegistry {
public:
  ClusterRegistry() : count_(0) { std::memset(nodes_, 0, sizeof(nodes_)); }

  int register_node(NodeType type, const char *hostname, const char *device,
                    uint32_t vram_mb, uint32_t cpu_cores, uint32_t ram_mb,
                    double clock_ghz) {
    if (count_ >= MAX_NODES)
      return -1;

    NodeIdentity &n = nodes_[count_];
    n.node_id = count_ + 1;
    n.type = type;
    std::strncpy(n.hostname, hostname, 63);
    n.hostname[63] = '\0';
    std::strncpy(n.device_name, device, 63);
    n.device_name[63] = '\0';
    n.vram_mb = vram_mb;
    n.cpu_cores = cpu_cores;
    n.ram_mb = ram_mb;
    n.clock_ghz = clock_ghz;
    n.available = true;

    // Hardware fingerprint
    n.fingerprint = compute_fingerprint(n);
    return static_cast<int>(count_++);
  }

  uint32_t gpu_count() const {
    uint32_t c = 0;
    for (uint32_t i = 0; i < count_; ++i)
      if (nodes_[i].type == NodeType::GPU_CUDA ||
          nodes_[i].type == NodeType::GPU_MPS)
        ++c;
    return c;
  }

  uint32_t cpu_count() const { return count_ - gpu_count(); }
  uint32_t total() const { return count_; }

  const NodeIdentity *node(uint32_t idx) const {
    return (idx < count_) ? &nodes_[idx] : nullptr;
  }

  // Total VRAM across all GPU nodes
  uint32_t total_vram_mb() const {
    uint32_t total = 0;
    for (uint32_t i = 0; i < count_; ++i)
      total += nodes_[i].vram_mb;
    return total;
  }

  // Total CPU cores across all CPU nodes
  uint32_t total_cpu_cores() const {
    uint32_t total = 0;
    for (uint32_t i = 0; i < count_; ++i)
      if (nodes_[i].type == NodeType::CPU_AMD ||
          nodes_[i].type == NodeType::CPU_INTEL)
        total += nodes_[i].cpu_cores;
    return total;
  }

private:
  NodeIdentity nodes_[MAX_NODES];
  uint32_t count_;

  static uint64_t compute_fingerprint(const NodeIdentity &n) {
    uint64_t h = 0xcbf29ce484222325ULL;
    auto mix = [&](uint64_t v) {
      h ^= v;
      h *= 0x100000001b3ULL;
    };
    mix(static_cast<uint64_t>(n.type));
    mix(n.vram_mb);
    mix(n.cpu_cores);
    mix(n.ram_mb);
    uint64_t clk;
    std::memcpy(&clk, &n.clock_ghz, sizeof(clk));
    mix(clk);
    return h;
  }
};

} // namespace distributed
