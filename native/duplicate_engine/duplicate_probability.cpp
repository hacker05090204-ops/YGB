/**
 * duplicate_probability.cpp — Duplicate Probability Estimator
 *
 * Outputs: duplicate_risk_score (0-100), similar_cve_ids,
 *          confidence_band.
 *
 * NO mock data. NO auto-submit. NO authority unlock.
 */

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>


namespace duplicate_engine {

// --- Confidence Band ---
enum class DuplicateConfidenceBand : uint8_t {
  VERY_LOW = 0, // 0-20: almost certainly novel
  LOW = 1,      // 20-40: probably novel
  MEDIUM = 2,   // 40-60: uncertain, needs review
  HIGH = 3,     // 60-80: likely duplicate
  VERY_HIGH = 4 // 80-100: almost certainly duplicate
};

// --- Duplicate Probability Output ---
struct DuplicateProbability {
  double risk_score; // 0-100
  DuplicateConfidenceBand band;
  char band_label[32];
  char similar_cve_ids[5][32];
  double similar_scores[5];
  uint32_t similar_count;
  double novelty_score; // 100 - risk_score
  bool should_proceed;  // Human recommendation
  char recommendation[512];
};

// --- Input signals for probability estimation ---
struct DuplicateSignals {
  double text_similarity;       // From TF-IDF cosine (0-1)
  double structural_similarity; // From component matching (0-1)
  double cwe_overlap;           // Same CWE category? (0-1)
  double temporal_proximity;    // Published within N days (0-1)
  double vendor_overlap;        // Same vendor? (0-1)
  double version_overlap;       // Same version range? (0-1)
};

// --- Duplicate Probability Estimator ---
class DuplicateProbabilityEstimator {
public:
  // Weights for combining signals
  static constexpr double W_TEXT = 0.35;
  static constexpr double W_STRUCTURAL = 0.20;
  static constexpr double W_CWE = 0.15;
  static constexpr double W_TEMPORAL = 0.10;
  static constexpr double W_VENDOR = 0.10;
  static constexpr double W_VERSION = 0.10;

  // Decision thresholds
  static constexpr double PROCEED_THRESHOLD = 40.0;
  static constexpr double BLOCK_THRESHOLD = 80.0;

private:
  uint64_t total_evaluated_;
  uint64_t total_blocked_;
  uint64_t total_warned_;

public:
  DuplicateProbabilityEstimator()
      : total_evaluated_(0), total_blocked_(0), total_warned_(0) {}

  // --- Estimate duplicate probability ---
  DuplicateProbability estimate(const DuplicateSignals &signals) {
    DuplicateProbability result;
    std::memset(&result, 0, sizeof(result));
    total_evaluated_++;

    // Weighted combination of signals
    double raw_score =
        W_TEXT * signals.text_similarity +
        W_STRUCTURAL * signals.structural_similarity +
        W_CWE * signals.cwe_overlap + W_TEMPORAL * signals.temporal_proximity +
        W_VENDOR * signals.vendor_overlap + W_VERSION * signals.version_overlap;

    // Scale to 0-100
    result.risk_score = std::min(100.0, std::max(0.0, raw_score * 100.0));

    result.novelty_score = 100.0 - result.risk_score;

    // Assign confidence band
    if (result.risk_score < 20.0) {
      result.band = DuplicateConfidenceBand::VERY_LOW;
      std::strncpy(result.band_label, "VERY_LOW", 31);
    } else if (result.risk_score < 40.0) {
      result.band = DuplicateConfidenceBand::LOW;
      std::strncpy(result.band_label, "LOW", 31);
    } else if (result.risk_score < 60.0) {
      result.band = DuplicateConfidenceBand::MEDIUM;
      std::strncpy(result.band_label, "MEDIUM", 31);
    } else if (result.risk_score < 80.0) {
      result.band = DuplicateConfidenceBand::HIGH;
      std::strncpy(result.band_label, "HIGH", 31);
    } else {
      result.band = DuplicateConfidenceBand::VERY_HIGH;
      std::strncpy(result.band_label, "VERY_HIGH", 31);
    }

    // Decision
    if (result.risk_score >= BLOCK_THRESHOLD) {
      result.should_proceed = false;
      total_blocked_++;
      std::snprintf(result.recommendation, sizeof(result.recommendation),
                    "BLOCK: Duplicate risk %.1f%% exceeds threshold %.0f%%. "
                    "This finding is very likely a known vulnerability. "
                    "Do NOT submit without proving novelty.",
                    result.risk_score, BLOCK_THRESHOLD);
    } else if (result.risk_score >= PROCEED_THRESHOLD) {
      result.should_proceed = false;
      total_warned_++;
      std::snprintf(result.recommendation, sizeof(result.recommendation),
                    "WARN: Duplicate risk %.1f%% is moderate. "
                    "Manual review required before submission. "
                    "Check for existing reports.",
                    result.risk_score);
    } else {
      result.should_proceed = true;
      std::snprintf(result.recommendation, sizeof(result.recommendation),
                    "PROCEED: Duplicate risk %.1f%% is acceptable. "
                    "Novelty score: %.1f%%.",
                    result.risk_score, result.novelty_score);
    }

    return result;
  }

  // --- Batch estimate from match results ---
  DuplicateProbability estimate_from_matches(const char similar_ids[][32],
                                             const double *scores,
                                             uint32_t count, double cwe_overlap,
                                             double temporal_proximity) {
    DuplicateSignals signals;
    std::memset(&signals, 0, sizeof(signals));

    // Use best text similarity
    if (count > 0 && scores) {
      signals.text_similarity = scores[0];
    }

    signals.cwe_overlap = cwe_overlap;
    signals.temporal_proximity = temporal_proximity;

    auto result = estimate(signals);

    // Copy similar CVE IDs
    result.similar_count = std::min(count, uint32_t(5));
    for (uint32_t i = 0; i < result.similar_count; ++i) {
      std::strncpy(result.similar_cve_ids[i], similar_ids[i], 31);
      result.similar_scores[i] = scores[i];
    }

    return result;
  }

  // --- Stats ---
  uint64_t get_total() const { return total_evaluated_; }
  uint64_t get_blocked() const { return total_blocked_; }

  // --- Self-test ---
  static bool run_tests() {
    DuplicateProbabilityEstimator est;
    int passed = 0, failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (cond) {
        ++passed;
      } else {
        ++failed;
      }
    };

    // Test 1: High similarity → high risk
    DuplicateSignals high = {0.95, 0.90, 1.0, 0.8, 1.0, 0.9};
    auto r1 = est.estimate(high);
    test(r1.risk_score >= 80.0, "High signals should be high risk");
    test(!r1.should_proceed, "High risk should not proceed");

    // Test 2: Low similarity → low risk
    DuplicateSignals low = {0.10, 0.05, 0.0, 0.1, 0.0, 0.0};
    auto r2 = est.estimate(low);
    test(r2.risk_score < 40.0, "Low signals should be low risk");
    test(r2.should_proceed, "Low risk should proceed");

    // Test 3: Medium → needs review
    DuplicateSignals med = {0.50, 0.40, 1.0, 0.3, 0.0, 0.0};
    auto r3 = est.estimate(med);
    test(r3.risk_score >= 20.0 && r3.risk_score < 80.0,
         "Medium signals should be medium risk");

    // Test 4: Stats
    test(est.get_total() == 3, "Should have 3 evaluations");

    // Test 5: Band labels
    test(r1.band == DuplicateConfidenceBand::VERY_HIGH ||
             r1.band == DuplicateConfidenceBand::HIGH,
         "High risk should have HIGH band");

    return failed == 0;
  }
};

} // namespace duplicate_engine
