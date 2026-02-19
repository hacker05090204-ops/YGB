/**
 * duplicate_risk_estimator.cpp — Duplicate Risk Scoring
 *
 * Before reporting a finding, estimate duplicate risk:
 *   - Similarity scoring against known findings
 *   - Fuzzy hash comparison
 *   - Structural fingerprint matching
 *   - Temporal proximity check
 *
 * Block reporting if duplicate probability > threshold.
 * NO auto-submission.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace precision_engine {

// =========================================================================
// DUPLICATE CHECK RESULT
// =========================================================================

struct DuplicateCheckResult {
  double similarity_score;   // 0.0–1.0
  double hash_similarity;    // fuzzy hash match 0.0–1.0
  double structural_match;   // structural fingerprint 0.0–1.0
  double temporal_proximity; // 0.0–1.0 (closer in time = higher)
  double combined_risk;      // weighted combined score
  bool likely_duplicate;
  bool block_reporting;
  char reason[256];
};

// =========================================================================
// DUPLICATE RISK ESTIMATOR
// =========================================================================

class DuplicateRiskEstimator {
public:
  static constexpr double DUPLICATE_THRESHOLD = 0.75;
  static constexpr double BLOCK_THRESHOLD = 0.85;
  static constexpr bool ALLOW_AUTO_SUBMIT = false;

  DuplicateRiskEstimator() : total_checks_(0), total_blocked_(0) {}

  DuplicateCheckResult estimate(double similarity, double hash_sim,
                                double structural, double temporal) {
    DuplicateCheckResult r;
    std::memset(&r, 0, sizeof(r));

    r.similarity_score = similarity;
    r.hash_similarity = hash_sim;
    r.structural_match = structural;
    r.temporal_proximity = temporal;

    // Weighted combination
    r.combined_risk = similarity * 0.35 + hash_sim * 0.25 + structural * 0.25 +
                      temporal * 0.15;

    r.likely_duplicate = (r.combined_risk >= DUPLICATE_THRESHOLD);
    r.block_reporting = (r.combined_risk >= BLOCK_THRESHOLD);

    ++total_checks_;
    if (r.block_reporting) {
      ++total_blocked_;
      std::snprintf(r.reason, sizeof(r.reason),
                    "DUPLICATE_BLOCKED: risk=%.3f (sim=%.2f hash=%.2f "
                    "struct=%.2f temp=%.2f)",
                    r.combined_risk, similarity, hash_sim, structural,
                    temporal);
    } else if (r.likely_duplicate) {
      std::snprintf(r.reason, sizeof(r.reason),
                    "DUPLICATE_WARNING: risk=%.3f — requires human review",
                    r.combined_risk);
    } else {
      std::snprintf(r.reason, sizeof(r.reason), "LOW_DUPLICATE_RISK: %.3f",
                    r.combined_risk);
    }

    return r;
  }

  uint32_t total_checks() const { return total_checks_; }
  uint32_t total_blocked() const { return total_blocked_; }

private:
  uint32_t total_checks_;
  uint32_t total_blocked_;
};

} // namespace precision_engine
