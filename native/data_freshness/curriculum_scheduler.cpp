/**
 * curriculum_scheduler.cpp — Curriculum Freshness Scheduler
 *
 * Rules:
 *   - Track training cycle metrics for improvement
 *   - Detect stagnation: no improvement for N consecutive cycles
 *   - Require new data injection when stagnant
 *   - Prevent infinite overfitting loop by tracking loss plateau
 *   - Log all scheduling decisions
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace data_freshness {

static constexpr uint32_t MAX_CYCLE_HISTORY = 200;
static constexpr uint32_t DEFAULT_STAGNATION_CYCLES = 15;
static constexpr double IMPROVEMENT_EPSILON = 0.001;
static constexpr double OVERFITTING_THRESHOLD = 0.05;

enum class SchedulerAction : uint8_t {
  CONTINUE = 0,
  WARNING_PLATEAU = 1,
  INJECT_DATA = 2,
  HALT_OVERFITTING = 3
};

struct CycleMetrics {
  uint32_t cycle;
  double train_loss;
  double val_loss;
  double precision;
  double feature_entropy;
  uint32_t new_samples;
  uint64_t timestamp_ms;
};

struct SchedulerState {
  uint32_t total_cycles;
  uint32_t stagnant_cycles;
  uint32_t stagnation_limit;
  double best_val_loss;
  double current_val_loss;
  double overfit_gap;  // val_loss - train_loss gap
  double previous_gap; // previous cycle's gap for trend detection
  bool data_injection_required;
  bool overfitting_detected;
  SchedulerAction action;
  char reason[256];
};

class CurriculumScheduler {
public:
  CurriculumScheduler()
      : count_(0), best_val_loss_(1e9),
        stagnation_limit_(DEFAULT_STAGNATION_CYCLES) {
    std::memset(&state_, 0, sizeof(state_));
    std::memset(history_, 0, sizeof(history_));
    state_.stagnation_limit = stagnation_limit_;
    state_.best_val_loss = best_val_loss_;
    state_.previous_gap = -1.0; // sentinel: no prior gap
  }

  void set_stagnation_limit(uint32_t limit) {
    stagnation_limit_ = limit;
    state_.stagnation_limit = limit;
  }

  void record_cycle(const CycleMetrics &cycle) {
    if (count_ < MAX_CYCLE_HISTORY) {
      history_[count_++] = cycle;
    } else {
      // Shift oldest out
      for (uint32_t i = 1; i < MAX_CYCLE_HISTORY; i++) {
        history_[i - 1] = history_[i];
      }
      history_[MAX_CYCLE_HISTORY - 1] = cycle;
    }

    evaluate();
  }

  const SchedulerState &state() const { return state_; }

  void reset() {
    count_ = 0;
    best_val_loss_ = 1e9;
    std::memset(&state_, 0, sizeof(state_));
    std::memset(history_, 0, sizeof(history_));
    state_.stagnation_limit = stagnation_limit_;
    state_.best_val_loss = best_val_loss_;
    state_.previous_gap = -1.0; // sentinel: no prior gap
  }

  // ---- Self-test ----
  static bool run_tests() {
    CurriculumScheduler sched;
    sched.set_stagnation_limit(5);
    int failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (!cond) {
        std::printf("  FAIL: %s\n", name);
        failed++;
      }
    };

    // Test: Improving cycles → continue
    for (uint32_t i = 0; i < 10; i++) {
      CycleMetrics m;
      m.cycle = i;
      m.train_loss = 0.5 - (i * 0.03);
      m.val_loss = 0.6 - (i * 0.03);
      m.precision = 0.80 + (i * 0.01);
      m.feature_entropy = 4.0;
      m.new_samples = 100;
      m.timestamp_ms = i * 1000;
      sched.record_cycle(m);
    }
    test(sched.state().action == SchedulerAction::CONTINUE,
         "improving = continue");
    test(sched.state().data_injection_required == false, "no data needed");

    // Test: Stagnation → inject data
    sched.reset();
    sched.set_stagnation_limit(5);
    for (uint32_t i = 0; i < 10; i++) {
      CycleMetrics m;
      m.cycle = i;
      m.train_loss = 0.30;
      m.val_loss = 0.35; // Same every cycle
      m.precision = 0.90;
      m.feature_entropy = 3.5;
      m.new_samples = 0;
      m.timestamp_ms = i * 1000;
      sched.record_cycle(m);
    }
    test(sched.state().stagnant_cycles >= 5, "stagnation detected");
    test(sched.state().data_injection_required == true,
         "data injection needed");

    // Test: Overfitting detection
    sched.reset();
    for (uint32_t i = 0; i < 10; i++) {
      CycleMetrics m;
      m.cycle = i;
      m.train_loss = 0.10 - (i * 0.008); // Train improving
      m.val_loss = 0.30 + (i * 0.01);    // Val worsening
      m.precision = 0.90;
      m.feature_entropy = 4.0;
      m.new_samples = 0;
      m.timestamp_ms = i * 1000;
      sched.record_cycle(m);
    }
    test(sched.state().overfitting_detected == true, "overfitting detected");
    test(sched.state().action == SchedulerAction::HALT_OVERFITTING,
         "halt on overfitting");

    return failed == 0;
  }

private:
  void evaluate() {
    if (count_ == 0)
      return;

    const auto &latest = history_[count_ - 1];
    state_.total_cycles = count_;
    state_.current_val_loss = latest.val_loss;

    // Track best val_loss
    if (latest.val_loss < best_val_loss_ - IMPROVEMENT_EPSILON) {
      best_val_loss_ = latest.val_loss;
      state_.stagnant_cycles = 0;
    } else {
      state_.stagnant_cycles++;
    }
    state_.best_val_loss = best_val_loss_;

    // Overfitting: gap between val and train is WIDENING
    double current_gap = latest.val_loss - latest.train_loss;
    bool gap_widening =
        (state_.previous_gap >= 0.0 &&
         current_gap > state_.previous_gap + IMPROVEMENT_EPSILON);
    state_.overfit_gap = current_gap;
    state_.overfitting_detected =
        (current_gap > OVERFITTING_THRESHOLD && gap_widening && count_ >= 5);
    state_.previous_gap = current_gap;

    // Determine action
    if (state_.overfitting_detected) {
      state_.action = SchedulerAction::HALT_OVERFITTING;
      state_.data_injection_required = true;
      std::snprintf(state_.reason, sizeof(state_.reason),
                    "OVERFITTING: gap=%.4f > %.4f (train=%.4f val=%.4f)",
                    state_.overfit_gap, OVERFITTING_THRESHOLD,
                    latest.train_loss, latest.val_loss);
    } else if (state_.stagnant_cycles >= stagnation_limit_) {
      state_.action = SchedulerAction::INJECT_DATA;
      state_.data_injection_required = true;
      std::snprintf(state_.reason, sizeof(state_.reason),
                    "STAGNATION: %u cycles without improvement (limit=%u)",
                    state_.stagnant_cycles, stagnation_limit_);
    } else if (state_.stagnant_cycles >= stagnation_limit_ / 2) {
      state_.action = SchedulerAction::WARNING_PLATEAU;
      state_.data_injection_required = false;
      std::snprintf(state_.reason, sizeof(state_.reason),
                    "WARNING: %u stagnant cycles (limit=%u)",
                    state_.stagnant_cycles, stagnation_limit_);
    } else {
      state_.action = SchedulerAction::CONTINUE;
      state_.data_injection_required = false;
      state_.reason[0] = '\0';
    }
  }

  CycleMetrics history_[MAX_CYCLE_HISTORY];
  uint32_t count_;
  double best_val_loss_;
  uint32_t stagnation_limit_;
  SchedulerState state_;
};

} // namespace data_freshness
