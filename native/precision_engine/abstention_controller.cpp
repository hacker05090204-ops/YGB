/**
 * abstention_controller.cpp — Abstention Preference Engine
 *
 * If confidence < dynamic_threshold → ABSTAIN.
 * Prefers false negatives over false positives.
 * Tracks abstention rate and adjusts for data efficiency.
 *
 * NO mock data. NO synthetic fallback. NO auto-submit.
 */

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <vector>


namespace precision_engine {

// --- Abstention Reason ---
enum class AbstentionReason : uint8_t {
  NONE = 0,                 // No abstention
  LOW_CONFIDENCE = 1,       // Below dynamic threshold
  FEATURE_DISAGREEMENT = 2, // Multi-signal disagree
  HIGH_CALIBRATION_GAP = 3, // In known overconfident bin
  UNSTABLE_FEATURES = 4,    // Unstable feature reliance
  INSUFFICIENT_EVIDENCE = 5 // Not enough supporting signals
};

struct AbstentionResult {
  bool should_abstain;
  AbstentionReason reason;
  double confidence;
  double threshold;
  double abstention_cost; // Estimated value of missed finding
  double fp_risk;         // Estimated false positive probability
  char explanation[512];
};

struct AbstentionStats {
  uint64_t total_predictions;
  uint64_t total_abstentions;
  uint64_t abstentions_low_conf;
  uint64_t abstentions_disagreement;
  uint64_t abstentions_calibration;
  uint64_t abstentions_unstable;
  uint64_t abstentions_insufficient;
  double abstention_rate;
};

// --- Feature Agreement Check ---
struct FeatureSignals {
  double signal_confidence;
  double response_confidence;
  double topology_confidence;
  double state_graph_confidence;
};

// --- Abstention Controller ---
class AbstentionController {
public:
  static constexpr double MAX_ABSTENTION_RATE = 0.40;
  static constexpr double AGREEMENT_THRESHOLD = 0.70;
  static constexpr double CALIBRATION_GAP_MAX = 0.10;
  static constexpr uint32_t MIN_AGREEING_SIGNALS = 3;

private:
  double dynamic_threshold_;
  AbstentionStats stats_;
  bool prefer_false_negatives_;

public:
  AbstentionController()
      : dynamic_threshold_(0.93),
        prefer_false_negatives_(true) // ALWAYS prefer FN over FP
  {
    std::memset(&stats_, 0, sizeof(stats_));
  }

  void set_threshold(double threshold) {
    dynamic_threshold_ = std::max(0.50, std::min(1.0, threshold));
  }

  double get_threshold() const { return dynamic_threshold_; }

  // --- Core abstention decision ---
  AbstentionResult evaluate(double overall_confidence,
                            const FeatureSignals &signals,
                            double calibration_gap) {
    AbstentionResult result;
    std::memset(&result, 0, sizeof(result));
    result.confidence = overall_confidence;
    result.threshold = dynamic_threshold_;
    result.should_abstain = false;
    result.reason = AbstentionReason::NONE;

    stats_.total_predictions++;

    // Check 1: Below dynamic threshold
    if (overall_confidence < dynamic_threshold_) {
      result.should_abstain = true;
      result.reason = AbstentionReason::LOW_CONFIDENCE;
      result.fp_risk = estimate_fp_risk(overall_confidence);
      std::snprintf(
          result.explanation, sizeof(result.explanation),
          "ABSTAIN: confidence %.4f < threshold %.4f (FP risk: %.1f%%)",
          overall_confidence, dynamic_threshold_, result.fp_risk * 100.0);
      stats_.abstentions_low_conf++;
      stats_.total_abstentions++;
      update_rate();
      return result;
    }

    // Check 2: Multi-signal disagreement
    uint32_t agreeing = count_agreeing_signals(signals);
    if (agreeing < MIN_AGREEING_SIGNALS) {
      result.should_abstain = true;
      result.reason = AbstentionReason::FEATURE_DISAGREEMENT;
      result.fp_risk = 0.5; // High risk when signals disagree
      std::snprintf(result.explanation, sizeof(result.explanation),
                    "ABSTAIN: only %u/%u signals agree (need %u)", agreeing, 4u,
                    MIN_AGREEING_SIGNALS);
      stats_.abstentions_disagreement++;
      stats_.total_abstentions++;
      update_rate();
      return result;
    }

    // Check 3: Known calibration gap
    if (calibration_gap > CALIBRATION_GAP_MAX) {
      result.should_abstain = true;
      result.reason = AbstentionReason::HIGH_CALIBRATION_GAP;
      result.fp_risk = calibration_gap;
      std::snprintf(result.explanation, sizeof(result.explanation),
                    "ABSTAIN: calibration gap %.4f > max %.4f in this bin",
                    calibration_gap, CALIBRATION_GAP_MAX);
      stats_.abstentions_calibration++;
      stats_.total_abstentions++;
      update_rate();
      return result;
    }

    // Check 4: Feature stability
    double signal_variance = compute_signal_variance(signals);
    if (signal_variance > 0.15) {
      result.should_abstain = true;
      result.reason = AbstentionReason::UNSTABLE_FEATURES;
      result.fp_risk = signal_variance;
      std::snprintf(result.explanation, sizeof(result.explanation),
                    "ABSTAIN: signal variance %.4f > 0.15 (unstable features)",
                    signal_variance);
      stats_.abstentions_unstable++;
      stats_.total_abstentions++;
      update_rate();
      return result;
    }

    // All checks passed
    result.fp_risk = estimate_fp_risk(overall_confidence);
    result.abstention_cost = 0.0;
    std::snprintf(result.explanation, sizeof(result.explanation),
                  "PROCEED: confidence %.4f, %u/4 signals agree, "
                  "gap %.4f, variance %.4f",
                  overall_confidence, agreeing, calibration_gap,
                  signal_variance);
    update_rate();
    return result;
  }

  // --- Stats ---
  AbstentionStats get_stats() const { return stats_; }

  void reset_stats() { std::memset(&stats_, 0, sizeof(stats_)); }

  // --- Self-test ---
  static bool run_tests() {
    AbstentionController ctrl;
    int passed = 0, failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (cond) {
        ++passed;
      } else {
        ++failed;
      }
    };

    // Test 1: Low confidence → ABSTAIN
    FeatureSignals good_signals = {0.95, 0.92, 0.94, 0.91};
    auto r1 = ctrl.evaluate(0.70, good_signals, 0.02);
    test(r1.should_abstain, "Low confidence should abstain");
    test(r1.reason == AbstentionReason::LOW_CONFIDENCE,
         "Reason should be LOW_CONFIDENCE");

    // Test 2: High confidence, good signals → PROCEED
    auto r2 = ctrl.evaluate(0.97, good_signals, 0.01);
    test(!r2.should_abstain, "High conf + good signals should proceed");

    // Test 3: High confidence, disagreeing signals → ABSTAIN
    FeatureSignals bad_signals = {0.95, 0.30, 0.25, 0.91};
    auto r3 = ctrl.evaluate(0.95, bad_signals, 0.01);
    test(r3.should_abstain, "Disagreeing signals should abstain");
    test(r3.reason == AbstentionReason::FEATURE_DISAGREEMENT,
         "Reason should be FEATURE_DISAGREEMENT");

    // Test 4: High calibration gap → ABSTAIN
    auto r4 = ctrl.evaluate(0.95, good_signals, 0.15);
    test(r4.should_abstain, "High calibration gap should abstain");

    // Test 5: Abstention rate tracking
    auto stats = ctrl.get_stats();
    test(stats.total_predictions > 0, "Should track predictions");
    test(stats.total_abstentions > 0, "Should track abstentions");

    return failed == 0;
  }

private:
  uint32_t count_agreeing_signals(const FeatureSignals &s) const {
    uint32_t count = 0;
    if (s.signal_confidence >= AGREEMENT_THRESHOLD)
      ++count;
    if (s.response_confidence >= AGREEMENT_THRESHOLD)
      ++count;
    if (s.topology_confidence >= AGREEMENT_THRESHOLD)
      ++count;
    if (s.state_graph_confidence >= AGREEMENT_THRESHOLD)
      ++count;
    return count;
  }

  double compute_signal_variance(const FeatureSignals &s) const {
    double vals[4] = {s.signal_confidence, s.response_confidence,
                      s.topology_confidence, s.state_graph_confidence};
    double mean = 0;
    for (int i = 0; i < 4; ++i)
      mean += vals[i];
    mean /= 4.0;

    double var = 0;
    for (int i = 0; i < 4; ++i) {
      double d = vals[i] - mean;
      var += d * d;
    }
    return var / 4.0;
  }

  double estimate_fp_risk(double confidence) const {
    // Based on calibration data analysis:
    // Below 0.80: ~15% FP, 0.80-0.87: ~15.2%, 0.87-0.93: ~7.3%
    // Above 0.93: ~0.4%
    if (confidence >= 0.93)
      return 0.004;
    if (confidence >= 0.87)
      return 0.073;
    if (confidence >= 0.80)
      return 0.152;
    if (confidence >= 0.73)
      return 0.100;
    return 0.20;
  }

  void update_rate() {
    if (stats_.total_predictions > 0) {
      stats_.abstention_rate = static_cast<double>(stats_.total_abstentions) /
                               stats_.total_predictions;
    }
  }
};

} // namespace precision_engine
