/**
 * freeze_invalidator.cpp — Freeze Invalidation on Drift Breach
 *
 * Rules:
 *   - Invalidate frozen model snapshot when drift exceeds tolerance
 *   - Log containment event with reason, field_id, snapshot hash
 *   - Trigger re-certification requirement
 *   - No silent drift allowed
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace runtime_cert_monitor {

static constexpr uint32_t MAX_EVENTS = 256;

enum class InvalidationReason : uint8_t {
  NONE = 0,
  PRECISION_BREACH = 1,
  KL_DRIFT_BREACH = 2,
  ECE_CALIBRATION_BREACH = 3,
  HASH_MISMATCH = 4,
  DIMENSION_CHANGE = 5,
  MANUAL_REVOCATION = 6
};

struct FreezeSnapshot {
  uint32_t field_id;
  uint64_t weight_hash;
  double precision_at_freeze;
  double ece_at_freeze;
  double kl_baseline;
  uint32_t feature_dims;
  uint64_t frozen_at_ms;
  bool valid;
};

struct InvalidationEvent {
  uint32_t field_id;
  InvalidationReason reason;
  double breach_value;
  double threshold_value;
  uint64_t timestamp_ms;
  char detail[256];
};

struct InvalidatorState {
  uint32_t event_count;
  bool freeze_valid;
  InvalidationReason last_reason;
  char last_detail[256];
};

class FreezeInvalidator {
public:
  FreezeInvalidator() : event_count_(0) {
    std::memset(&snapshot_, 0, sizeof(snapshot_));
    std::memset(&state_, 0, sizeof(state_));
    std::memset(events_, 0, sizeof(events_));
    state_.freeze_valid = true;
  }

  // ---- Set frozen snapshot ----
  void set_snapshot(uint32_t field_id, uint64_t weight_hash, double precision,
                    double ece, double kl, uint32_t dims, uint64_t frozen_at) {
    snapshot_.field_id = field_id;
    snapshot_.weight_hash = weight_hash;
    snapshot_.precision_at_freeze = precision;
    snapshot_.ece_at_freeze = ece;
    snapshot_.kl_baseline = kl;
    snapshot_.feature_dims = dims;
    snapshot_.frozen_at_ms = frozen_at;
    snapshot_.valid = true;
    state_.freeze_valid = true;
  }

  // ---- Check for invalidation ----
  bool check_precision(double current_precision, double threshold) {
    if (!snapshot_.valid)
      return true;
    if (current_precision < threshold) {
      log_event(snapshot_.field_id, InvalidationReason::PRECISION_BREACH,
                current_precision, threshold,
                "Precision dropped below threshold post-freeze");
      state_.freeze_valid = false;
      return false;
    }
    return true;
  }

  bool check_kl_drift(double current_kl, double tolerance) {
    if (!snapshot_.valid)
      return true;
    if (current_kl > tolerance) {
      log_event(snapshot_.field_id, InvalidationReason::KL_DRIFT_BREACH,
                current_kl, tolerance,
                "KL divergence exceeds dynamic tolerance");
      state_.freeze_valid = false;
      return false;
    }
    return true;
  }

  bool check_ece(double current_ece, double threshold) {
    if (!snapshot_.valid)
      return true;
    if (current_ece > threshold) {
      log_event(snapshot_.field_id, InvalidationReason::ECE_CALIBRATION_BREACH,
                current_ece, threshold,
                "ECE exceeds calibration threshold post-freeze");
      state_.freeze_valid = false;
      return false;
    }
    return true;
  }

  bool check_hash(uint64_t current_hash) {
    if (!snapshot_.valid)
      return true;
    if (current_hash != snapshot_.weight_hash) {
      log_event(snapshot_.field_id, InvalidationReason::HASH_MISMATCH,
                static_cast<double>(current_hash),
                static_cast<double>(snapshot_.weight_hash),
                "Weight hash changed — model modified post-freeze");
      state_.freeze_valid = false;
      return false;
    }
    return true;
  }

  bool check_dimensions(uint32_t current_dims) {
    if (!snapshot_.valid)
      return true;
    if (current_dims != snapshot_.feature_dims) {
      log_event(snapshot_.field_id, InvalidationReason::DIMENSION_CHANGE,
                static_cast<double>(current_dims),
                static_cast<double>(snapshot_.feature_dims),
                "Feature dimensions changed post-freeze");
      state_.freeze_valid = false;
      return false;
    }
    return true;
  }

  const InvalidatorState &state() const { return state_; }
  const FreezeSnapshot &snapshot() const { return snapshot_; }

  void reset() {
    event_count_ = 0;
    std::memset(&snapshot_, 0, sizeof(snapshot_));
    std::memset(&state_, 0, sizeof(state_));
    std::memset(events_, 0, sizeof(events_));
    state_.freeze_valid = true;
  }

  // ---- Self-test ----
  static bool run_tests() {
    FreezeInvalidator inv;
    int failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (!cond) {
        std::printf("  FAIL: %s\n", name);
        failed++;
      }
    };

    inv.set_snapshot(0, 12345, 0.97, 0.015, 0.10, 512, 1000);
    test(inv.state().freeze_valid == true, "freeze valid after snapshot");

    // Good precision
    test(inv.check_precision(0.96, 0.95) == true, "precision OK");
    test(inv.state().freeze_valid == true, "still valid");

    // Bad precision
    test(inv.check_precision(0.80, 0.95) == false, "precision breach");
    test(inv.state().freeze_valid == false, "freeze invalid after breach");

    // Reset and test KL
    inv.reset();
    inv.set_snapshot(1, 67890, 0.98, 0.01, 0.05, 256, 2000);
    test(inv.check_kl_drift(0.60, 0.35) == false, "KL drift breach");
    test(inv.state().freeze_valid == false, "freeze invalid after KL breach");

    // Reset and test hash
    inv.reset();
    inv.set_snapshot(2, 11111, 0.99, 0.008, 0.03, 128, 3000);
    test(inv.check_hash(99999) == false, "hash mismatch");
    test(inv.state().freeze_valid == false,
         "freeze invalid after hash mismatch");

    return failed == 0;
  }

private:
  void log_event(uint32_t field_id, InvalidationReason reason, double breach,
                 double threshold, const char *detail) {
    if (event_count_ < MAX_EVENTS) {
      auto &e = events_[event_count_++];
      e.field_id = field_id;
      e.reason = reason;
      e.breach_value = breach;
      e.threshold_value = threshold;
      e.timestamp_ms = 0; // Would be set from system clock
      std::strncpy(e.detail, detail, sizeof(e.detail) - 1);
    }

    state_.event_count = event_count_;
    state_.last_reason = reason;
    std::strncpy(state_.last_detail, detail, sizeof(state_.last_detail) - 1);
  }

  FreezeSnapshot snapshot_;
  InvalidationEvent events_[MAX_EVENTS];
  uint32_t event_count_;
  InvalidatorState state_;
};

} // namespace runtime_cert_monitor
