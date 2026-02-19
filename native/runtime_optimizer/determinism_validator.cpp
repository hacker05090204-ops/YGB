/**
 * determinism_validator.cpp — GPU Training Determinism Proof
 *
 * Rules:
 *   - Run 3 identical training passes with same seed
 *   - Validate identical output hash across all 3 runs
 *   - Validate identical precision
 *   - Validate calibration stability (ECE delta < epsilon)
 *   - Block training start if determinism fails
 *   - Must pass after dynamic batch scaling changes
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace runtime_optimizer {

static constexpr uint32_t REQUIRED_RUNS = 3;
static constexpr double PRECISION_EPSILON = 1e-6;
static constexpr double ECE_EPSILON = 1e-5;

enum class DeterminismResult : uint8_t {
  UNTESTED = 0,
  PASS = 1,
  FAIL_HASH_MISMATCH = 2,
  FAIL_PRECISION_MISMATCH = 3,
  FAIL_CALIBRATION_DRIFT = 4,
  FAIL_MULTIPLE = 5,
  INSUFFICIENT_RUNS = 6
};

struct RunResult {
  uint64_t output_hash;
  double precision;
  double ece;
  uint32_t batch_size;
  uint64_t seed;
  uint64_t duration_ms;
  bool valid;
};

struct DeterminismState {
  DeterminismResult result;
  uint32_t runs_completed;
  bool hash_identical;
  bool precision_identical;
  bool calibration_stable;
  bool training_allowed;
  double max_precision_delta;
  double max_ece_delta;
  char detail[512];
};

class DeterminismValidator {
public:
  DeterminismValidator() : run_count_(0) {
    std::memset(&state_, 0, sizeof(state_));
    std::memset(runs_, 0, sizeof(runs_));
    state_.result = DeterminismResult::UNTESTED;
  }

  // ---- Record a run result ----
  void record_run(const RunResult &run) {
    if (run_count_ < REQUIRED_RUNS) {
      runs_[run_count_++] = run;
      state_.runs_completed = run_count_;

      if (run_count_ == REQUIRED_RUNS) {
        validate();
      }
    }
  }

  const DeterminismState &state() const { return state_; }

  void reset() {
    run_count_ = 0;
    std::memset(&state_, 0, sizeof(state_));
    std::memset(runs_, 0, sizeof(runs_));
    state_.result = DeterminismResult::UNTESTED;
  }

  // ---- Self-test ----
  static bool run_tests() {
    DeterminismValidator v;
    int failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (!cond) {
        std::printf("  FAIL: %s\n", name);
        failed++;
      }
    };

    // Test: 3 identical runs → PASS
    RunResult r1 = {12345, 0.97, 0.015, 64, 42, 1000, true};
    RunResult r2 = {12345, 0.97, 0.015, 64, 42, 1100, true};
    RunResult r3 = {12345, 0.97, 0.015, 64, 42, 950, true};
    v.record_run(r1);
    v.record_run(r2);
    v.record_run(r3);
    test(v.state().result == DeterminismResult::PASS, "identical runs pass");
    test(v.state().training_allowed == true, "training allowed");
    test(v.state().hash_identical == true, "hashes identical");

    // Test: Hash mismatch → FAIL
    v.reset();
    RunResult r4 = {12345, 0.97, 0.015, 64, 42, 1000, true};
    RunResult r5 = {99999, 0.97, 0.015, 64, 42, 1100, true}; // different hash
    RunResult r6 = {12345, 0.97, 0.015, 64, 42, 950, true};
    v.record_run(r4);
    v.record_run(r5);
    v.record_run(r6);
    test(v.state().result == DeterminismResult::FAIL_HASH_MISMATCH ||
             v.state().result == DeterminismResult::FAIL_MULTIPLE,
         "hash mismatch fails");
    test(v.state().training_allowed == false,
         "training blocked on hash mismatch");

    // Test: Precision mismatch → FAIL
    v.reset();
    RunResult r7 = {12345, 0.97, 0.015, 64, 42, 1000, true};
    RunResult r8 = {12345, 0.92, 0.015, 64,
                    42,    1100, true}; // different precision
    RunResult r9 = {12345, 0.97, 0.015, 64, 42, 950, true};
    v.record_run(r7);
    v.record_run(r8);
    v.record_run(r9);
    test(v.state().training_allowed == false,
         "training blocked on precision mismatch");

    // Test: Insufficient runs
    v.reset();
    v.record_run(r1);
    test(v.state().result == DeterminismResult::UNTESTED,
         "untested with 1 run");
    test(v.state().training_allowed == false,
         "training not allowed with 1 run");

    return failed == 0;
  }

private:
  void validate() {
    uint32_t failures = 0;

    // Check hash identity
    state_.hash_identical = true;
    for (uint32_t i = 1; i < REQUIRED_RUNS; i++) {
      if (runs_[i].output_hash != runs_[0].output_hash) {
        state_.hash_identical = false;
        break;
      }
    }
    if (!state_.hash_identical)
      failures++;

    // Check precision identity
    state_.precision_identical = true;
    state_.max_precision_delta = 0.0;
    for (uint32_t i = 1; i < REQUIRED_RUNS; i++) {
      double delta = std::fabs(runs_[i].precision - runs_[0].precision);
      if (delta > state_.max_precision_delta)
        state_.max_precision_delta = delta;
      if (delta > PRECISION_EPSILON) {
        state_.precision_identical = false;
      }
    }
    if (!state_.precision_identical)
      failures++;

    // Check calibration stability
    state_.calibration_stable = true;
    state_.max_ece_delta = 0.0;
    for (uint32_t i = 1; i < REQUIRED_RUNS; i++) {
      double delta = std::fabs(runs_[i].ece - runs_[0].ece);
      if (delta > state_.max_ece_delta)
        state_.max_ece_delta = delta;
      if (delta > ECE_EPSILON) {
        state_.calibration_stable = false;
      }
    }
    if (!state_.calibration_stable)
      failures++;

    // Result
    if (failures == 0) {
      state_.result = DeterminismResult::PASS;
      state_.training_allowed = true;
      std::snprintf(state_.detail, sizeof(state_.detail),
                    "DETERMINISM_PASS: hash=%llu prec=%.6f ece=%.6f — all %u "
                    "runs identical",
                    (unsigned long long)runs_[0].output_hash,
                    runs_[0].precision, runs_[0].ece, REQUIRED_RUNS);
    } else {
      state_.training_allowed = false;

      if (failures > 1) {
        state_.result = DeterminismResult::FAIL_MULTIPLE;
      } else if (!state_.hash_identical) {
        state_.result = DeterminismResult::FAIL_HASH_MISMATCH;
      } else if (!state_.precision_identical) {
        state_.result = DeterminismResult::FAIL_PRECISION_MISMATCH;
      } else {
        state_.result = DeterminismResult::FAIL_CALIBRATION_DRIFT;
      }

      std::snprintf(state_.detail, sizeof(state_.detail),
                    "DETERMINISM_FAIL: hash=%s prec=%s(Δ=%.6f) cal=%s(Δ=%.6f) "
                    "— training BLOCKED",
                    state_.hash_identical ? "OK" : "MISMATCH",
                    state_.precision_identical ? "OK" : "MISMATCH",
                    state_.max_precision_delta,
                    state_.calibration_stable ? "OK" : "DRIFT",
                    state_.max_ece_delta);
    }
  }

  RunResult runs_[REQUIRED_RUNS];
  uint32_t run_count_;
  DeterminismState state_;
};

} // namespace runtime_optimizer
