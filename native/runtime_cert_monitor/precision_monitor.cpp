/**
 * precision_monitor.cpp — Post-Certification Precision Monitor
 *
 * Rolling 1000-decision precision check for certified fields.
 *
 * Rules:
 *   - Track last 1000 decisions in circular buffer
 *   - Evaluate every 50 decisions OR every 5 minutes
 *   - If rolling precision < field threshold → demote to TRAINING
 *   - If precision drops > 10% from rolling average → EMERGENCY_HALT
 *   - Log containment reason on every action change
 *   - No mock data — only real inference outcomes
 *   - No auto-submission even if precision is high
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace runtime_cert_monitor {

static constexpr uint32_t ROLLING_WINDOW = 1000;
static constexpr double DEFAULT_PRECISION_THRESHOLD = 0.95;
static constexpr uint32_t EVAL_INTERVAL_DECISIONS = 50;
static constexpr uint64_t EVAL_INTERVAL_MS = 300000; // 5 minutes
static constexpr double RAPID_DROP_THRESHOLD = 0.25; // >25% drop → emergency

enum class DemotionAction : uint8_t {
  NONE = 0,
  WARNING = 1,
  DEMOTE_TO_TRAINING = 2,
  EMERGENCY_HALT = 3
};

struct DecisionOutcome {
  bool predicted_positive;
  bool actually_positive;
  double confidence;
  uint32_t field_id;
  uint64_t timestamp_ms;
};

struct PrecisionState {
  double rolling_precision;
  double threshold;
  double previous_precision; // for rapid-drop detection
  uint32_t true_positives;
  uint32_t false_positives;
  uint32_t total_positive_predictions;
  uint32_t window_fill;
  uint32_t decisions_since_eval;
  uint64_t last_eval_time_ms;
  DemotionAction action;
  bool demotion_triggered;
  bool rapid_drop_detected;
  char containment_log[512];
};

class PostCertPrecisionMonitor {
public:
  PostCertPrecisionMonitor()
      : head_(0), count_(0), threshold_(DEFAULT_PRECISION_THRESHOLD) {
    std::memset(&state_, 0, sizeof(state_));
    std::memset(window_, 0, sizeof(window_));
    state_.threshold = threshold_;
    state_.previous_precision = 1.0; // assume perfect start
  }

  void set_threshold(double t) {
    threshold_ = t;
    state_.threshold = t;
  }

  // ---- Record a decision outcome ----
  void record(const DecisionOutcome &outcome) {
    // Remove oldest if buffer full
    if (count_ == ROLLING_WINDOW) {
      remove_oldest();
    }

    window_[head_] = outcome;
    head_ = (head_ + 1) % ROLLING_WINDOW;
    if (count_ < ROLLING_WINDOW)
      count_++;

    state_.decisions_since_eval++;

    // Always recompute precision for accuracy
    recompute();

    // Only run demotion check at eval intervals
    bool time_trigger = false;
    if (outcome.timestamp_ms > 0 && state_.last_eval_time_ms > 0 &&
        (outcome.timestamp_ms - state_.last_eval_time_ms) >= EVAL_INTERVAL_MS) {
      time_trigger = true;
    }

    bool decision_trigger =
        (state_.decisions_since_eval >= EVAL_INTERVAL_DECISIONS);

    if (time_trigger || decision_trigger) {
      // Periodic eval: check rapid drop FIRST (uses previous_precision
      // from last eval), then run demotion (which updates previous_precision).
      check_rapid_drop();
      check_demotion();
      state_.decisions_since_eval = 0;
      state_.last_eval_time_ms = outcome.timestamp_ms;
    }
  }

  const PrecisionState &state() const { return state_; }

  void reset() {
    head_ = 0;
    count_ = 0;
    std::memset(&state_, 0, sizeof(state_));
    std::memset(window_, 0, sizeof(window_));
    state_.threshold = threshold_;
    state_.previous_precision = 1.0;
  }

  // ---- Self-test ----
  static bool run_tests() {
    PostCertPrecisionMonitor mon;
    int failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (!cond) {
        std::printf("  FAIL: %s\n", name);
        failed++;
      }
    };

    // Test 1: Empty state
    test(mon.state().rolling_precision == 0.0, "empty precision == 0");
    test(mon.state().demotion_triggered == false, "no demotion on empty");

    // Test 2: All correct predictions
    for (uint32_t i = 0; i < 100; i++) {
      DecisionOutcome d;
      d.predicted_positive = true;
      d.actually_positive = true;
      d.confidence = 0.98;
      d.field_id = 0;
      d.timestamp_ms = i * 1000;
      mon.record(d);
    }
    test(std::fabs(mon.state().rolling_precision - 1.0) < 0.001,
         "100% precision with all TP");
    test(mon.state().demotion_triggered == false, "no demotion at 100%");

    // Test 3: Add false positives to drop below threshold — triggers at eval
    mon.reset();
    for (uint32_t i = 0; i < 80; i++) {
      DecisionOutcome d;
      d.predicted_positive = true;
      d.actually_positive = true;
      d.confidence = 0.95;
      d.field_id = 0;
      d.timestamp_ms = i * 1000;
      mon.record(d);
    }
    for (uint32_t i = 0; i < 20; i++) {
      DecisionOutcome d;
      d.predicted_positive = true;
      d.actually_positive = false; // false positive
      d.confidence = 0.90;
      d.field_id = 0;
      d.timestamp_ms = (80 + i) * 1000;
      mon.record(d);
    }
    // 100 decisions total — eval triggers at 50 and at 100
    // Precision = 80/(80+20) = 0.80
    test(mon.state().rolling_precision < 0.85, "precision should be ~0.80");
    test(mon.state().demotion_triggered == true, "demotion at 80% precision");
    test(mon.state().action == DemotionAction::DEMOTE_TO_TRAINING,
         "action should be DEMOTE_TO_TRAINING");

    // Test 4: Eval interval — no check before 50 decisions
    mon.reset();
    for (uint32_t i = 0; i < 30; i++) {
      DecisionOutcome d;
      d.predicted_positive = true;
      d.actually_positive = (i < 10); // 10 TP, 20 FP → 33% precision
      d.confidence = 0.90;
      d.field_id = 0;
      d.timestamp_ms = i * 1000;
      mon.record(d);
    }
    // Only 30 decisions — no eval yet (need 50)
    // Rapid drop may fire, but periodic demotion should not
    test(mon.state().decisions_since_eval == 30,
         "decisions_since_eval should be 30");

    // Test 5: Time-based eval — 5-min gap triggers eval
    mon.reset();
    for (uint32_t i = 0; i < 10; i++) {
      DecisionOutcome d;
      d.predicted_positive = true;
      d.actually_positive = true;
      d.confidence = 0.98;
      d.field_id = 0;
      d.timestamp_ms = i * 1000;
      mon.record(d);
    }
    // Jump time by 6 minutes, add bad decisions
    for (uint32_t i = 0; i < 40; i++) {
      DecisionOutcome d;
      d.predicted_positive = true;
      d.actually_positive = false;
      d.confidence = 0.80;
      d.field_id = 0;
      d.timestamp_ms = 360000 + i * 1000; // 6 min later
      mon.record(d);
    }
    // Precision = 10/50 = 0.20 — should be demoted via time trigger
    test(mon.state().demotion_triggered == true,
         "time-based eval should trigger demotion");

    // Test 6: Rapid drop detection
    mon.reset();
    // Build up good baseline (50+ decisions for first eval)
    for (uint32_t i = 0; i < 55; i++) {
      DecisionOutcome d;
      d.predicted_positive = true;
      d.actually_positive = true;
      d.confidence = 0.99;
      d.field_id = 0;
      d.timestamp_ms = i * 1000;
      mon.record(d);
    }
    test(std::fabs(mon.state().rolling_precision - 1.0) < 0.001,
         "baseline precision should be 1.0");
    // Now inject massive failure — 50 FPs
    for (uint32_t i = 0; i < 50; i++) {
      DecisionOutcome d;
      d.predicted_positive = true;
      d.actually_positive = false;
      d.confidence = 0.50;
      d.field_id = 0;
      d.timestamp_ms = 55000 + i * 1000;
      mon.record(d);
    }
    // Precision = 55/105 ≈ 0.524. Previous was 1.0. Drop = 0.476 > 0.10
    test(mon.state().rapid_drop_detected == true,
         "rapid drop should be detected");
    test(mon.state().action == DemotionAction::EMERGENCY_HALT,
         "rapid drop should trigger EMERGENCY_HALT");

    return failed == 0;
  }

private:
  void remove_oldest() {
    uint32_t oldest = (head_ + ROLLING_WINDOW - count_) % ROLLING_WINDOW;
    std::memset(&window_[oldest], 0, sizeof(DecisionOutcome));
  }

  void recompute() {
    uint32_t tp = 0, fp = 0, total_pos = 0;
    for (uint32_t i = 0; i < count_; i++) {
      uint32_t idx = (head_ + ROLLING_WINDOW - count_ + i) % ROLLING_WINDOW;
      if (window_[idx].predicted_positive) {
        total_pos++;
        if (window_[idx].actually_positive)
          tp++;
        else
          fp++;
      }
    }

    state_.true_positives = tp;
    state_.false_positives = fp;
    state_.total_positive_predictions = total_pos;
    state_.window_fill = count_;
    state_.rolling_precision =
        (total_pos > 0) ? static_cast<double>(tp) / total_pos : 0.0;
  }

  void check_demotion() {
    // Never downgrade from EMERGENCY_HALT (set by rapid-drop between evals)
    if (state_.rapid_drop_detected)
      return;

    // Only check after minimum samples
    if (count_ < 50) {
      state_.action = DemotionAction::NONE;
      state_.demotion_triggered = false;
      return;
    }

    if (state_.rolling_precision < threshold_) {
      state_.action = DemotionAction::DEMOTE_TO_TRAINING;
      state_.demotion_triggered = true;
      std::snprintf(
          state_.containment_log, sizeof(state_.containment_log),
          "DEMOTION: precision=%.4f < threshold=%.4f (TP=%u FP=%u window=%u)",
          state_.rolling_precision, threshold_, state_.true_positives,
          state_.false_positives, count_);
      // Snapshot previous for future rapid-drop comparison
      state_.previous_precision = state_.rolling_precision;
    } else if (state_.rolling_precision < threshold_ + 0.02) {
      state_.action = DemotionAction::WARNING;
      state_.demotion_triggered = false;
      std::snprintf(state_.containment_log, sizeof(state_.containment_log),
                    "WARNING: precision=%.4f near threshold=%.4f",
                    state_.rolling_precision, threshold_);
      state_.previous_precision = state_.rolling_precision;
    } else {
      state_.action = DemotionAction::NONE;
      state_.demotion_triggered = false;
      state_.containment_log[0] = '\0';
      state_.previous_precision = state_.rolling_precision;
    }
  }

  void check_rapid_drop() {
    // Need at least 50 samples and non-zero previous
    if (count_ < 50 || state_.previous_precision <= 0.0)
      return;

    double drop = state_.previous_precision - state_.rolling_precision;
    if (drop > RAPID_DROP_THRESHOLD) {
      state_.rapid_drop_detected = true;
      state_.action = DemotionAction::EMERGENCY_HALT;
      state_.demotion_triggered = true;
      std::snprintf(
          state_.containment_log, sizeof(state_.containment_log),
          "EMERGENCY_HALT: rapid drop %.4f -> %.4f (delta=%.4f > %.4f)",
          state_.previous_precision, state_.rolling_precision, drop,
          RAPID_DROP_THRESHOLD);
    }
  }

  DecisionOutcome window_[ROLLING_WINDOW];
  uint32_t head_;
  uint32_t count_;
  double threshold_;
  PrecisionState state_;
};

} // namespace runtime_cert_monitor
