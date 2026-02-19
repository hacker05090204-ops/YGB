/**
 * false_positive_suppressor.cpp — Multi-Signal False Positive Suppression
 *
 * Requires agreement across signal, response, topology, and state_graph.
 * Penalizes unstable feature reliance.
 * Rejects if multi-feature agreement threshold not met.
 *
 * NO mock data. NO auto-submit. NO authority unlock.
 */

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

namespace precision_engine {

// --- Feature vector per signal channel ---
struct ChannelEvidence {
  double confidence;
  double stability;     // Consistency across repeated observations
  double feature_count; // Number of contributing features
  bool active;          // Channel produced output
};

struct SuppressionInput {
  ChannelEvidence signal;
  ChannelEvidence response;
  ChannelEvidence topology;
  ChannelEvidence state_graph;
  double overall_confidence; // Model's raw output
};

enum class SuppressionVerdict : uint8_t {
  ALLOW = 0,        // All checks pass
  SUPPRESS_FP = 1,  // Likely false positive
  NEEDS_REVIEW = 2, // Borderline, human review required
  INVALID_INPUT = 3 // Missing required channels
};

struct SuppressionResult {
  SuppressionVerdict verdict;
  double adjusted_confidence;
  double agreement_score; // 0-1, how much channels agree
  double stability_score; // 0-1, feature stability
  double penalty;         // Confidence penalty applied
  uint32_t active_channels;
  uint32_t agreeing_channels;
  char reason[512];
};

// --- False Positive Suppressor ---
class FalsePositiveSuppressor {
public:
  static constexpr double AGREEMENT_MIN = 0.75;
  static constexpr double STABILITY_MIN = 0.60;
  static constexpr double PENALTY_PER_MISSING = 0.10;
  static constexpr double PENALTY_DISAGREEMENT = 0.15;
  static constexpr double PENALTY_UNSTABLE = 0.08;
  static constexpr uint32_t MIN_ACTIVE_CHANNELS = 3;
  static constexpr double SUPPRESS_THRESHOLD = 0.50;
  static constexpr double REVIEW_THRESHOLD = 0.80;

private:
  double agreement_min_;
  double stability_min_;
  uint64_t total_evaluated_;
  uint64_t total_suppressed_;
  uint64_t total_allowed_;
  uint64_t total_review_;

public:
  FalsePositiveSuppressor()
      : agreement_min_(AGREEMENT_MIN), stability_min_(STABILITY_MIN),
        total_evaluated_(0), total_suppressed_(0), total_allowed_(0),
        total_review_(0) {}

  // --- Evaluate prediction for false positive risk ---
  SuppressionResult evaluate(const SuppressionInput &input) {
    SuppressionResult result;
    std::memset(&result, 0, sizeof(result));
    total_evaluated_++;

    // Count active channels
    const ChannelEvidence *channels[4] = {&input.signal, &input.response,
                                          &input.topology, &input.state_graph};
    result.active_channels = 0;
    for (int i = 0; i < 4; ++i) {
      if (channels[i]->active)
        ++result.active_channels;
    }

    // Check minimum active channels
    if (result.active_channels < MIN_ACTIVE_CHANNELS) {
      result.verdict = SuppressionVerdict::SUPPRESS_FP;
      result.adjusted_confidence = 0.0;
      result.penalty = input.overall_confidence;
      std::snprintf(result.reason, sizeof(result.reason),
                    "SUPPRESS: only %u/%u channels active (need %u)",
                    result.active_channels, 4u, MIN_ACTIVE_CHANNELS);
      total_suppressed_++;
      return result;
    }

    // Compute agreement score
    result.agreement_score = compute_agreement(channels);

    // Compute stability score
    result.stability_score = compute_stability(channels);

    // Compute agreement penalties
    result.penalty = 0.0;

    // Penalty for missing channels
    uint32_t missing = 4 - result.active_channels;
    result.penalty += missing * PENALTY_PER_MISSING;

    // Penalty for disagreement
    if (result.agreement_score < agreement_min_) {
      result.penalty += PENALTY_DISAGREEMENT *
                        (1.0 - result.agreement_score / agreement_min_);
    }

    // Penalty for unstable features
    if (result.stability_score < stability_min_) {
      result.penalty +=
          PENALTY_UNSTABLE * (1.0 - result.stability_score / stability_min_);
    }

    // Count agreeing channels
    result.agreeing_channels =
        count_agreeing(channels, input.overall_confidence);

    // Adjust confidence
    result.adjusted_confidence =
        std::max(0.0, input.overall_confidence - result.penalty);

    // Verdict
    if (result.adjusted_confidence < SUPPRESS_THRESHOLD) {
      result.verdict = SuppressionVerdict::SUPPRESS_FP;
      std::snprintf(result.reason, sizeof(result.reason),
                    "SUPPRESS: adjusted confidence %.4f < %.2f "
                    "(agreement=%.2f, stability=%.2f, penalty=%.4f)",
                    result.adjusted_confidence, SUPPRESS_THRESHOLD,
                    result.agreement_score, result.stability_score,
                    result.penalty);
      total_suppressed_++;
    } else if (result.adjusted_confidence < REVIEW_THRESHOLD) {
      result.verdict = SuppressionVerdict::NEEDS_REVIEW;
      std::snprintf(result.reason, sizeof(result.reason),
                    "REVIEW: adjusted confidence %.4f in review zone "
                    "[%.2f, %.2f) (agreement=%.2f, penalty=%.4f)",
                    result.adjusted_confidence, SUPPRESS_THRESHOLD,
                    REVIEW_THRESHOLD, result.agreement_score, result.penalty);
      total_review_++;
    } else {
      result.verdict = SuppressionVerdict::ALLOW;
      std::snprintf(result.reason, sizeof(result.reason),
                    "ALLOW: adjusted confidence %.4f (agreement=%.2f, "
                    "stability=%.2f, %u/4 channels agree)",
                    result.adjusted_confidence, result.agreement_score,
                    result.stability_score, result.agreeing_channels);
      total_allowed_++;
    }

    return result;
  }

  // --- Get stats ---
  uint64_t get_total() const { return total_evaluated_; }
  uint64_t get_suppressed() const { return total_suppressed_; }
  uint64_t get_allowed() const { return total_allowed_; }
  double suppression_rate() const {
    if (total_evaluated_ == 0)
      return 0.0;
    return static_cast<double>(total_suppressed_) / total_evaluated_;
  }

  // --- Self-test ---
  static bool run_tests() {
    FalsePositiveSuppressor sup;
    int passed = 0, failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (cond) {
        ++passed;
      } else {
        ++failed;
      }
    };

    // Test 1: All channels agree, high confidence → ALLOW
    SuppressionInput good;
    good.signal = {0.95, 0.90, 10, true};
    good.response = {0.93, 0.88, 8, true};
    good.topology = {0.91, 0.85, 12, true};
    good.state_graph = {0.94, 0.92, 6, true};
    good.overall_confidence = 0.95;
    auto r1 = sup.evaluate(good);
    test(r1.verdict == SuppressionVerdict::ALLOW, "Good input should ALLOW");

    // Test 2: Only 2 channels active → SUPPRESS
    SuppressionInput sparse;
    sparse.signal = {0.95, 0.90, 10, true};
    sparse.response = {0.93, 0.88, 8, true};
    sparse.topology = {0.0, 0.0, 0, false};
    sparse.state_graph = {0.0, 0.0, 0, false};
    sparse.overall_confidence = 0.95;
    auto r2 = sup.evaluate(sparse);
    test(r2.verdict == SuppressionVerdict::SUPPRESS_FP,
         "Sparse channels should SUPPRESS");

    // Test 3: Disagreeing channels → SUPPRESS or REVIEW
    SuppressionInput disagree;
    disagree.signal = {0.95, 0.90, 10, true};
    disagree.response = {0.20, 0.88, 8, true};
    disagree.topology = {0.15, 0.85, 12, true};
    disagree.state_graph = {0.94, 0.92, 6, true};
    disagree.overall_confidence = 0.80;
    auto r3 = sup.evaluate(disagree);
    test(r3.verdict != SuppressionVerdict::ALLOW,
         "Disagreeing channels should not ALLOW");

    // Test 4: Unstable features → penalized
    SuppressionInput unstable;
    unstable.signal = {0.85, 0.30, 2, true};
    unstable.response = {0.83, 0.25, 2, true};
    unstable.topology = {0.81, 0.20, 2, true};
    unstable.state_graph = {0.84, 0.28, 2, true};
    unstable.overall_confidence = 0.85;
    auto r4 = sup.evaluate(unstable);
    test(r4.adjusted_confidence < unstable.overall_confidence,
         "Unstable features should reduce confidence");

    // Test 5: Stats tracking
    test(sup.get_total() == 4, "Should have 4 total evaluations");
    test(sup.get_suppressed() >= 1, "Should have suppressions");

    return failed == 0;
  }

private:
  double compute_agreement(const ChannelEvidence *channels[4]) const {
    // Pairwise agreement between active channels
    double total = 0.0;
    int pairs = 0;
    for (int i = 0; i < 4; ++i) {
      if (!channels[i]->active)
        continue;
      for (int j = i + 1; j < 4; ++j) {
        if (!channels[j]->active)
          continue;
        double diff =
            std::fabs(channels[i]->confidence - channels[j]->confidence);
        total += 1.0 - diff; // Agreement = 1 - difference
        ++pairs;
      }
    }
    if (pairs == 0)
      return 0.0;
    return total / pairs;
  }

  double compute_stability(const ChannelEvidence *channels[4]) const {
    double total = 0.0;
    int active = 0;
    for (int i = 0; i < 4; ++i) {
      if (channels[i]->active) {
        total += channels[i]->stability;
        ++active;
      }
    }
    if (active == 0)
      return 0.0;
    return total / active;
  }

  uint32_t count_agreeing(const ChannelEvidence *channels[4],
                          double target) const {
    uint32_t count = 0;
    double threshold = target * 0.80; // Within 20% of target
    for (int i = 0; i < 4; ++i) {
      if (channels[i]->active && channels[i]->confidence >= threshold) {
        ++count;
      }
    }
    return count;
  }
};

} // namespace precision_engine
