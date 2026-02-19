// ============================================================
// FIELD FREEZE GUARD — IMMUTABLE POST-CERTIFICATION LOCK
// ============================================================
// Upon field certification:
//   1. Snapshot weight hash
//   2. Store calibration baseline
//   3. Lock feature dimensions
//   4. All future merges validated against frozen state
// ============================================================

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


// ============================================================
// CONSTANTS
// ============================================================
static constexpr uint32_t MAX_HASH_LEN = 64;
static constexpr uint32_t MAX_FIELDS = 32;
static constexpr double MAX_CALIB_DELTA = 0.015; // max calibration drift
static constexpr double MAX_DRIFT_DELTA = 0.02;  // max feature drift
static constexpr uint32_t MAX_DIM_CHANGE = 0;    // NO dimension changes

// ============================================================
// FROZEN FIELD SNAPSHOT
// ============================================================
struct FrozenSnapshot {
  uint32_t field_id;
  char weight_hash[MAX_HASH_LEN + 1]; // SHA-256 of weights
  double calibration_ece;             // ECE at freeze time
  double calibration_precision;       // precision at freeze time
  double calibration_fpr;             // FPR at freeze time
  uint32_t feature_dimensions;        // locked feature count
  uint64_t freeze_timestamp;          // epoch seconds
  bool is_frozen;
};

// ============================================================
// MERGE REQUEST — incoming merge to validate
// ============================================================
struct MergeCandidate {
  uint32_t field_id;
  char new_weight_hash[MAX_HASH_LEN + 1];
  double new_ece;
  double new_precision;
  double new_fpr;
  uint32_t new_feature_dimensions;
};

// ============================================================
// VALIDATION RESULT
// ============================================================
struct FreezeValidation {
  bool allowed;
  bool hash_valid;
  bool calibration_compatible;
  bool drift_compatible;
  bool dimensions_compatible;
  uint32_t checks_passed;
  uint32_t checks_total;
  char reason[256];
};

// ============================================================
// FREEZE GUARD ENGINE
// ============================================================
class FieldFreezeGuard {
public:
  FieldFreezeGuard() {
    std::memset(snapshots_, 0, sizeof(snapshots_));
    frozen_count_ = 0;
  }

  // --------------------------------------------------------
  // FREEZE — lock field post-certification
  // --------------------------------------------------------
  bool freeze_field(uint32_t field_id, const char *weight_hash, double ece,
                    double precision, double fpr, uint32_t feature_dims,
                    uint64_t timestamp) {
    if (field_id >= MAX_FIELDS)
      return false;
    if (snapshots_[field_id].is_frozen)
      return false; // already frozen

    FrozenSnapshot &s = snapshots_[field_id];
    s.field_id = field_id;
    std::strncpy(s.weight_hash, weight_hash, MAX_HASH_LEN);
    s.weight_hash[MAX_HASH_LEN] = '\0';
    s.calibration_ece = ece;
    s.calibration_precision = precision;
    s.calibration_fpr = fpr;
    s.feature_dimensions = feature_dims;
    s.freeze_timestamp = timestamp;
    s.is_frozen = true;
    frozen_count_++;

    return true;
  }

  // --------------------------------------------------------
  // VALIDATE MERGE — check against frozen state
  // --------------------------------------------------------
  FreezeValidation validate_merge(const MergeCandidate &m) const {
    FreezeValidation v;
    std::memset(&v, 0, sizeof(v));
    v.checks_total = 4;

    if (m.field_id >= MAX_FIELDS || !snapshots_[m.field_id].is_frozen) {
      v.allowed = false;
      std::snprintf(v.reason, sizeof(v.reason),
                    "REJECT: field %u not frozen — cannot validate merge",
                    m.field_id);
      return v;
    }

    const FrozenSnapshot &s = snapshots_[m.field_id];

    // 1. Hash validation — must match frozen state
    v.hash_valid = (std::strcmp(s.weight_hash, m.new_weight_hash) == 0);
    if (v.hash_valid)
      v.checks_passed++;

    // 2. Calibration delta check
    double ece_delta = std::fabs(m.new_ece - s.calibration_ece);
    v.calibration_compatible = (ece_delta <= MAX_CALIB_DELTA);
    if (v.calibration_compatible)
      v.checks_passed++;

    // 3. Drift compatibility (precision + FPR)
    double prec_delta = std::fabs(m.new_precision - s.calibration_precision);
    double fpr_delta = std::fabs(m.new_fpr - s.calibration_fpr);
    v.drift_compatible =
        (prec_delta <= MAX_DRIFT_DELTA && fpr_delta <= MAX_DRIFT_DELTA);
    if (v.drift_compatible)
      v.checks_passed++;

    // 4. Feature dimensions — MUST NOT change
    v.dimensions_compatible =
        (m.new_feature_dimensions == s.feature_dimensions);
    if (v.dimensions_compatible)
      v.checks_passed++;

    // Overall
    v.allowed = (v.checks_passed == v.checks_total);

    if (v.allowed) {
      std::snprintf(v.reason, sizeof(v.reason),
                    "MERGE_ALLOWED: field %u — all %u checks passed",
                    m.field_id, v.checks_total);
    } else {
      std::snprintf(v.reason, sizeof(v.reason),
                    "MERGE_REJECTED: field %u — %u/%u checks passed "
                    "[hash=%s cal=%s drift=%s dim=%s]",
                    m.field_id, v.checks_passed, v.checks_total,
                    v.hash_valid ? "OK" : "FAIL",
                    v.calibration_compatible ? "OK" : "FAIL",
                    v.drift_compatible ? "OK" : "FAIL",
                    v.dimensions_compatible ? "OK" : "FAIL");
    }

    return v;
  }

  // --------------------------------------------------------
  // QUERY
  // --------------------------------------------------------
  bool is_frozen(uint32_t field_id) const {
    if (field_id >= MAX_FIELDS)
      return false;
    return snapshots_[field_id].is_frozen;
  }

  uint32_t frozen_count() const { return frozen_count_; }

  const FrozenSnapshot *get_snapshot(uint32_t field_id) const {
    if (field_id >= MAX_FIELDS)
      return nullptr;
    if (!snapshots_[field_id].is_frozen)
      return nullptr;
    return &snapshots_[field_id];
  }

private:
  FrozenSnapshot snapshots_[MAX_FIELDS];
  uint32_t frozen_count_;
};
