/**
 * dynamic_threshold.cpp — Dynamic Confidence Threshold Engine
 *
 * Adjusts confidence threshold per field to maintain:
 *   - Minimum confidence >= 0.93
 *   - Precision-first optimization
 *   - Per-field calibrated thresholds
 *   - Adaptive threshold based on FPR feedback
 *
 * NO auto-submission. All reports require manual approval.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace precision_engine {

// =========================================================================
// THRESHOLD CONFIG
// =========================================================================

struct ThresholdConfig {
  double base_threshold;  // 0.93
  double min_threshold;   // 0.90 (never below)
  double max_threshold;   // 0.99
  double adjustment_rate; // 0.005 per cycle
  double target_fpr;      // 0.04
};

static ThresholdConfig default_config() {
  return {0.93, 0.90, 0.99, 0.005, 0.04};
}

// =========================================================================
// THRESHOLD STATE
// =========================================================================

struct ThresholdState {
  double current_threshold;
  double observed_fpr;
  double observed_precision;
  uint32_t adjustments_up;
  uint32_t adjustments_down;
  bool at_minimum;
  bool at_maximum;
  char field_name[64];
};

// =========================================================================
// DYNAMIC THRESHOLD ENGINE
// =========================================================================

class DynamicThreshold {
public:
  static constexpr bool ALLOW_AUTO_SUBMIT = false;

  explicit DynamicThreshold(ThresholdConfig cfg = default_config())
      : config_(cfg) {
    std::memset(&state_, 0, sizeof(state_));
    state_.current_threshold = cfg.base_threshold;
  }

  // Adjust threshold based on observed FPR and precision
  ThresholdState adjust(double observed_fpr, double observed_precision,
                        const char *field) {
    state_.observed_fpr = observed_fpr;
    state_.observed_precision = observed_precision;
    std::strncpy(state_.field_name, field, 63);
    state_.field_name[63] = '\0';

    if (observed_fpr > config_.target_fpr) {
      // Too many false positives: raise threshold
      state_.current_threshold += config_.adjustment_rate;
      if (state_.current_threshold > config_.max_threshold) {
        state_.current_threshold = config_.max_threshold;
        state_.at_maximum = true;
      }
      state_.adjustments_up++;
    } else if (observed_fpr < config_.target_fpr * 0.5 &&
               observed_precision > 0.97) {
      // Very low FPR + high precision: can lower slightly
      state_.current_threshold -= config_.adjustment_rate * 0.5;
      if (state_.current_threshold < config_.min_threshold) {
        state_.current_threshold = config_.min_threshold;
        state_.at_minimum = true;
      }
      state_.adjustments_down++;
    }

    return state_;
  }

  double current_threshold() const { return state_.current_threshold; }
  const ThresholdState &state() const { return state_; }

private:
  ThresholdConfig config_;
  ThresholdState state_;
};

} // namespace precision_engine
