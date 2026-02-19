/**
 * hunt_precision_guard.cpp — Hunt-Mode Precision Gate
 *
 * Rules:
 *   - Every hunt finding must have confidence ≥ 0.93
 *   - Runtime precision monitor must be active during hunt
 *   - No auto-submission regardless of confidence
 *   - Log all gating decisions
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace hunt_guard {

static constexpr double MIN_HUNT_CONFIDENCE = 0.93;
static constexpr double MIN_HUNT_PRECISION = 0.95;
static constexpr uint32_t MAX_GATE_LOG = 500;

enum class HuntGateResult : uint8_t {
  PASS = 0,
  BLOCKED_LOW_CONFIDENCE = 1,
  BLOCKED_LOW_PRECISION = 2,
  BLOCKED_MONITOR_INACTIVE = 3,
  BLOCKED_NO_APPROVAL = 4
};

struct HuntFinding {
  uint32_t finding_id;
  uint32_t field_id;
  double confidence;
  double precision_at_time;
  bool monitor_active;
  bool human_approved;
  uint64_t timestamp_ms;
};

struct GateDecision {
  uint32_t finding_id;
  HuntGateResult result;
  char reason[256];
};

struct HuntPrecisionState {
  uint32_t findings_reviewed;
  uint32_t findings_passed;
  uint32_t findings_blocked;
  double min_confidence_seen;
  double max_confidence_seen;
  double avg_confidence;
  bool guard_active;
};

class HuntPrecisionGuard {
public:
  HuntPrecisionGuard() : log_count_(0), conf_sum_(0.0) {
    std::memset(&state_, 0, sizeof(state_));
    std::memset(log_, 0, sizeof(log_));
    state_.guard_active = true;
    state_.min_confidence_seen = 1.0;
  }

  GateDecision evaluate(const HuntFinding &finding) {
    GateDecision d;
    std::memset(&d, 0, sizeof(d));
    d.finding_id = finding.finding_id;

    state_.findings_reviewed++;
    conf_sum_ += finding.confidence;
    state_.avg_confidence = conf_sum_ / state_.findings_reviewed;
    if (finding.confidence < state_.min_confidence_seen)
      state_.min_confidence_seen = finding.confidence;
    if (finding.confidence > state_.max_confidence_seen)
      state_.max_confidence_seen = finding.confidence;

    // Gate 1: Monitor must be active
    if (!finding.monitor_active) {
      d.result = HuntGateResult::BLOCKED_MONITOR_INACTIVE;
      std::snprintf(d.reason, sizeof(d.reason),
                    "BLOCKED: runtime precision monitor not active");
      state_.findings_blocked++;
      log_decision(d);
      return d;
    }

    // Gate 2: Confidence ≥ 0.93
    if (finding.confidence < MIN_HUNT_CONFIDENCE) {
      d.result = HuntGateResult::BLOCKED_LOW_CONFIDENCE;
      std::snprintf(d.reason, sizeof(d.reason),
                    "BLOCKED: confidence=%.4f < %.4f minimum",
                    finding.confidence, MIN_HUNT_CONFIDENCE);
      state_.findings_blocked++;
      log_decision(d);
      return d;
    }

    // Gate 3: Runtime precision above threshold
    if (finding.precision_at_time < MIN_HUNT_PRECISION) {
      d.result = HuntGateResult::BLOCKED_LOW_PRECISION;
      std::snprintf(d.reason, sizeof(d.reason),
                    "BLOCKED: runtime precision=%.4f < %.4f",
                    finding.precision_at_time, MIN_HUNT_PRECISION);
      state_.findings_blocked++;
      log_decision(d);
      return d;
    }

    // Gate 4: Human approval required (NO auto-submission)
    if (!finding.human_approved) {
      d.result = HuntGateResult::BLOCKED_NO_APPROVAL;
      std::snprintf(d.reason, sizeof(d.reason),
                    "BLOCKED: no human approval — NO auto-submission allowed");
      state_.findings_blocked++;
      log_decision(d);
      return d;
    }

    d.result = HuntGateResult::PASS;
    std::snprintf(d.reason, sizeof(d.reason),
                  "PASS: conf=%.4f prec=%.4f approved=yes", finding.confidence,
                  finding.precision_at_time);
    state_.findings_passed++;
    log_decision(d);
    return d;
  }

  const HuntPrecisionState &state() const { return state_; }

  void reset() {
    log_count_ = 0;
    conf_sum_ = 0.0;
    std::memset(&state_, 0, sizeof(state_));
    std::memset(log_, 0, sizeof(log_));
    state_.guard_active = true;
    state_.min_confidence_seen = 1.0;
  }

  // ---- Self-test ----
  static bool run_tests() {
    HuntPrecisionGuard guard;
    int failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (!cond) {
        std::printf("  FAIL: %s\n", name);
        failed++;
      }
    };

    // Test: Good finding with approval → pass
    HuntFinding f1 = {1, 0, 0.97, 0.96, true, true, 1000};
    auto d1 = guard.evaluate(f1);
    test(d1.result == HuntGateResult::PASS, "good finding passes");

    // Test: Low confidence → blocked
    HuntFinding f2 = {2, 0, 0.85, 0.96, true, true, 2000};
    auto d2 = guard.evaluate(f2);
    test(d2.result == HuntGateResult::BLOCKED_LOW_CONFIDENCE,
         "low conf blocked");

    // Test: No human approval → blocked (NO auto-submit)
    HuntFinding f3 = {3, 0, 0.97, 0.96, true, false, 3000};
    auto d3 = guard.evaluate(f3);
    test(d3.result == HuntGateResult::BLOCKED_NO_APPROVAL,
         "no approval blocked");

    // Test: Monitor inactive → blocked
    HuntFinding f4 = {4, 0, 0.97, 0.96, false, true, 4000};
    auto d4 = guard.evaluate(f4);
    test(d4.result == HuntGateResult::BLOCKED_MONITOR_INACTIVE,
         "no monitor blocked");

    test(guard.state().findings_reviewed == 4, "4 reviewed");
    test(guard.state().findings_passed == 1, "1 passed");
    test(guard.state().findings_blocked == 3, "3 blocked");

    return failed == 0;
  }

private:
  void log_decision(const GateDecision &d) {
    if (log_count_ < MAX_GATE_LOG) {
      log_[log_count_++] = d;
    }
  }

  GateDecision log_[MAX_GATE_LOG];
  uint32_t log_count_;
  double conf_sum_;
  HuntPrecisionState state_;
};

} // namespace hunt_guard
