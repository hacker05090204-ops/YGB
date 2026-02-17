/**
 * reproducibility_score.cpp — PoC Reproducibility Scorer
 *
 * Re-runs PoC N times, computes success rate.
 * Outputs reproducibility percentage and stability assessment.
 *
 * NO mock data. NO auto-submit.
 */

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <vector>


namespace confidence_engine {

struct ReproductionAttempt {
  uint32_t attempt_id;
  bool succeeded;
  double response_time_ms;
  double similarity_to_original; // 0-1
  char error[256];
};

struct ReproducibilityResult {
  double success_rate; // 0-1
  double success_pct;  // 0-100
  uint32_t total_attempts;
  uint32_t successful_attempts;
  double avg_response_time_ms;
  double response_time_variance;
  double avg_similarity;
  char stability_label[32];
  char recommendation[256];
  bool meets_threshold;
};

// --- Reproducibility Scorer ---
class ReproducibilityScorer {
public:
  static constexpr uint32_t DEFAULT_ATTEMPTS = 5;
  static constexpr double MIN_SUCCESS_RATE = 0.60;
  static constexpr double HIGH_SUCCESS_RATE = 0.90;
  static constexpr double MIN_SIMILARITY = 0.70;

  // --- Score from reproduction attempts ---
  ReproducibilityResult
  score(const std::vector<ReproductionAttempt> &attempts) const {
    ReproducibilityResult result;
    std::memset(&result, 0, sizeof(result));

    result.total_attempts = static_cast<uint32_t>(attempts.size());

    if (attempts.empty()) {
      result.success_rate = 0.0;
      result.success_pct = 0.0;
      result.meets_threshold = false;
      std::strncpy(result.stability_label, "Untested", 31);
      std::strncpy(result.recommendation,
                   "No reproduction attempts. Run PoC at least 5 times.",
                   sizeof(result.recommendation) - 1);
      return result;
    }

    // Count successes
    double total_time = 0;
    double total_sim = 0;
    for (const auto &a : attempts) {
      if (a.succeeded) {
        result.successful_attempts++;
        total_sim += a.similarity_to_original;
      }
      total_time += a.response_time_ms;
    }

    result.success_rate =
        static_cast<double>(result.successful_attempts) / result.total_attempts;
    result.success_pct = result.success_rate * 100.0;
    result.avg_response_time_ms = total_time / result.total_attempts;

    if (result.successful_attempts > 0) {
      result.avg_similarity = total_sim / result.successful_attempts;
    }

    // Response time variance
    double var = 0;
    for (const auto &a : attempts) {
      double d = a.response_time_ms - result.avg_response_time_ms;
      var += d * d;
    }
    result.response_time_variance = var / result.total_attempts;

    // Stability label
    if (result.success_rate >= HIGH_SUCCESS_RATE &&
        result.avg_similarity >= MIN_SIMILARITY) {
      std::strncpy(result.stability_label, "Stable", 31);
    } else if (result.success_rate >= MIN_SUCCESS_RATE) {
      std::strncpy(result.stability_label, "Intermittent", 31);
    } else {
      std::strncpy(result.stability_label, "Unreliable", 31);
    }

    result.meets_threshold = result.success_rate >= MIN_SUCCESS_RATE;

    // Recommendation
    if (result.success_rate >= HIGH_SUCCESS_RATE) {
      std::snprintf(result.recommendation, sizeof(result.recommendation),
                    "Highly reproducible (%.0f%%, %u/%u). "
                    "Suitable for report.",
                    result.success_pct, result.successful_attempts,
                    result.total_attempts);
    } else if (result.meets_threshold) {
      std::snprintf(result.recommendation, sizeof(result.recommendation),
                    "Partially reproducible (%.0f%%, %u/%u). "
                    "Note intermittency in report.",
                    result.success_pct, result.successful_attempts,
                    result.total_attempts);
    } else {
      std::snprintf(result.recommendation, sizeof(result.recommendation),
                    "Unreliable (%.0f%%, %u/%u). "
                    "Do NOT submit until consistently reproducible.",
                    result.success_pct, result.successful_attempts,
                    result.total_attempts);
    }

    return result;
  }

  // --- Self-test ---
  static bool run_tests() {
    ReproducibilityScorer scorer;
    int passed = 0, failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (cond) {
        ++passed;
      } else {
        ++failed;
      }
    };

    // Test 1: Fully reproducible
    std::vector<ReproductionAttempt> all_good = {{1, true, 150.0, 0.98, ""},
                                                 {2, true, 145.0, 0.97, ""},
                                                 {3, true, 148.0, 0.99, ""},
                                                 {4, true, 152.0, 0.96, ""},
                                                 {5, true, 147.0, 0.98, ""}};
    auto r1 = scorer.score(all_good);
    test(r1.success_pct == 100.0, "5/5 should be 100%");
    test(r1.meets_threshold, "Should meet threshold");

    // Test 2: Intermittent
    std::vector<ReproductionAttempt> partial = {
        {1, true, 150.0, 0.95, ""},
        {2, false, 200.0, 0.0, "timeout"},
        {3, true, 155.0, 0.90, ""},
        {4, true, 148.0, 0.92, ""},
        {5, false, 300.0, 0.0, "timeout"}};
    auto r2 = scorer.score(partial);
    test(r2.success_pct == 60.0, "3/5 should be 60%");
    test(r2.meets_threshold, "60% should meet threshold");

    // Test 3: Unreliable
    std::vector<ReproductionAttempt> bad = {{1, false, 500.0, 0.0, "error"},
                                            {2, false, 600.0, 0.0, "error"},
                                            {3, true, 150.0, 0.50, ""},
                                            {4, false, 400.0, 0.0, "error"},
                                            {5, false, 550.0, 0.0, "error"}};
    auto r3 = scorer.score(bad);
    test(!r3.meets_threshold, "1/5 should not meet threshold");

    // Test 4: No attempts
    std::vector<ReproductionAttempt> empty;
    auto r4 = scorer.score(empty);
    test(!r4.meets_threshold, "No attempts = not reproducible");

    return failed == 0;
  }
};

} // namespace confidence_engine
