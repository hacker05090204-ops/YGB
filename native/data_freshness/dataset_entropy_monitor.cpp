/**
 * dataset_entropy_monitor.cpp — Feature Entropy Floor Monitor
 *
 * Rules:
 *   - Monitor feature entropy across training batches
 *   - Block training if entropy < floor threshold
 *   - Detect stagnation patterns (same entropy for N cycles)
 *   - Prevent infinite overfitting loop
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace data_freshness {

static constexpr uint32_t ENTROPY_HISTORY = 100;
static constexpr double DEFAULT_ENTROPY_FLOOR = 2.0;
static constexpr uint32_t DEFAULT_STAGNATION_CYCLES = 10;
static constexpr double STAGNATION_EPSILON = 0.01;

enum class FreshnessAction : uint8_t {
  HEALTHY = 0,
  WARNING_LOW_ENTROPY = 1,
  BLOCK_TRAINING = 2,
  REQUIRE_NEW_DATA = 3
};

struct EntropySnapshot {
  double feature_entropy;
  double label_entropy;
  uint32_t unique_features;
  uint32_t total_samples;
  uint32_t cycle_number;
};

struct FreshnessState {
  double current_entropy;
  double entropy_floor;
  double entropy_trend;      // negative = declining
  uint32_t stagnation_count; // consecutive similar entropy cycles
  uint32_t stagnation_limit;
  bool training_blocked;
  bool new_data_required;
  FreshnessAction action;
  char reason[256];
};

class DatasetEntropyMonitor {
public:
  DatasetEntropyMonitor()
      : head_(0), count_(0), entropy_floor_(DEFAULT_ENTROPY_FLOOR),
        stagnation_limit_(DEFAULT_STAGNATION_CYCLES) {
    std::memset(&state_, 0, sizeof(state_));
    std::memset(history_, 0, sizeof(history_));
    state_.entropy_floor = entropy_floor_;
    state_.stagnation_limit = stagnation_limit_;
  }

  void set_entropy_floor(double floor) {
    entropy_floor_ = floor;
    state_.entropy_floor = floor;
  }

  void set_stagnation_limit(uint32_t limit) {
    stagnation_limit_ = limit;
    state_.stagnation_limit = limit;
  }

  void record(const EntropySnapshot &snap) {
    history_[head_] = snap;
    head_ = (head_ + 1) % ENTROPY_HISTORY;
    if (count_ < ENTROPY_HISTORY)
      count_++;

    recompute();
    check_freshness();
  }

  const FreshnessState &state() const { return state_; }

  void reset() {
    head_ = 0;
    count_ = 0;
    std::memset(&state_, 0, sizeof(state_));
    std::memset(history_, 0, sizeof(history_));
    state_.entropy_floor = entropy_floor_;
    state_.stagnation_limit = stagnation_limit_;
  }

  // ---- Self-test ----
  static bool run_tests() {
    DatasetEntropyMonitor mon;
    int failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (!cond) {
        std::printf("  FAIL: %s\n", name);
        failed++;
      }
    };

    // Test: Good entropy → healthy
    for (uint32_t i = 0; i < 20; i++) {
      EntropySnapshot s;
      s.feature_entropy = 4.5 + (i * 0.01);
      s.label_entropy = 1.0;
      s.unique_features = 1000;
      s.total_samples = 5000;
      s.cycle_number = i;
      mon.record(s);
    }
    test(mon.state().action == FreshnessAction::HEALTHY,
         "good entropy = healthy");
    test(mon.state().training_blocked == false, "training not blocked");

    // Test: Low entropy → block training
    mon.reset();
    for (uint32_t i = 0; i < 20; i++) {
      EntropySnapshot s;
      s.feature_entropy = 1.0; // Below floor
      s.label_entropy = 0.5;
      s.unique_features = 50;
      s.total_samples = 5000;
      s.cycle_number = i;
      mon.record(s);
    }
    test(mon.state().training_blocked == true, "low entropy blocks training");

    // Test: Stagnation → require new data
    mon.reset();
    mon.set_stagnation_limit(5);
    for (uint32_t i = 0; i < 20; i++) {
      EntropySnapshot s;
      s.feature_entropy = 3.0; // Above floor but stagnant
      s.label_entropy = 1.0;
      s.unique_features = 500;
      s.total_samples = 5000;
      s.cycle_number = i;
      mon.record(s);
    }
    test(mon.state().stagnation_count > 5, "stagnation detected");
    test(mon.state().new_data_required == true, "new data required");

    return failed == 0;
  }

private:
  void recompute() {
    if (count_ == 0)
      return;

    uint32_t latest = (head_ + ENTROPY_HISTORY - 1) % ENTROPY_HISTORY;
    state_.current_entropy = history_[latest].feature_entropy;

    // Compute trend (last 10 samples)
    if (count_ >= 2) {
      uint32_t prev = (head_ + ENTROPY_HISTORY - 2) % ENTROPY_HISTORY;
      state_.entropy_trend =
          history_[latest].feature_entropy - history_[prev].feature_entropy;
    }

    // Stagnation detection
    if (count_ >= 2) {
      uint32_t prev = (head_ + ENTROPY_HISTORY - 2) % ENTROPY_HISTORY;
      double delta = std::fabs(history_[latest].feature_entropy -
                               history_[prev].feature_entropy);
      if (delta < STAGNATION_EPSILON) {
        state_.stagnation_count++;
      } else {
        state_.stagnation_count = 0;
      }
    }
  }

  void check_freshness() {
    // Below entropy floor → block
    if (state_.current_entropy < entropy_floor_) {
      state_.training_blocked = true;
      state_.action = FreshnessAction::BLOCK_TRAINING;
      std::snprintf(state_.reason, sizeof(state_.reason),
                    "BLOCKED: entropy=%.4f < floor=%.4f",
                    state_.current_entropy, entropy_floor_);
      return;
    }

    // Stagnation → require new data
    if (state_.stagnation_count >= stagnation_limit_) {
      state_.new_data_required = true;
      state_.action = FreshnessAction::REQUIRE_NEW_DATA;
      std::snprintf(state_.reason, sizeof(state_.reason),
                    "STAGNATION: %u cycles unchanged (limit=%u)",
                    state_.stagnation_count, stagnation_limit_);
      return;
    }

    // Declining trend warning
    if (state_.entropy_trend < -0.1) {
      state_.action = FreshnessAction::WARNING_LOW_ENTROPY;
      state_.training_blocked = false;
      state_.new_data_required = false;
      std::snprintf(state_.reason, sizeof(state_.reason),
                    "WARNING: entropy declining (trend=%.4f)",
                    state_.entropy_trend);
      return;
    }

    // All good
    state_.action = FreshnessAction::HEALTHY;
    state_.training_blocked = false;
    state_.new_data_required = false;
    state_.reason[0] = '\0';
  }

  EntropySnapshot history_[ENTROPY_HISTORY];
  uint32_t head_;
  uint32_t count_;
  double entropy_floor_;
  uint32_t stagnation_limit_;
  FreshnessState state_;
};

} // namespace data_freshness
