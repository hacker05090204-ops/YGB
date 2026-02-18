/**
 * deterministic_sync.cpp — Deterministic Gradient Synchronization
 *
 * Synchronizes gradients across distributed GPU nodes with deterministic
 * ordering. Seed-locked shard assignment ensures reproducibility.
 *
 * All nodes train SAME field on different data shards.
 * NO cross-field contamination. NO half-trained merging.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace distributed {

// =========================================================================
// SHARD ASSIGNMENT
// =========================================================================

struct ShardAssignment {
  uint32_t node_id;
  uint32_t shard_start;
  uint32_t shard_end;
  uint32_t shard_size;
  uint32_t seed;       // per-shard deterministic seed
  char field_name[64]; // SAME field for all shards
};

// =========================================================================
// SYNC STATE
// =========================================================================

struct SyncState {
  uint32_t epoch;
  uint32_t nodes_synced;
  uint32_t nodes_total;
  double max_grad_divergence;
  bool all_synced;
  bool determinism_verified;
  uint64_t sync_hash;
  char status[128];
};

// =========================================================================
// DETERMINISTIC SYNC ENGINE
// =========================================================================

static constexpr uint32_t MAX_SHARDS = 8;

class DeterministicSync {
public:
  static constexpr uint32_t SEED_BASE = 42;
  static constexpr double MAX_GRAD_DIVERGENCE = 0.01;

  DeterministicSync() : num_shards_(0), current_epoch_(0) {
    std::memset(shards_, 0, sizeof(shards_));
  }

  // Assign data shards to nodes (all same field)
  void assign_shards(uint32_t num_nodes, uint32_t total_samples,
                     const char *field_name) {
    num_shards_ = (num_nodes > MAX_SHARDS) ? MAX_SHARDS : num_nodes;
    uint32_t per_shard = total_samples / num_shards_;
    uint32_t remainder = total_samples % num_shards_;

    uint32_t offset = 0;
    for (uint32_t i = 0; i < num_shards_; ++i) {
      shards_[i].node_id = i + 1;
      shards_[i].shard_start = offset;
      shards_[i].shard_size = per_shard + (i < remainder ? 1 : 0);
      shards_[i].shard_end = offset + shards_[i].shard_size;
      shards_[i].seed = SEED_BASE + i * 1000 + current_epoch_;
      std::strncpy(shards_[i].field_name, field_name, 63);
      shards_[i].field_name[63] = '\0';
      offset = shards_[i].shard_end;
    }
  }

  // Verify all nodes computed on same field (anti-contamination)
  bool verify_field_isolation() const {
    if (num_shards_ == 0)
      return true;
    for (uint32_t i = 1; i < num_shards_; ++i) {
      if (std::strcmp(shards_[0].field_name, shards_[i].field_name) != 0)
        return false; // CROSS-FIELD CONTAMINATION DETECTED
    }
    return true;
  }

  // Synchronize epoch gradients
  SyncState sync_epoch(const double *grad_norms, uint32_t num_nodes) {
    SyncState s;
    std::memset(&s, 0, sizeof(s));
    s.epoch = current_epoch_;
    s.nodes_total = num_nodes;

    // Compute max gradient divergence
    double mean = 0.0;
    for (uint32_t i = 0; i < num_nodes; ++i)
      mean += grad_norms[i];
    mean /= num_nodes;

    double max_div = 0.0;
    for (uint32_t i = 0; i < num_nodes; ++i) {
      double div = std::fabs(grad_norms[i] - mean) / (mean + 1e-8);
      if (div > max_div)
        max_div = div;
    }

    s.max_grad_divergence = max_div;
    s.all_synced = (max_div <= MAX_GRAD_DIVERGENCE);
    s.determinism_verified = verify_field_isolation();
    s.nodes_synced = s.all_synced ? num_nodes : 0;

    // Deterministic sync hash
    uint64_t h = 0;
    for (uint32_t i = 0; i < num_nodes; ++i) {
      uint64_t bits;
      std::memcpy(&bits, &grad_norms[i], sizeof(bits));
      h ^= bits;
      h = (h << 17) | (h >> 47);
    }
    s.sync_hash = h;

    if (s.all_synced) {
      std::snprintf(s.status, sizeof(s.status),
                    "SYNCED: epoch=%u, divergence=%.4f", current_epoch_,
                    max_div);
    } else {
      std::snprintf(s.status, sizeof(s.status),
                    "DIVERGED: epoch=%u, div=%.4f > %.4f", current_epoch_,
                    max_div, MAX_GRAD_DIVERGENCE);
    }

    ++current_epoch_;
    return s;
  }

  uint32_t num_shards() const { return num_shards_; }
  uint32_t epoch() const { return current_epoch_; }

private:
  ShardAssignment shards_[MAX_SHARDS];
  uint32_t num_shards_;
  uint32_t current_epoch_;
};

} // namespace distributed
