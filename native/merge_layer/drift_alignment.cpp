/**
 * drift_alignment.cpp — Drift Alignment for Merge
 *
 * KL divergence within tolerance and distribution compatibility
 * check before allowing weight merge.
 *
 * If drift exceeds KL threshold: reject merge.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace merge_layer {

// =========================================================================
// DRIFT METRICS
// =========================================================================

struct DriftMetrics {
  double kl_divergence;
  double js_divergence; // Jensen-Shannon
  double mean_shift;
  double variance_ratio;
  uint32_t samples;
};

// =========================================================================
// DRIFT ALIGNMENT RESULT
// =========================================================================

struct DriftAlignmentResult {
  double kl_diff;
  double js_diff;
  double mean_shift;
  bool compatible;
  char reason[256];
};

// =========================================================================
// DRIFT ALIGNMENT ENGINE
// =========================================================================

class DriftAlignment {
public:
  static constexpr double MAX_KL_DIVERGENCE = 0.35;
  static constexpr double MAX_JS_DIVERGENCE = 0.20;
  static constexpr double MAX_MEAN_SHIFT = 0.10;

  DriftAlignmentResult check(const DriftMetrics &baseline,
                             const DriftMetrics &candidate) {
    DriftAlignmentResult r;
    std::memset(&r, 0, sizeof(r));

    r.kl_diff = candidate.kl_divergence;
    r.js_diff = candidate.js_divergence;
    r.mean_shift = std::fabs(candidate.mean_shift - baseline.mean_shift);

    bool kl_ok = (r.kl_diff <= MAX_KL_DIVERGENCE);
    bool js_ok = (r.js_diff <= MAX_JS_DIVERGENCE);
    bool shift_ok = (r.mean_shift <= MAX_MEAN_SHIFT);

    r.compatible = kl_ok && js_ok && shift_ok;

    if (r.compatible) {
      std::snprintf(r.reason, sizeof(r.reason),
                    "DRIFT_COMPATIBLE: KL=%.4f JS=%.4f shift=%.4f", r.kl_diff,
                    r.js_diff, r.mean_shift);
    } else {
      std::snprintf(r.reason, sizeof(r.reason),
                    "DRIFT_INCOMPATIBLE: KL=%.4f%s JS=%.4f%s shift=%.4f%s",
                    r.kl_diff, kl_ok ? "" : "!", r.js_diff, js_ok ? "" : "!",
                    r.mean_shift, shift_ok ? "" : "!");
    }

    return r;
  }
};

} // namespace merge_layer
