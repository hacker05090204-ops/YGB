// ============================================================
// FIELD PROGRESS CALCULATOR — REAL METRICS ONLY
// ============================================================
// Computes field progress as weighted sum of real metrics.
// NO time-based estimation. NO mock data. NO fake progress.
// ETA computed ONLY from actual training velocity.
// ============================================================

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


// ============================================================
// METRIC WEIGHTS (must sum to 1.0)
// ============================================================
static constexpr double W_PRECISION = 0.30;
static constexpr double W_FPR = 0.25;
static constexpr double W_DUPLICATE = 0.20;
static constexpr double W_ECE = 0.15;
static constexpr double W_STABILITY = 0.10;

static_assert(W_PRECISION + W_FPR + W_DUPLICATE + W_ECE + W_STABILITY > 0.999 &&
                  W_PRECISION + W_FPR + W_DUPLICATE + W_ECE + W_STABILITY <
                      1.001,
              "Weights must sum to 1.0");

// ============================================================
// METRIC INPUT — real values only
// ============================================================
struct FieldMetrics {
  double precision;        // 0.0–1.0 (higher=better)
  double fpr;              // 0.0–1.0 (lower=better)
  double duplicate_det;    // 0.0–1.0 (higher=better)
  double ece;              // 0.0–1.0 (lower=better)
  uint32_t stability_days; // 0–N (higher=better, target=7)

  bool precision_available;
  bool fpr_available;
  bool duplicate_available;
  bool ece_available;
  bool stability_available;
};

// ============================================================
// THRESHOLDS — per field type
// ============================================================
struct FieldThresholds {
  double target_precision;   // e.g. 0.96
  double target_fpr;         // e.g. 0.04
  double target_dup;         // e.g. 0.88
  double target_ece;         // e.g. 0.018
  uint32_t target_stability; // e.g. 7
};

// ============================================================
// VELOCITY — for optional ETA
// ============================================================
struct TrainingVelocity {
  double samples_per_hour;          // 0 = no data
  double precision_delta_per_epoch; // improvement rate
  uint32_t epochs_completed;
  bool has_velocity_data;
};

// ============================================================
// PROGRESS RESULT
// ============================================================
struct ProgressResult {
  double overall_percent; // 0.0–100.0
  double precision_score; // 0.0–1.0
  double fpr_score;       // 0.0–1.0
  double duplicate_score; // 0.0–1.0
  double ece_score;       // 0.0–1.0
  double stability_score; // 0.0–1.0

  uint32_t metrics_available; // count of available metrics
  uint32_t metrics_total;     // always 5

  bool has_eta;
  double eta_hours; // -1 if unavailable

  char summary[256];
};

// ============================================================
// SCORE HELPERS
// ============================================================

// Score for "higher is better" metrics (precision, dup)
static double score_higher(double value, double target) {
  if (target <= 0.0)
    return 0.0;
  double s = value / target;
  if (s > 1.0)
    s = 1.0;
  if (s < 0.0)
    s = 0.0;
  return s;
}

// Score for "lower is better" metrics (FPR, ECE)
static double score_lower(double value, double target) {
  if (target <= 0.0)
    return (value <= 0.0) ? 1.0 : 0.0;
  if (value <= 0.0)
    return 1.0;
  if (value >= target * 2.0)
    return 0.0;
  double s = 1.0 - (value / (target * 2.0));
  if (s > 1.0)
    s = 1.0;
  if (s < 0.0)
    s = 0.0;
  // Bonus: at or below target = full score
  if (value <= target)
    return 1.0;
  return s;
}

// Score for stability days
static double score_stability(uint32_t days, uint32_t target) {
  if (target == 0)
    return 1.0;
  double s = static_cast<double>(days) / static_cast<double>(target);
  if (s > 1.0)
    s = 1.0;
  return s;
}

// ============================================================
// CALCULATE — real progress, no mock data
// ============================================================
static ProgressResult calculate_progress(const FieldMetrics &m,
                                         const FieldThresholds &t,
                                         const TrainingVelocity &v) {
  ProgressResult r;
  std::memset(&r, 0, sizeof(r));
  r.metrics_total = 5;
  r.eta_hours = -1.0;
  r.has_eta = false;

  double weighted_sum = 0.0;
  double weight_sum = 0.0;

  // Precision
  if (m.precision_available) {
    r.precision_score = score_higher(m.precision, t.target_precision);
    weighted_sum += r.precision_score * W_PRECISION;
    weight_sum += W_PRECISION;
    r.metrics_available++;
  }

  // FPR (lower = better)
  if (m.fpr_available) {
    r.fpr_score = score_lower(m.fpr, t.target_fpr);
    weighted_sum += r.fpr_score * W_FPR;
    weight_sum += W_FPR;
    r.metrics_available++;
  }

  // Duplicate detection
  if (m.duplicate_available) {
    r.duplicate_score = score_higher(m.duplicate_det, t.target_dup);
    weighted_sum += r.duplicate_score * W_DUPLICATE;
    weight_sum += W_DUPLICATE;
    r.metrics_available++;
  }

  // ECE (lower = better)
  if (m.ece_available) {
    r.ece_score = score_lower(m.ece, t.target_ece);
    weighted_sum += r.ece_score * W_ECE;
    weight_sum += W_ECE;
    r.metrics_available++;
  }

  // Stability
  if (m.stability_available) {
    r.stability_score = score_stability(m.stability_days, t.target_stability);
    weighted_sum += r.stability_score * W_STABILITY;
    weight_sum += W_STABILITY;
    r.metrics_available++;
  }

  // Compute overall — only from available metrics
  if (weight_sum > 0.0) {
    r.overall_percent = (weighted_sum / weight_sum) * 100.0;
  } else {
    r.overall_percent = 0.0;
  }

  // Clamp
  if (r.overall_percent > 100.0)
    r.overall_percent = 100.0;
  if (r.overall_percent < 0.0)
    r.overall_percent = 0.0;

  // ETA — ONLY from real velocity, never time-based
  if (v.has_velocity_data && v.precision_delta_per_epoch > 0.0) {
    double remaining = t.target_precision - m.precision;
    if (remaining > 0.0 && v.samples_per_hour > 0.0) {
      double epochs_needed = remaining / v.precision_delta_per_epoch;
      // Rough estimate: assume 1 epoch ~= current velocity
      r.eta_hours = epochs_needed; // simplified
      r.has_eta = true;
    }
  }

  // Summary
  if (r.metrics_available == 0) {
    std::snprintf(r.summary, sizeof(r.summary),
                  "AWAITING_DATA: 0/%u metrics available", r.metrics_total);
  } else {
    std::snprintf(
        r.summary, sizeof(r.summary), "PROGRESS: %.1f%% (%u/%u metrics) %s",
        r.overall_percent, r.metrics_available, r.metrics_total,
        r.has_eta ? "[ETA available]" : "[No ETA — awaiting velocity]");
  }

  return r;
}

// ============================================================
// CLIENT-SIDE THRESHOLDS
// ============================================================
static FieldThresholds client_side_thresholds() {
  return {0.96, 0.04, 0.88, 0.018, 7};
}

// ============================================================
// API THRESHOLDS
// ============================================================
static FieldThresholds api_thresholds() { return {0.95, 0.05, 0.85, 0.02, 7}; }

// ============================================================
// EXTENDED LADDER THRESHOLDS (uses API baseline)
// ============================================================
static FieldThresholds extended_thresholds() {
  return api_thresholds(); // Same as API baseline
}
