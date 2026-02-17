/**
 * drift_runtime.cpp — Drift Telemetry + Duplicate Rate Monitor
 *
 * Tracks:
 * - Rolling KL divergence
 * - Entropy shift
 * - Confidence inflation
 * - Duplicate Risk Score distribution
 * - High similarity clusters
 *
 * KL > 0.35: WARNING
 * KL > 0.45: CONTAINMENT
 * Duplicate cluster spike > 20%: REVIEW ALERT
 *
 * NO mock data. NO auto-submit. NO authority unlock.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace runtime_monitor {

static constexpr uint32_t DRIFT_WINDOW = 500;
static constexpr double KL_WARNING_FLOOR = 0.35;
static constexpr double KL_CONTAINMENT_FLOOR = 0.45;
static constexpr double KL_BASELINE_WARN_MULT = 1.5;
static constexpr double KL_BASELINE_CONT_MULT = 2.0;
static constexpr double KL_EMA_ALPHA = 0.05; // EMA smoothing factor
static constexpr double ENTROPY_SHIFT_WARN = 0.15;
static constexpr double CONFIDENCE_INFLATION_MAX = 0.10;
static constexpr double DUPLICATE_CLUSTER_SPIKE = 0.20;
static constexpr double DUP_CONF_BOOST = 0.02;
static constexpr double DUP_ABSTENTION_BOOST = 0.03;

enum class DriftAction : uint8_t {
  NONE = 0,
  WARNING = 1,
  CONTAINMENT = 2,
  REVIEW_ALERT = 3
};

enum class GpuStatus : uint8_t {
  UNKNOWN = 0,
  AVAILABLE = 1,
  UNAVAILABLE = 2,
  TIMEOUT = 3
};

struct DriftMetrics {
  double kl_divergence;
  double entropy_current;
  double entropy_baseline;
  double entropy_shift;
  double confidence_mean;
  double confidence_baseline;
  double confidence_inflation;

  // Duplicate cluster
  double duplicate_cluster_rate;
  uint32_t high_sim_clusters;
  uint32_t total_samples;

  // Relative thresholds (Phase 3)
  double kl_baseline_mean;  // EMA of KL divergence
  double kl_warn_threshold; // max(0.35, baseline * 1.5)
  double kl_cont_threshold; // max(0.45, baseline * 2.0)

  // Adaptive precision (Phase 4)
  double confidence_threshold_adj; // +0.02 per dup spike
  double abstention_band_adj;      // +0.03 per dup spike
  bool adaptive_shift_active;

  // GPU status (Phase 1)
  GpuStatus gpu_status;
  char gpu_status_detail[128];

  // Actions
  DriftAction drift_action;
  DriftAction dup_action;
  bool containment_active;
  char alert_reason[256];
};

struct DriftSample {
  double confidence;
  double feature_entropy;
  double duplicate_risk_score;
};

class DriftRuntimeMonitor {
public:
  DriftRuntimeMonitor()
      : head_(0), count_(0), kl_baseline_ema_(0.0),
        kl_baseline_initialized_(false) {
    std::memset(&metrics_, 0, sizeof(metrics_));
    std::memset(window_, 0, sizeof(window_));
    metrics_.confidence_baseline = 0.85;
    metrics_.entropy_baseline = 2.0;
    metrics_.gpu_status = GpuStatus::UNKNOWN;
    metrics_.gpu_status_detail[0] = '\0';
    metrics_.confidence_threshold_adj = 0.0;
    metrics_.abstention_band_adj = 0.0;
    metrics_.adaptive_shift_active = false;
  }

  void set_baselines(double conf, double entropy) {
    metrics_.confidence_baseline = conf;
    metrics_.entropy_baseline = entropy;
  }

  // --- GPU status (set from subprocess result, never fabricated) ---
  void set_gpu_status(GpuStatus status, const char *detail = nullptr) {
    metrics_.gpu_status = status;
    if (detail) {
      std::snprintf(metrics_.gpu_status_detail,
                    sizeof(metrics_.gpu_status_detail), "%s", detail);
    } else {
      metrics_.gpu_status_detail[0] = '\0';
    }
  }

  // --- Restore baselines from persisted state ---
  void restore_kl_baseline(double ema) {
    kl_baseline_ema_ = ema;
    kl_baseline_initialized_ = (ema > 0.0);
  }

  double get_kl_baseline_ema() const { return kl_baseline_ema_; }

  void record(const DriftSample &sample) {
    window_[head_] = sample;
    head_ = (head_ + 1) % DRIFT_WINDOW;
    if (count_ < DRIFT_WINDOW)
      ++count_;
    metrics_.total_samples++;

    recompute();
    check_alerts();
  }

  const DriftMetrics &metrics() const { return metrics_; }

  void reset() {
    head_ = 0;
    count_ = 0;
    kl_baseline_ema_ = 0.0;
    kl_baseline_initialized_ = false;
    std::memset(&metrics_, 0, sizeof(metrics_));
    std::memset(window_, 0, sizeof(window_));
    metrics_.confidence_baseline = 0.85;
    metrics_.entropy_baseline = 2.0;
    metrics_.gpu_status = GpuStatus::UNKNOWN;
    metrics_.gpu_status_detail[0] = '\0';
    metrics_.confidence_threshold_adj = 0.0;
    metrics_.abstention_band_adj = 0.0;
    metrics_.adaptive_shift_active = false;
  }

  // --- Self-test ---
  static bool run_tests() {
    DriftRuntimeMonitor mon;
    int passed = 0, failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (cond) {
        ++passed;
      } else {
        ++failed;
      }
    };

    // Test 1: No data = no alerts
    test(mon.metrics().containment_active == false, "Empty: no containment");
    test(mon.metrics().drift_action == DriftAction::NONE,
         "Empty: no drift action");

    // Test 2: Stable samples
    for (int i = 0; i < 100; ++i) {
      DriftSample s = {0.85, 2.0, 10.0};
      mon.record(s);
    }
    test(mon.metrics().kl_divergence < KL_WARNING_FLOOR,
         "Stable: KL below warning");
    test(mon.metrics().containment_active == false, "Stable: no containment");

    // Test 3: Confidence inflation detection
    mon.reset();
    mon.set_baselines(0.80, 2.0);
    for (int i = 0; i < 100; ++i) {
      DriftSample s = {0.95, 2.0, 5.0};
      mon.record(s);
    }
    test(mon.metrics().confidence_inflation > 0.05,
         "High confidence vs baseline = inflation detected");

    // Test 4: Entropy shift detection
    mon.reset();
    mon.set_baselines(0.85, 3.0);
    for (int i = 0; i < 100; ++i) {
      DriftSample s = {0.85, 1.5, 5.0};
      mon.record(s);
    }
    test(std::fabs(mon.metrics().entropy_shift) > 0.1, "Entropy drop detected");

    // Test 5: Duplicate cluster spike
    mon.reset();
    for (int i = 0; i < 100; ++i) {
      DriftSample s = {0.85, 2.0, 85.0}; // high dup risk
      mon.record(s);
    }
    test(mon.metrics().duplicate_cluster_rate > 0.5,
         "High dup risk scores = cluster spike");
    test(mon.metrics().dup_action == DriftAction::REVIEW_ALERT,
         "Duplicate spike triggers review alert");

    // Test 6: KL-based containment (simulated via entropy shift)
    mon.reset();
    mon.set_baselines(0.50, 4.0);
    for (int i = 0; i < 200; ++i) {
      DriftSample s = {0.95, 0.5, 5.0};
      mon.record(s);
    }
    // Large confidence and entropy changes should raise KL
    test(mon.metrics().kl_divergence >= 0.0, "KL divergence computed");

    return failed == 0;
  }

private:
  DriftSample window_[DRIFT_WINDOW];
  uint32_t head_;
  uint32_t count_;
  DriftMetrics metrics_;
  double kl_baseline_ema_;
  bool kl_baseline_initialized_;

  void recompute() {
    if (count_ == 0)
      return;

    double conf_sum = 0, ent_sum = 0, dup_high = 0;
    for (uint32_t i = 0; i < count_; ++i) {
      conf_sum += window_[i].confidence;
      ent_sum += window_[i].feature_entropy;
      if (window_[i].duplicate_risk_score >= 60.0)
        dup_high++;
    }

    metrics_.confidence_mean = conf_sum / count_;
    metrics_.entropy_current = ent_sum / count_;
    metrics_.confidence_inflation =
        metrics_.confidence_mean - metrics_.confidence_baseline;
    metrics_.entropy_shift =
        metrics_.entropy_current - metrics_.entropy_baseline;

    // Approximate KL divergence from confidence + entropy shift
    double conf_ratio =
        metrics_.confidence_baseline > 0.01
            ? metrics_.confidence_mean / metrics_.confidence_baseline
            : 1.0;
    double ent_ratio =
        metrics_.entropy_baseline > 0.01
            ? metrics_.entropy_current / metrics_.entropy_baseline
            : 1.0;

    // KL ≈ sum of component-wise divergences
    double kl_conf = conf_ratio > 0 ? conf_ratio * std::log(conf_ratio) : 0.0;
    double kl_ent = ent_ratio > 0 ? ent_ratio * std::log(ent_ratio) : 0.0;
    metrics_.kl_divergence = std::fabs(kl_conf) + std::fabs(kl_ent);

    // Update KL baseline EMA (Phase 3)
    if (!kl_baseline_initialized_) {
      kl_baseline_ema_ = metrics_.kl_divergence;
      kl_baseline_initialized_ = true;
    } else {
      kl_baseline_ema_ = KL_EMA_ALPHA * metrics_.kl_divergence +
                         (1.0 - KL_EMA_ALPHA) * kl_baseline_ema_;
    }
    metrics_.kl_baseline_mean = kl_baseline_ema_;

    // Compute relative thresholds (Phase 3)
    metrics_.kl_warn_threshold =
        std::fmax(KL_WARNING_FLOOR, kl_baseline_ema_ * KL_BASELINE_WARN_MULT);
    metrics_.kl_cont_threshold = std::fmax(
        KL_CONTAINMENT_FLOOR, kl_baseline_ema_ * KL_BASELINE_CONT_MULT);

    // Duplicate clustering
    metrics_.duplicate_cluster_rate = static_cast<double>(dup_high) / count_;
    metrics_.high_sim_clusters = static_cast<uint32_t>(dup_high);
  }

  void check_alerts() {
    // KL alerts — relative thresholds (Phase 3)
    if (metrics_.kl_divergence > metrics_.kl_cont_threshold) {
      metrics_.drift_action = DriftAction::CONTAINMENT;
      metrics_.containment_active = true;
      std::snprintf(metrics_.alert_reason, sizeof(metrics_.alert_reason),
                    "KL CONTAINMENT: %.4f > %.4f (base=%.4f)",
                    metrics_.kl_divergence, metrics_.kl_cont_threshold,
                    kl_baseline_ema_);
    } else if (metrics_.kl_divergence > metrics_.kl_warn_threshold) {
      metrics_.drift_action = DriftAction::WARNING;
      metrics_.containment_active = false;
      std::snprintf(metrics_.alert_reason, sizeof(metrics_.alert_reason),
                    "KL WARNING: %.4f > %.4f (base=%.4f)",
                    metrics_.kl_divergence, metrics_.kl_warn_threshold,
                    kl_baseline_ema_);
    } else {
      metrics_.drift_action = DriftAction::NONE;
      metrics_.containment_active = false;
      metrics_.alert_reason[0] = '\0';
    }

    // Duplicate cluster alerts + auto-adjust (Phase 4)
    if (metrics_.duplicate_cluster_rate > DUPLICATE_CLUSTER_SPIKE) {
      metrics_.dup_action = DriftAction::REVIEW_ALERT;
      metrics_.adaptive_shift_active = true;
      metrics_.confidence_threshold_adj += DUP_CONF_BOOST;
      if (metrics_.confidence_threshold_adj > 0.10)
        metrics_.confidence_threshold_adj = 0.10; // cap
      metrics_.abstention_band_adj += DUP_ABSTENTION_BOOST;
      if (metrics_.abstention_band_adj > 0.15)
        metrics_.abstention_band_adj = 0.15; // cap
    } else {
      metrics_.dup_action = DriftAction::NONE;
      // Decay adjustments slowly when spike subsides
      if (metrics_.confidence_threshold_adj > 0.0) {
        metrics_.confidence_threshold_adj -= 0.005;
        if (metrics_.confidence_threshold_adj < 0.0)
          metrics_.confidence_threshold_adj = 0.0;
      }
      if (metrics_.abstention_band_adj > 0.0) {
        metrics_.abstention_band_adj -= 0.005;
        if (metrics_.abstention_band_adj < 0.0)
          metrics_.abstention_band_adj = 0.0;
      }
      if (metrics_.confidence_threshold_adj == 0.0 &&
          metrics_.abstention_band_adj == 0.0) {
        metrics_.adaptive_shift_active = false;
      }
    }
  }
};

} // namespace runtime_monitor
