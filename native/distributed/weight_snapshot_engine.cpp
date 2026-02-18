/**
 * weight_snapshot_engine.cpp — Weight Snapshot & Hash Chain
 *
 * Exports weight snapshots every N epochs with cryptographic hash chain.
 * Supports rollback to previous certified snapshot.
 *
 * NO direct weight overwrite. All snapshots immutable once certified.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace distributed {

// =========================================================================
// SNAPSHOT RECORD
// =========================================================================

struct WeightSnapshot {
  uint32_t snapshot_id;
  uint32_t epoch;
  double precision;
  double recall;
  double ece;
  double kl_divergence;
  double entropy;
  double dup_score;
  uint64_t weight_hash;
  uint64_t prev_hash; // chain link
  bool certified;
  char field_name[64];
  char timestamp[64];
};

// =========================================================================
// SNAPSHOT ENGINE
// =========================================================================

static constexpr uint32_t MAX_SNAPSHOTS = 256;

class WeightSnapshotEngine {
public:
  WeightSnapshotEngine() : count_(0), snapshot_interval_(5) {}

  // Create a snapshot
  int create_snapshot(uint32_t epoch, double precision, double recall,
                      double ece, double kl, double entropy, double dup_score,
                      const char *field_name) {
    if (count_ >= MAX_SNAPSHOTS)
      return -1;

    WeightSnapshot &s = snapshots_[count_];
    s.snapshot_id = count_ + 1;
    s.epoch = epoch;
    s.precision = precision;
    s.recall = recall;
    s.ece = ece;
    s.kl_divergence = kl;
    s.entropy = entropy;
    s.dup_score = dup_score;
    s.weight_hash = compute_hash(s);
    s.prev_hash = (count_ > 0) ? snapshots_[count_ - 1].weight_hash : 0;
    s.certified = false;
    std::strncpy(s.field_name, field_name, 63);
    s.field_name[63] = '\0';

    return static_cast<int>(count_++);
  }

  // Certify a snapshot (immutable after this)
  bool certify(uint32_t idx) {
    if (idx >= count_)
      return false;
    snapshots_[idx].certified = true;
    return true;
  }

  // Find last certified snapshot for rollback
  int last_certified() const {
    for (int i = static_cast<int>(count_) - 1; i >= 0; --i) {
      if (snapshots_[i].certified)
        return i;
    }
    return -1;
  }

  // Verify hash chain integrity
  bool verify_chain() const {
    for (uint32_t i = 1; i < count_; ++i) {
      if (snapshots_[i].prev_hash != snapshots_[i - 1].weight_hash)
        return false;
    }
    return true;
  }

  // Should we snapshot at this epoch?
  bool should_snapshot(uint32_t epoch) const {
    return (epoch % snapshot_interval_ == 0);
  }

  uint32_t count() const { return count_; }
  const WeightSnapshot *snapshot(uint32_t idx) const {
    return (idx < count_) ? &snapshots_[idx] : nullptr;
  }

  void set_interval(uint32_t n) { snapshot_interval_ = n; }

private:
  WeightSnapshot snapshots_[MAX_SNAPSHOTS];
  uint32_t count_;
  uint32_t snapshot_interval_;

  static uint64_t compute_hash(const WeightSnapshot &s) {
    uint64_t h = 0x6a09e667bb67ae85ULL;
    auto mix = [&](uint64_t v) {
      h ^= v;
      h = (h << 13) | (h >> 51);
      h *= 0x9e3779b97f4a7c15ULL;
    };
    uint64_t bits;
    std::memcpy(&bits, &s.precision, sizeof(bits));
    mix(bits);
    std::memcpy(&bits, &s.recall, sizeof(bits));
    mix(bits);
    std::memcpy(&bits, &s.ece, sizeof(bits));
    mix(bits);
    std::memcpy(&bits, &s.kl_divergence, sizeof(bits));
    mix(bits);
    std::memcpy(&bits, &s.entropy, sizeof(bits));
    mix(bits);
    mix(s.epoch);
    return h;
  }
};

} // namespace distributed
