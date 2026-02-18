/**
 * entropy_preservation.cpp — Entropy Preservation Guard
 *
 * Ensures no entropy collapse during merge:
 *   - Information retention >= 98%
 *   - No mode collapse (min entropy per class)
 *   - Representation diversity maintained
 *
 * If entropy collapses: reject merge, rollback.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace merge_layer {

// =========================================================================
// ENTROPY METRICS
// =========================================================================

struct EntropyMetrics {
  double total_entropy;
  double min_class_entropy;
  double max_class_entropy;
  double entropy_variance;
  uint32_t num_classes;
  uint32_t collapsed_classes; // classes with near-zero entropy
};

// =========================================================================
// ENTROPY PRESERVATION RESULT
// =========================================================================

struct EntropyPreservationResult {
  double retention_ratio; // candidate / baseline
  bool no_collapse;
  bool diversity_maintained;
  bool preserved;
  char reason[256];
};

// =========================================================================
// ENTROPY PRESERVATION ENGINE
// =========================================================================

class EntropyPreservation {
public:
  static constexpr double MIN_RETENTION = 0.98;
  static constexpr double MIN_CLASS_ENTROPY = 0.01;
  static constexpr double MAX_VARIANCE_GROWTH = 2.0;

  EntropyPreservationResult check(const EntropyMetrics &baseline,
                                  const EntropyMetrics &candidate) {
    EntropyPreservationResult r;
    std::memset(&r, 0, sizeof(r));

    // Retention ratio
    r.retention_ratio = (baseline.total_entropy > 1e-8)
                            ? candidate.total_entropy / baseline.total_entropy
                            : 1.0;

    // No collapse check
    r.no_collapse = (candidate.collapsed_classes == 0 &&
                     candidate.min_class_entropy >= MIN_CLASS_ENTROPY);

    // Diversity: variance shouldn't grow too much
    double var_ratio =
        (baseline.entropy_variance > 1e-8)
            ? candidate.entropy_variance / baseline.entropy_variance
            : 1.0;
    r.diversity_maintained = (var_ratio <= MAX_VARIANCE_GROWTH);

    r.preserved = (r.retention_ratio >= MIN_RETENTION && r.no_collapse &&
                   r.diversity_maintained);

    if (r.preserved) {
      std::snprintf(r.reason, sizeof(r.reason),
                    "ENTROPY_OK: retention=%.4f collapsed=%u var_ratio=%.2f",
                    r.retention_ratio, candidate.collapsed_classes, var_ratio);
    } else {
      std::snprintf(r.reason, sizeof(r.reason),
                    "ENTROPY_RISK: retention=%.4f%s collapsed=%u%s var=%.2f%s",
                    r.retention_ratio,
                    (r.retention_ratio >= MIN_RETENTION) ? "" : "!",
                    candidate.collapsed_classes, r.no_collapse ? "" : "!",
                    var_ratio, r.diversity_maintained ? "" : "!");
    }

    return r;
  }
};

} // namespace merge_layer
