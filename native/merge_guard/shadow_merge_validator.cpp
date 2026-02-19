/**
 * shadow_merge_validator.cpp — Dual-Head Merge Safety Validator
 *
 * Before merging a candidate model:
 *   1. Load candidate alongside current model
 *   2. Run dual-head inference on validation set
 *   3. Compare precision delta, calibration delta, dup detection delta
 *   4. Reject if degradation > tolerance
 *   5. Automatic rollback snapshot on rejection
 *
 * NO mid-training merge.
 * NO auto-submission of merge results.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace merge_guard {

static constexpr double DEFAULT_PRECISION_TOLERANCE = 0.02;
static constexpr double DEFAULT_CALIBRATION_TOLERANCE = 0.005;
static constexpr double DEFAULT_DUP_TOLERANCE = 0.03;
static constexpr uint32_t MAX_VALIDATION_SAMPLES = 10000;

enum class MergeDecision : uint8_t {
  PENDING = 0,
  APPROVED = 1,
  REJECTED_PRECISION = 2,
  REJECTED_CALIBRATION = 3,
  REJECTED_DUPLICATION = 4,
  REJECTED_MULTIPLE = 5,
  ROLLBACK_TRIGGERED = 6
};

struct ModelSnapshot {
  uint64_t weight_hash;
  double precision;
  double ece;
  double dup_detection_rate;
  uint32_t feature_dims;
  uint32_t sample_count;
  bool valid;
};

struct MergeResult {
  MergeDecision decision;
  double precision_delta;
  double calibration_delta;
  double dup_delta;
  bool precision_pass;
  bool calibration_pass;
  bool dup_pass;
  bool rollback_applied;
  char reason[512];
  ModelSnapshot rollback_snapshot;
};

struct MergeTolerances {
  double precision_tolerance;
  double calibration_tolerance;
  double dup_tolerance;
};

class ShadowMergeValidator {
public:
  ShadowMergeValidator() {
    std::memset(&current_, 0, sizeof(current_));
    std::memset(&candidate_, 0, sizeof(candidate_));
    std::memset(&result_, 0, sizeof(result_));
    tolerances_ = {DEFAULT_PRECISION_TOLERANCE, DEFAULT_CALIBRATION_TOLERANCE,
                   DEFAULT_DUP_TOLERANCE};
  }

  void set_tolerances(double prec, double cal, double dup) {
    tolerances_.precision_tolerance = prec;
    tolerances_.calibration_tolerance = cal;
    tolerances_.dup_tolerance = dup;
  }

  // ---- Set current model snapshot ----
  void set_current(uint64_t hash, double prec, double ece, double dup,
                   uint32_t dims, uint32_t samples) {
    current_.weight_hash = hash;
    current_.precision = prec;
    current_.ece = ece;
    current_.dup_detection_rate = dup;
    current_.feature_dims = dims;
    current_.sample_count = samples;
    current_.valid = true;
  }

  // ---- Set candidate model metrics ----
  void set_candidate(uint64_t hash, double prec, double ece, double dup,
                     uint32_t dims, uint32_t samples) {
    candidate_.weight_hash = hash;
    candidate_.precision = prec;
    candidate_.ece = ece;
    candidate_.dup_detection_rate = dup;
    candidate_.feature_dims = dims;
    candidate_.sample_count = samples;
    candidate_.valid = true;
  }

  // ---- Evaluate merge safety ----
  MergeResult evaluate() {
    std::memset(&result_, 0, sizeof(result_));

    if (!current_.valid || !candidate_.valid) {
      result_.decision = MergeDecision::PENDING;
      std::snprintf(result_.reason, sizeof(result_.reason),
                    "INVALID: both models must have valid snapshots");
      return result_;
    }

    // Compute deltas (negative = candidate is worse)
    result_.precision_delta = candidate_.precision - current_.precision;
    result_.calibration_delta =
        candidate_.ece - current_.ece; // positive = worse
    result_.dup_delta =
        candidate_.dup_detection_rate - current_.dup_detection_rate;

    // Check tolerances
    result_.precision_pass =
        (result_.precision_delta >= -tolerances_.precision_tolerance);
    result_.calibration_pass =
        (result_.calibration_delta <= tolerances_.calibration_tolerance);
    result_.dup_pass = (result_.dup_delta >= -tolerances_.dup_tolerance);

    uint32_t failures = 0;
    if (!result_.precision_pass)
      failures++;
    if (!result_.calibration_pass)
      failures++;
    if (!result_.dup_pass)
      failures++;

    if (failures == 0) {
      result_.decision = MergeDecision::APPROVED;
      std::snprintf(
          result_.reason, sizeof(result_.reason),
          "MERGE_APPROVED: prec_delta=%.4f cal_delta=%.4f dup_delta=%.4f",
          result_.precision_delta, result_.calibration_delta,
          result_.dup_delta);
    } else {
      // Rollback
      result_.rollback_applied = true;
      result_.rollback_snapshot = current_;

      if (failures > 1) {
        result_.decision = MergeDecision::REJECTED_MULTIPLE;
      } else if (!result_.precision_pass) {
        result_.decision = MergeDecision::REJECTED_PRECISION;
      } else if (!result_.calibration_pass) {
        result_.decision = MergeDecision::REJECTED_CALIBRATION;
      } else {
        result_.decision = MergeDecision::REJECTED_DUPLICATION;
      }

      std::snprintf(
          result_.reason, sizeof(result_.reason),
          "MERGE_REJECTED: prec=%s(%.4f) cal=%s(%.4f) dup=%s(%.4f) — ROLLBACK",
          result_.precision_pass ? "OK" : "FAIL", result_.precision_delta,
          result_.calibration_pass ? "OK" : "FAIL", result_.calibration_delta,
          result_.dup_pass ? "OK" : "FAIL", result_.dup_delta);
    }

    return result_;
  }

  const MergeResult &last_result() const { return result_; }

  void reset() {
    std::memset(&current_, 0, sizeof(current_));
    std::memset(&candidate_, 0, sizeof(candidate_));
    std::memset(&result_, 0, sizeof(result_));
  }

  // ---- Self-test ----
  static bool run_tests() {
    ShadowMergeValidator v;
    int failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (!cond) {
        std::printf("  FAIL: %s\n", name);
        failed++;
      }
    };

    // Test: Good candidate → approved
    v.set_current(100, 0.97, 0.015, 0.90, 512, 5000);
    v.set_candidate(200, 0.98, 0.013, 0.92, 512, 5000);
    auto r = v.evaluate();
    test(r.decision == MergeDecision::APPROVED, "better candidate approved");
    test(r.rollback_applied == false, "no rollback on approval");

    // Test: Worse precision → rejected
    v.reset();
    v.set_current(100, 0.97, 0.015, 0.90, 512, 5000);
    v.set_candidate(200, 0.93, 0.015, 0.90, 512, 5000);
    r = v.evaluate();
    test(r.decision == MergeDecision::REJECTED_PRECISION,
         "worse prec rejected");
    test(r.rollback_applied == true, "rollback on rejection");
    test(r.rollback_snapshot.weight_hash == 100, "rollback has current hash");

    // Test: Multiple failures
    v.reset();
    v.set_current(100, 0.97, 0.010, 0.90, 512, 5000);
    v.set_candidate(200, 0.93, 0.030, 0.85, 512, 5000);
    r = v.evaluate();
    test(r.decision == MergeDecision::REJECTED_MULTIPLE, "multiple failures");

    return failed == 0;
  }

private:
  ModelSnapshot current_;
  ModelSnapshot candidate_;
  MergeResult result_;
  MergeTolerances tolerances_;
};

} // namespace merge_guard
