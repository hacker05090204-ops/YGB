/**
 * drift_monitor.cpp — Post-Certification Drift & Calibration Monitor
 *
 * Rules:
 *   - ECE > threshold → calibration_required flag
 *   - KL divergence > dynamic tolerance → freeze invalidation
 *   - KL > 2x baseline → immediate emergency containment
 *   - Rolling window of 500 samples for stability
 *   - Baseline computed from first 100 samples
 *   - No mock data — real inference metrics only
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace runtime_cert_monitor {

static constexpr uint32_t DRIFT_WINDOW = 500;
static constexpr uint32_t BASELINE_SAMPLES = 100;
static constexpr double DEFAULT_ECE_THRESHOLD = 0.02;
static constexpr double DEFAULT_KL_THRESHOLD = 0.35;
static constexpr double KL_CRITICAL = 0.50;
static constexpr double KL_SPIKE_MULTIPLIER = 2.0; // 2x baseline → emergency

enum class DriftAction : uint8_t {
  NONE = 0,
  CALIBRATION_REQUIRED = 1,
  FREEZE_INVALIDATION = 2,
  EMERGENCY_CONTAINMENT = 3
};

struct DriftSample {
  double predicted_confidence;
  bool actually_positive;
  double feature_kl; // KL divergence of this sample's features
  uint32_t field_id;
  uint64_t timestamp_ms;
};

struct DriftState {
  // ECE tracking
  double ece;
  double ece_threshold;
  bool calibration_required;

  // KL tracking
  double kl_mean;
  double kl_max;
  double kl_threshold;
  bool freeze_invalid;

  // Baseline tracking
  double kl_baseline;
  bool baseline_set;
  uint32_t baseline_count;

  // Spike detection
  bool kl_spike_detected;

  // Counts
  uint32_t window_fill;
  DriftAction action;
  char alert_log[512];
};

class PostCertDriftMonitor {
public:
  PostCertDriftMonitor()
      : head_(0), count_(0), ece_threshold_(DEFAULT_ECE_THRESHOLD),
        kl_threshold_(DEFAULT_KL_THRESHOLD) {
    std::memset(&state_, 0, sizeof(state_));
    std::memset(window_, 0, sizeof(window_));
    state_.ece_threshold = ece_threshold_;
    state_.kl_threshold = kl_threshold_;
    state_.baseline_set = false;
    state_.baseline_count = 0;
    state_.kl_baseline = 0.0;
    baseline_kl_sum_ = 0.0;
  }

  void set_thresholds(double ece_t, double kl_t) {
    ece_threshold_ = ece_t;
    kl_threshold_ = kl_t;
    state_.ece_threshold = ece_t;
    state_.kl_threshold = kl_t;
  }

  void record(const DriftSample &sample) {
    if (count_ == DRIFT_WINDOW) {
      // Shift oldest out (circular)
      // oldest slot will be overwritten
    }

    window_[head_] = sample;
    head_ = (head_ + 1) % DRIFT_WINDOW;
    if (count_ < DRIFT_WINDOW)
      count_++;

    // Build baseline from first BASELINE_SAMPLES
    if (!state_.baseline_set) {
      baseline_kl_sum_ += sample.feature_kl;
      state_.baseline_count++;
      if (state_.baseline_count >= BASELINE_SAMPLES) {
        state_.kl_baseline = baseline_kl_sum_ / state_.baseline_count;
        state_.baseline_set = true;
      }
    }

    recompute();
    check_alerts();
  }

  const DriftState &state() const { return state_; }

  void reset() {
    head_ = 0;
    count_ = 0;
    std::memset(&state_, 0, sizeof(state_));
    std::memset(window_, 0, sizeof(window_));
    state_.ece_threshold = ece_threshold_;
    state_.kl_threshold = kl_threshold_;
    state_.baseline_set = false;
    state_.baseline_count = 0;
    state_.kl_baseline = 0.0;
    baseline_kl_sum_ = 0.0;
  }

  // ---- Self-test ----
  static bool run_tests() {
    PostCertDriftMonitor mon;
    int failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (!cond) {
        std::printf("  FAIL: %s\n", name);
        failed++;
      }
    };

    // Test 1: Well-calibrated data → no alerts
    for (uint32_t i = 0; i < 100; i++) {
      DriftSample s;
      s.predicted_confidence = 0.80;
      s.actually_positive = (i % 5 != 0) ? true : false; // ~80% positive
      s.feature_kl = 0.05;
      s.field_id = 0;
      s.timestamp_ms = i;
      mon.record(s);
    }
    test(mon.state().calibration_required == false,
         "no cal required with good ECE");
    test(mon.state().freeze_invalid == false, "no freeze invalid with low KL");
    test(mon.state().baseline_set == true,
         "baseline should be set after 100 samples");
    test(std::fabs(mon.state().kl_baseline - 0.05) < 0.001,
         "baseline should be ~0.05");

    // Test 2: High KL → freeze invalidation
    mon.reset();
    for (uint32_t i = 0; i < 100; i++) {
      DriftSample s;
      s.predicted_confidence = 0.90;
      s.actually_positive = true;
      s.feature_kl = 0.60; // Very high
      s.field_id = 0;
      s.timestamp_ms = i;
      mon.record(s);
    }
    test(mon.state().freeze_invalid == true,
         "freeze should be invalid with high KL");
    test(mon.state().action == DriftAction::FREEZE_INVALIDATION ||
             mon.state().action == DriftAction::EMERGENCY_CONTAINMENT,
         "action should be FREEZE_INVALIDATION or higher");

    // Test 3: KL spike > 2x baseline → emergency containment
    mon.reset();
    // Build baseline with low KL
    for (uint32_t i = 0; i < 100; i++) {
      DriftSample s;
      s.predicted_confidence = 0.85;
      s.actually_positive = true;
      s.feature_kl = 0.10; // baseline will be ~0.10
      s.field_id = 0;
      s.timestamp_ms = i;
      mon.record(s);
    }
    test(mon.state().baseline_set == true, "baseline set after 100 samples");
    test(std::fabs(mon.state().kl_baseline - 0.10) < 0.01,
         "baseline should be ~0.10");
    // Now inject 2x+ spike
    for (uint32_t i = 0; i < 100; i++) {
      DriftSample s;
      s.predicted_confidence = 0.85;
      s.actually_positive = true;
      s.feature_kl = 0.50; // 5x baseline
      s.field_id = 0;
      s.timestamp_ms = 100 + i;
      mon.record(s);
    }
    test(mon.state().kl_spike_detected == true,
         "KL spike should be detected (5x baseline)");
    test(mon.state().action == DriftAction::EMERGENCY_CONTAINMENT,
         "action should be EMERGENCY_CONTAINMENT on spike");

    // Test 4: Baseline not set before 100 samples
    mon.reset();
    for (uint32_t i = 0; i < 50; i++) {
      DriftSample s;
      s.predicted_confidence = 0.85;
      s.actually_positive = true;
      s.feature_kl = 0.10;
      s.field_id = 0;
      s.timestamp_ms = i;
      mon.record(s);
    }
    test(mon.state().baseline_set == false,
         "baseline should NOT be set at 50 samples");
    test(mon.state().kl_spike_detected == false,
         "no spike detection without baseline");

    return failed == 0;
  }

private:
  void recompute() {
    if (count_ == 0)
      return;

    // ECE: Expected Calibration Error
    static constexpr uint32_t NUM_BINS = 10;
    uint32_t bin_count[NUM_BINS] = {};
    double bin_conf_sum[NUM_BINS] = {};
    double bin_acc_sum[NUM_BINS] = {};

    double kl_sum = 0.0;
    double kl_max = 0.0;

    for (uint32_t i = 0; i < count_; i++) {
      uint32_t idx = (head_ + DRIFT_WINDOW - count_ + i) % DRIFT_WINDOW;
      const auto &s = window_[idx];

      // ECE binning
      uint32_t bin = static_cast<uint32_t>(s.predicted_confidence * NUM_BINS);
      if (bin >= NUM_BINS)
        bin = NUM_BINS - 1;
      bin_count[bin]++;
      bin_conf_sum[bin] += s.predicted_confidence;
      bin_acc_sum[bin] += s.actually_positive ? 1.0 : 0.0;

      // KL
      kl_sum += s.feature_kl;
      if (s.feature_kl > kl_max)
        kl_max = s.feature_kl;
    }

    // Compute ECE
    double ece = 0.0;
    for (uint32_t b = 0; b < NUM_BINS; b++) {
      if (bin_count[b] > 0) {
        double avg_conf = bin_conf_sum[b] / bin_count[b];
        double avg_acc = bin_acc_sum[b] / bin_count[b];
        ece += (static_cast<double>(bin_count[b]) / count_) *
               std::fabs(avg_conf - avg_acc);
      }
    }

    state_.ece = ece;
    state_.kl_mean = kl_sum / count_;
    state_.kl_max = kl_max;
    state_.window_fill = count_;
  }

  void check_alerts() {
    if (count_ < 50) {
      state_.action = DriftAction::NONE;
      state_.calibration_required = false;
      state_.freeze_invalid = false;
      state_.kl_spike_detected = false;
      return;
    }

    // ---- KL spike > 2x baseline → immediate emergency ----
    if (state_.baseline_set && state_.kl_baseline > 0.0) {
      double spike_threshold = state_.kl_baseline * KL_SPIKE_MULTIPLIER;
      if (state_.kl_mean > spike_threshold) {
        state_.kl_spike_detected = true;
        state_.action = DriftAction::EMERGENCY_CONTAINMENT;
        state_.freeze_invalid = true;
        state_.calibration_required = true;
        std::snprintf(state_.alert_log, sizeof(state_.alert_log),
                      "SPIKE: KL=%.4f > 2x baseline=%.4f (threshold=%.4f)",
                      state_.kl_mean, state_.kl_baseline, spike_threshold);
        return;
      } else {
        state_.kl_spike_detected = false;
      }
    }

    // ---- KL critical → emergency ----
    if (state_.kl_mean >= KL_CRITICAL) {
      state_.action = DriftAction::EMERGENCY_CONTAINMENT;
      state_.freeze_invalid = true;
      state_.calibration_required = true;
      std::snprintf(state_.alert_log, sizeof(state_.alert_log),
                    "EMERGENCY: KL=%.4f >= %.4f, ECE=%.4f", state_.kl_mean,
                    KL_CRITICAL, state_.ece);
      return;
    }

    // ---- KL > threshold → freeze invalidation ----
    if (state_.kl_mean > kl_threshold_) {
      state_.action = DriftAction::FREEZE_INVALIDATION;
      state_.freeze_invalid = true;
      std::snprintf(state_.alert_log, sizeof(state_.alert_log),
                    "FREEZE_INVALID: KL=%.4f > threshold=%.4f", state_.kl_mean,
                    kl_threshold_);
    } else {
      state_.freeze_invalid = false;
    }

    // ---- ECE > threshold → calibration required ----
    if (state_.ece > ece_threshold_) {
      state_.calibration_required = true;
      if (state_.action < DriftAction::CALIBRATION_REQUIRED) {
        state_.action = DriftAction::CALIBRATION_REQUIRED;
      }
      std::snprintf(state_.alert_log, sizeof(state_.alert_log),
                    "CALIBRATION_REQUIRED: ECE=%.4f > threshold=%.4f",
                    state_.ece, ece_threshold_);
    } else {
      state_.calibration_required = false;
    }

    if (!state_.freeze_invalid && !state_.calibration_required) {
      state_.action = DriftAction::NONE;
      state_.alert_log[0] = '\0';
    }
  }

  DriftSample window_[DRIFT_WINDOW];
  uint32_t head_;
  uint32_t count_;
  double ece_threshold_;
  double kl_threshold_;
  double baseline_kl_sum_;
  DriftState state_;
};

} // namespace runtime_cert_monitor
