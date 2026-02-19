/**
 * hunt_duplicate_guard.cpp — Hunt-Mode Duplicate Risk Gate
 *
 * Rules:
 *   - Duplicate risk score must be < 0.85 to report finding
 *   - Track rolling duplicate risk across hunt session
 *   - Block if too many high-risk duplicates in window
 *   - Log all duplicate assessments
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace hunt_guard {

static constexpr double MAX_DUPLICATE_RISK = 0.85;
static constexpr uint32_t DUP_WINDOW = 200;
static constexpr double DUP_RATE_ALERT = 0.30; // 30% dup rate → alert

enum class DupGateResult : uint8_t {
  PASS = 0,
  BLOCKED_HIGH_RISK = 1,
  BLOCKED_SESSION_DUP_RATE = 2
};

struct DupAssessment {
  uint32_t finding_id;
  double duplicate_risk_score;
  uint32_t closest_match_id;
  double similarity_to_closest;
  uint64_t timestamp_ms;
};

struct DupGateDecision {
  uint32_t finding_id;
  DupGateResult result;
  double risk_score;
  char reason[256];
};

struct DupGuardState {
  uint32_t assessments_total;
  uint32_t blocked_total;
  uint32_t window_count;
  uint32_t window_high_risk;
  double window_dup_rate;
  double avg_risk;
  bool session_alert;
};

class HuntDuplicateGuard {
public:
  HuntDuplicateGuard() : head_(0), count_(0), risk_sum_(0.0) {
    std::memset(&state_, 0, sizeof(state_));
    std::memset(window_, 0, sizeof(window_));
  }

  DupGateDecision evaluate(const DupAssessment &assessment) {
    DupGateDecision d;
    std::memset(&d, 0, sizeof(d));
    d.finding_id = assessment.finding_id;
    d.risk_score = assessment.duplicate_risk_score;

    // Record in window
    window_[head_] = assessment;
    head_ = (head_ + 1) % DUP_WINDOW;
    if (count_ < DUP_WINDOW)
      count_++;

    state_.assessments_total++;
    recompute();

    // Gate 1: Individual duplicate risk
    if (assessment.duplicate_risk_score >= MAX_DUPLICATE_RISK) {
      d.result = DupGateResult::BLOCKED_HIGH_RISK;
      std::snprintf(
          d.reason, sizeof(d.reason),
          "BLOCKED: dup_risk=%.4f >= %.4f (closest_match=%u sim=%.4f)",
          assessment.duplicate_risk_score, MAX_DUPLICATE_RISK,
          assessment.closest_match_id, assessment.similarity_to_closest);
      state_.blocked_total++;
      return d;
    }

    // Gate 2: Session dup rate too high
    if (state_.session_alert) {
      d.result = DupGateResult::BLOCKED_SESSION_DUP_RATE;
      std::snprintf(d.reason, sizeof(d.reason),
                    "BLOCKED: session dup rate=%.4f > %.4f — review required",
                    state_.window_dup_rate, DUP_RATE_ALERT);
      state_.blocked_total++;
      return d;
    }

    d.result = DupGateResult::PASS;
    std::snprintf(d.reason, sizeof(d.reason), "PASS: dup_risk=%.4f < %.4f",
                  assessment.duplicate_risk_score, MAX_DUPLICATE_RISK);
    return d;
  }

  const DupGuardState &state() const { return state_; }

  void reset() {
    head_ = 0;
    count_ = 0;
    risk_sum_ = 0.0;
    std::memset(&state_, 0, sizeof(state_));
    std::memset(window_, 0, sizeof(window_));
  }

  // ---- Self-test ----
  static bool run_tests() {
    HuntDuplicateGuard guard;
    int failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (!cond) {
        std::printf("  FAIL: %s\n", name);
        failed++;
      }
    };

    // Test: Low risk → pass
    DupAssessment a1 = {1, 0.30, 0, 0.25, 1000};
    auto d1 = guard.evaluate(a1);
    test(d1.result == DupGateResult::PASS, "low dup risk passes");

    // Test: High risk → blocked
    DupAssessment a2 = {2, 0.90, 5, 0.88, 2000};
    auto d2 = guard.evaluate(a2);
    test(d2.result == DupGateResult::BLOCKED_HIGH_RISK,
         "high dup risk blocked");

    test(guard.state().blocked_total == 1, "1 blocked");
    test(guard.state().assessments_total == 2, "2 assessed");

    return failed == 0;
  }

private:
  void recompute() {
    uint32_t high_risk = 0;
    double sum = 0.0;
    for (uint32_t i = 0; i < count_; i++) {
      uint32_t idx = (head_ + DUP_WINDOW - count_ + i) % DUP_WINDOW;
      sum += window_[idx].duplicate_risk_score;
      if (window_[idx].duplicate_risk_score >= MAX_DUPLICATE_RISK)
        high_risk++;
    }

    state_.window_count = count_;
    state_.window_high_risk = high_risk;
    state_.avg_risk = (count_ > 0) ? sum / count_ : 0.0;
    state_.window_dup_rate =
        (count_ > 0) ? static_cast<double>(high_risk) / count_ : 0.0;
    state_.session_alert =
        (count_ >= 10 && state_.window_dup_rate > DUP_RATE_ALERT);
  }

  DupAssessment window_[DUP_WINDOW];
  uint32_t head_;
  uint32_t count_;
  double risk_sum_;
  DupGuardState state_;
};

} // namespace hunt_guard
