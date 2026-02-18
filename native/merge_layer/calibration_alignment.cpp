/**
 * calibration_alignment.cpp — Calibration Alignment for Merge
 *
 * Validates ECE difference <= 0.005 and temperature consistency
 * between merge candidates before allowing weight merge.
 *
 * If misaligned: reject merge, rollback to certified snapshot.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace merge_layer {

// =========================================================================
// CALIBRATION METRICS
// =========================================================================

struct CalibrationMetrics {
  double ece;         // Expected Calibration Error
  double temperature; // Temperature scaling parameter
  double brier_score;
  double max_bin_gap; // max |confidence - accuracy| in any bin
  uint32_t num_bins;
};

// =========================================================================
// CALIBRATION ALIGNMENT RESULT
// =========================================================================

struct CalibrationAlignmentResult {
  double ece_diff;
  double temp_diff;
  double brier_diff;
  bool aligned;
  char reason[256];
};

// =========================================================================
// CALIBRATION ALIGNMENT ENGINE
// =========================================================================

class CalibrationAlignment {
public:
  static constexpr double MAX_ECE_DIFF = 0.005;
  static constexpr double MAX_TEMP_DIFF = 0.2;
  static constexpr double MAX_BRIER_DIFF = 0.03;

  CalibrationAlignmentResult check(const CalibrationMetrics &a,
                                   const CalibrationMetrics &b) {
    CalibrationAlignmentResult r;
    std::memset(&r, 0, sizeof(r));

    r.ece_diff = std::fabs(a.ece - b.ece);
    r.temp_diff = std::fabs(a.temperature - b.temperature);
    r.brier_diff = std::fabs(a.brier_score - b.brier_score);

    bool ece_ok = (r.ece_diff <= MAX_ECE_DIFF);
    bool temp_ok = (r.temp_diff <= MAX_TEMP_DIFF);
    bool brier_ok = (r.brier_diff <= MAX_BRIER_DIFF);

    r.aligned = ece_ok && temp_ok && brier_ok;

    if (r.aligned) {
      std::snprintf(r.reason, sizeof(r.reason),
                    "CALIBRATED: ECE_diff=%.4f temp_diff=%.3f brier_diff=%.4f",
                    r.ece_diff, r.temp_diff, r.brier_diff);
    } else {
      std::snprintf(
          r.reason, sizeof(r.reason),
          "MISCALIBRATED: ECE_diff=%.4f%s temp_diff=%.3f%s brier=%.4f%s",
          r.ece_diff, ece_ok ? "" : "!", r.temp_diff, temp_ok ? "" : "!",
          r.brier_diff, brier_ok ? "" : "!");
    }

    return r;
  }
};

} // namespace merge_layer
