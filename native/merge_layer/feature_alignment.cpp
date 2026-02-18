/**
 * feature_alignment.cpp — Feature Space Alignment Check
 *
 * Verifies feature space alignment before merge:
 *   - Cosine similarity >= 0.95 across feature vectors
 *   - No feature drift beyond tolerance
 *   - Representation space consistency
 *
 * If alignment fails: reject merge, rollback to certified snapshot.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace merge_layer {

// =========================================================================
// ALIGNMENT RESULT
// =========================================================================

struct FeatureAlignmentResult {
  double cosine_similarity;
  double l2_distance;
  double angular_distance;
  bool aligned;
  char reason[256];
};

// =========================================================================
// FEATURE ALIGNMENT ENGINE
// =========================================================================

class FeatureAlignment {
public:
  static constexpr double MIN_COSINE_SIMILARITY = 0.95;
  static constexpr double MAX_L2_DISTANCE = 0.50;

  // Check alignment between two feature vectors
  FeatureAlignmentResult check(const float *vec_a, const float *vec_b,
                               uint32_t dim) {
    FeatureAlignmentResult r;
    std::memset(&r, 0, sizeof(r));

    if (dim == 0) {
      r.aligned = false;
      std::snprintf(r.reason, sizeof(r.reason), "EMPTY_VECTORS");
      return r;
    }

    // Cosine similarity
    double dot = 0.0, norm_a = 0.0, norm_b = 0.0;
    for (uint32_t i = 0; i < dim; ++i) {
      dot += vec_a[i] * vec_b[i];
      norm_a += vec_a[i] * vec_a[i];
      norm_b += vec_b[i] * vec_b[i];
    }
    norm_a = std::sqrt(norm_a);
    norm_b = std::sqrt(norm_b);
    r.cosine_similarity =
        (norm_a > 1e-8 && norm_b > 1e-8) ? dot / (norm_a * norm_b) : 0.0;

    // L2 distance (normalized)
    double l2 = 0.0;
    for (uint32_t i = 0; i < dim; ++i) {
      double d = vec_a[i] - vec_b[i];
      l2 += d * d;
    }
    r.l2_distance = std::sqrt(l2) / dim;

    // Angular distance
    double clamped = r.cosine_similarity;
    if (clamped > 1.0)
      clamped = 1.0;
    if (clamped < -1.0)
      clamped = -1.0;
    r.angular_distance = std::acos(clamped) / 3.14159265358979;

    // Verdict
    r.aligned = (r.cosine_similarity >= MIN_COSINE_SIMILARITY &&
                 r.l2_distance <= MAX_L2_DISTANCE);

    if (r.aligned) {
      std::snprintf(r.reason, sizeof(r.reason), "ALIGNED: cos=%.4f L2=%.4f",
                    r.cosine_similarity, r.l2_distance);
    } else {
      std::snprintf(r.reason, sizeof(r.reason),
                    "MISALIGNED: cos=%.4f(<%.2f) L2=%.4f(>%.2f)",
                    r.cosine_similarity, MIN_COSINE_SIMILARITY, r.l2_distance,
                    MAX_L2_DISTANCE);
    }

    return r;
  }
};

} // namespace merge_layer
