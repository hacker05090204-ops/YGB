/**
 * evidence_strength.cpp — Evidence Weight Engine
 *
 * Computes evidence weight from: PoC, screenshots, response diff,
 * timing, header analysis, error messages.
 *
 * NO mock data. NO authority unlock.
 */

#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>


namespace confidence_engine {

struct EvidenceItem {
  char type[64];      // "screenshot", "video", "poc_steps", etc.
  double weight;      // 0-1, how strong this evidence is
  double reliability; // 0-1, how trustworthy
  bool verified;      // Independently verified?
};

struct EvidenceAssessment {
  double total_strength;    // 0-1
  double total_reliability; // 0-1
  uint32_t item_count;
  uint32_t verified_count;
  char strength_label[32]; // "Strong", "Medium", "Weak"
  char recommendation[256];
  bool sufficient_for_report;
};

// --- Evidence Strength Evaluator ---
class EvidenceStrengthEvaluator {
public:
  static constexpr double MIN_STRENGTH_FOR_REPORT = 0.40;

  // --- Weights for evidence types ---
  static constexpr double W_POC_STEPS = 0.25;
  static constexpr double W_SCREENSHOT = 0.15;
  static constexpr double W_VIDEO = 0.20;
  static constexpr double W_RESPONSE_DIFF = 0.15;
  static constexpr double W_TIMING = 0.10;
  static constexpr double W_ERROR_MSG = 0.10;
  static constexpr double W_HEADER_LEAK = 0.05;

  // --- Evaluate evidence ---
  EvidenceAssessment evaluate(const std::vector<EvidenceItem> &items) const {
    EvidenceAssessment result;
    std::memset(&result, 0, sizeof(result));

    if (items.empty()) {
      result.total_strength = 0.0;
      result.total_reliability = 0.0;
      result.sufficient_for_report = false;
      std::strncpy(result.strength_label, "None", 31);
      std::strncpy(result.recommendation,
                   "No evidence provided. Cannot proceed.",
                   sizeof(result.recommendation) - 1);
      return result;
    }

    result.item_count = static_cast<uint32_t>(items.size());

    double total_weight = 0.0;
    double total_rel = 0.0;
    for (const auto &item : items) {
      total_weight += item.weight;
      total_rel += item.reliability;
      if (item.verified)
        result.verified_count++;
    }

    result.total_strength = std::min(1.0, total_weight / items.size());
    result.total_reliability = total_rel / items.size();

    // Bonus for multiple verified items
    if (result.verified_count >= 2) {
      result.total_strength = std::min(1.0, result.total_strength * 1.1);
    }

    // Label
    if (result.total_strength >= 0.75) {
      std::strncpy(result.strength_label, "Strong", 31);
    } else if (result.total_strength >= 0.40) {
      std::strncpy(result.strength_label, "Medium", 31);
    } else {
      std::strncpy(result.strength_label, "Weak", 31);
    }

    result.sufficient_for_report =
        result.total_strength >= MIN_STRENGTH_FOR_REPORT;

    if (result.sufficient_for_report) {
      std::snprintf(result.recommendation, sizeof(result.recommendation),
                    "Evidence is %s (%.0f%%). Proceed with human review.",
                    result.strength_label, result.total_strength * 100.0);
    } else {
      std::snprintf(result.recommendation, sizeof(result.recommendation),
                    "Evidence too weak (%.0f%%). Gather more evidence "
                    "before report: add PoC steps, screenshots, or "
                    "response diffs.",
                    result.total_strength * 100.0);
    }

    return result;
  }

  // --- Self-test ---
  static bool run_tests() {
    EvidenceStrengthEvaluator eval;
    int passed = 0, failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (cond) {
        ++passed;
      } else {
        ++failed;
      }
    };

    // Test 1: Strong evidence
    std::vector<EvidenceItem> strong = {{"poc_steps", 0.90, 0.95, true},
                                        {"screenshot", 0.85, 0.90, true},
                                        {"video", 0.80, 0.85, false},
                                        {"response_diff", 0.75, 0.80, true}};
    auto r1 = eval.evaluate(strong);
    test(r1.sufficient_for_report, "Strong should be sufficient");
    test(r1.verified_count == 3, "Should have 3 verified");

    // Test 2: Weak evidence
    std::vector<EvidenceItem> weak = {{"header_leak", 0.15, 0.30, false}};
    auto r2 = eval.evaluate(weak);
    test(!r2.sufficient_for_report, "Weak should be insufficient");

    // Test 3: No evidence
    std::vector<EvidenceItem> none;
    auto r3 = eval.evaluate(none);
    test(!r3.sufficient_for_report, "No evidence = not sufficient");
    test(r3.total_strength == 0.0, "Strength should be 0");

    return failed == 0;
  }
};

} // namespace confidence_engine
