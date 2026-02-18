/**
 * amp_controller.cpp — Automatic Mixed Precision Controller
 *
 * FP16/FP32 mixed precision with dynamic loss scaling.
 * Thermal throttle at 83°C. Overflow detection and recovery.
 *
 * NO cross-field contamination. NO authority unlock.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace performance {

// =========================================================================
// AMP CONFIG
// =========================================================================

struct AmpConfig {
  double initial_loss_scale;          // default: 65536.0
  double scale_growth_factor;         // default: 2.0
  double scale_backoff_factor;        // default: 0.5
  uint32_t growth_interval;           // steps between scale increases
  uint32_t max_consecutive_overflows; // before fallback to FP32
  double thermal_throttle_c;          // default: 83.0
};

static AmpConfig default_amp() {
  AmpConfig c;
  c.initial_loss_scale = 65536.0;
  c.scale_growth_factor = 2.0;
  c.scale_backoff_factor = 0.5;
  c.growth_interval = 2000;
  c.max_consecutive_overflows = 5;
  c.thermal_throttle_c = 83.0;
  return c;
}

// =========================================================================
// AMP STATE
// =========================================================================

struct AmpState {
  double current_loss_scale;
  bool enabled; // true = FP16 active
  uint32_t steps_since_growth;
  uint32_t consecutive_overflows;
  uint32_t total_overflows;
  uint32_t total_scale_ups;
  uint32_t total_scale_downs;
  bool fallback_fp32; // forced FP32 mode
  double gpu_temp_c;
  bool thermal_throttled;
};

// =========================================================================
// AMP CONTROLLER
// =========================================================================

class AmpController {
public:
  explicit AmpController(AmpConfig config = default_amp()) : config_(config) {
    std::memset(&state_, 0, sizeof(state_));
    state_.current_loss_scale = config_.initial_loss_scale;
    state_.enabled = true;
  }

  // Check for overflow and adjust loss scale
  AmpState step(bool overflow_detected, double gpu_temp_c) {
    state_.gpu_temp_c = gpu_temp_c;

    // Thermal check
    if (gpu_temp_c >= config_.thermal_throttle_c) {
      state_.thermal_throttled = true;
      // Don't change AMP state, just flag
    } else {
      state_.thermal_throttled = false;
    }

    if (overflow_detected) {
      state_.consecutive_overflows++;
      state_.total_overflows++;

      // Backoff loss scale
      state_.current_loss_scale *= config_.scale_backoff_factor;
      if (state_.current_loss_scale < 1.0)
        state_.current_loss_scale = 1.0;
      state_.total_scale_downs++;
      state_.steps_since_growth = 0;

      // Too many overflows → fallback to FP32
      if (state_.consecutive_overflows >= config_.max_consecutive_overflows) {
        state_.fallback_fp32 = true;
        state_.enabled = false;
      }
    } else {
      state_.consecutive_overflows = 0;
      state_.steps_since_growth++;

      // Grow loss scale periodically
      if (state_.steps_since_growth >= config_.growth_interval) {
        state_.current_loss_scale *= config_.scale_growth_factor;
        if (state_.current_loss_scale > 65536.0)
          state_.current_loss_scale = 65536.0;
        state_.total_scale_ups++;
        state_.steps_since_growth = 0;
      }
    }

    return state_;
  }

  // Re-enable AMP after manual intervention
  void reenable() {
    state_.enabled = true;
    state_.fallback_fp32 = false;
    state_.consecutive_overflows = 0;
    state_.current_loss_scale = config_.initial_loss_scale;
  }

  const AmpConfig &config() const { return config_; }
  const AmpState &state() const { return state_; }

private:
  AmpConfig config_;
  AmpState state_;
};

} // namespace performance
