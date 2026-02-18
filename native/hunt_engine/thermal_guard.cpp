/**
 * thermal_guard.cpp — Hunt Engine Thermal Protection
 *
 * Auto-pauses hunt execution when GPU temperature exceeds 83°C.
 * Resumes when temperature drops below safe threshold.
 *
 * No training in hunt engine. No auto-submit.
 */

#include <cstdint>
#include <cstdio>
#include <cstring>


namespace hunt_engine {

// =========================================================================
// THERMAL CONFIG
// =========================================================================

struct ThermalConfig {
  double pause_threshold_c;   // default: 83.0
  double resume_threshold_c;  // default: 75.0 (hysteresis)
  double warning_threshold_c; // default: 78.0
  uint32_t poll_interval_ms;  // default: 5000
};

static ThermalConfig default_thermal_config() {
  return {83.0, 75.0, 78.0, 5000};
}

// =========================================================================
// THERMAL STATE
// =========================================================================

enum class ThermalState : uint8_t { NORMAL = 0, WARNING = 1, PAUSED = 2 };

static const char *thermal_state_name(ThermalState s) {
  switch (s) {
  case ThermalState::NORMAL:
    return "NORMAL";
  case ThermalState::WARNING:
    return "WARNING";
  case ThermalState::PAUSED:
    return "PAUSED";
  default:
    return "UNKNOWN";
  }
}

// =========================================================================
// THERMAL VERDICT
// =========================================================================

struct ThermalVerdict {
  ThermalState state;
  double current_temp_c;
  bool should_pause;
  bool should_resume;
  char reason[256];
};

// =========================================================================
// THERMAL GUARD
// =========================================================================

class ThermalGuard {
public:
  explicit ThermalGuard(ThermalConfig config = default_thermal_config())
      : config_(config), state_(ThermalState::NORMAL), peak_temp_(0.0),
        pause_count_(0) {}

  ThermalVerdict evaluate(double gpu_temp_c) {
    ThermalVerdict v;
    std::memset(&v, 0, sizeof(v));
    v.current_temp_c = gpu_temp_c;

    if (gpu_temp_c > peak_temp_)
      peak_temp_ = gpu_temp_c;

    if (gpu_temp_c >= config_.pause_threshold_c) {
      // PAUSE — too hot
      state_ = ThermalState::PAUSED;
      v.should_pause = true;
      v.should_resume = false;
      ++pause_count_;
      std::snprintf(v.reason, sizeof(v.reason),
                    "THERMAL_PAUSE: %.1fC >= %.1fC threshold", gpu_temp_c,
                    config_.pause_threshold_c);
    } else if (state_ == ThermalState::PAUSED &&
               gpu_temp_c <= config_.resume_threshold_c) {
      // RESUME — cooled down below hysteresis
      state_ = ThermalState::NORMAL;
      v.should_pause = false;
      v.should_resume = true;
      std::snprintf(v.reason, sizeof(v.reason),
                    "THERMAL_RESUME: %.1fC <= %.1fC resume threshold",
                    gpu_temp_c, config_.resume_threshold_c);
    } else if (gpu_temp_c >= config_.warning_threshold_c) {
      if (state_ != ThermalState::PAUSED)
        state_ = ThermalState::WARNING;
      v.should_pause = false;
      v.should_resume = false;
      std::snprintf(v.reason, sizeof(v.reason),
                    "THERMAL_WARNING: %.1fC >= %.1fC warning", gpu_temp_c,
                    config_.warning_threshold_c);
    } else {
      if (state_ != ThermalState::PAUSED)
        state_ = ThermalState::NORMAL;
      v.should_pause = false;
      v.should_resume = false;
      std::snprintf(v.reason, sizeof(v.reason), "THERMAL_OK: %.1fC",
                    gpu_temp_c);
    }

    v.state = state_;
    return v;
  }

  ThermalState state() const { return state_; }
  double peak_temp() const { return peak_temp_; }
  uint32_t pause_count() const { return pause_count_; }
  const ThermalConfig &config() const { return config_; }

private:
  ThermalConfig config_;
  ThermalState state_;
  double peak_temp_;
  uint32_t pause_count_;
};

} // namespace hunt_engine
