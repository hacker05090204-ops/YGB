/**
 * confidence_scorer.cpp — Structured Confidence Band Output
 *
 * Replaces binary "Bug Found" with rich confidence object:
 * { confidence%, evidence_strength, reproducibility, impact,
 *   duplicate_risk, scope_compliance }
 *
 * NO mock data. NO auto-submit. NO authority unlock.
 */

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>


namespace confidence_engine {

enum class EvidenceLevel : uint8_t {
  NONE = 0,
  LOW = 1,
  MEDIUM = 2,
  HIGH = 3,
  CRITICAL = 4
};

enum class ImpactCertainty : uint8_t {
  UNVERIFIED = 0,
  LOW = 1,
  MEDIUM = 2,
  HIGH = 3,
  CONFIRMED = 4
};

// --- Structured Confidence Band ---
struct ConfidenceBand {
  double confidence_pct; // 0-100
  EvidenceLevel evidence_strength;
  double reproducibility_pct; // 0-100
  ImpactCertainty business_impact;
  double duplicate_risk_pct; // 0-100
  bool scope_compliant;
  char confidence_label[32];
  char evidence_label[32];
  char impact_label[32];
  char summary[512];
  bool human_review_required; // ALWAYS true
};

// --- Input signals for scoring ---
struct ScoringInput {
  double model_confidence;    // Raw model output (0-1)
  double calibration_gap;     // From calibration bin
  double signal_agreement;    // Multi-signal agreement (0-1)
  double feature_stability;   // Feature consistency (0-1)
  double poc_success_rate;    // PoC reproduction rate (0-1)
  double response_uniqueness; // How unique is the response (0-1)
  double timing_consistency;  // Timing-based evidence (0-1)
  double duplicate_risk;      // From duplicate estimator (0-100)
  bool scope_valid;           // From scope engine
  bool has_screenshot;
  bool has_video;
  bool has_poc_steps;
};

// --- Confidence Scorer ---
class ConfidenceScorer {
public:
  ConfidenceScorer() = default;

  // --- Score a finding ---
  ConfidenceBand score(const ScoringInput &input) const {
    ConfidenceBand band;
    std::memset(&band, 0, sizeof(band));

    // Adjusted confidence (penalize overconfident bins)
    double adjusted = input.model_confidence;
    if (input.calibration_gap > 0.05) {
      adjusted -= input.calibration_gap * 0.5;
    }
    adjusted *= input.signal_agreement;
    adjusted = std::max(0.0, std::min(1.0, adjusted));

    band.confidence_pct = adjusted * 100.0;

    // Confidence label
    if (band.confidence_pct >= 90) {
      std::strncpy(band.confidence_label, "VERY_HIGH", 31);
    } else if (band.confidence_pct >= 75) {
      std::strncpy(band.confidence_label, "HIGH", 31);
    } else if (band.confidence_pct >= 50) {
      std::strncpy(band.confidence_label, "MEDIUM", 31);
    } else if (band.confidence_pct >= 25) {
      std::strncpy(band.confidence_label, "LOW", 31);
    } else {
      std::strncpy(band.confidence_label, "VERY_LOW", 31);
    }

    // Evidence strength
    double evidence_score = 0.0;
    if (input.has_screenshot)
      evidence_score += 0.2;
    if (input.has_video)
      evidence_score += 0.3;
    if (input.has_poc_steps)
      evidence_score += 0.3;
    evidence_score += input.response_uniqueness * 0.2;

    if (evidence_score >= 0.8) {
      band.evidence_strength = EvidenceLevel::CRITICAL;
      std::strncpy(band.evidence_label, "Critical", 31);
    } else if (evidence_score >= 0.6) {
      band.evidence_strength = EvidenceLevel::HIGH;
      std::strncpy(band.evidence_label, "High", 31);
    } else if (evidence_score >= 0.3) {
      band.evidence_strength = EvidenceLevel::MEDIUM;
      std::strncpy(band.evidence_label, "Medium", 31);
    } else if (evidence_score > 0.0) {
      band.evidence_strength = EvidenceLevel::LOW;
      std::strncpy(band.evidence_label, "Low", 31);
    } else {
      band.evidence_strength = EvidenceLevel::NONE;
      std::strncpy(band.evidence_label, "None", 31);
    }

    // Reproducibility
    band.reproducibility_pct = input.poc_success_rate * 100.0;

    // Business impact certainty
    double impact = input.model_confidence * 0.4 +
                    input.response_uniqueness * 0.3 +
                    input.timing_consistency * 0.3;
    if (impact >= 0.8) {
      band.business_impact = ImpactCertainty::CONFIRMED;
      std::strncpy(band.impact_label, "Confirmed", 31);
    } else if (impact >= 0.6) {
      band.business_impact = ImpactCertainty::HIGH;
      std::strncpy(band.impact_label, "High", 31);
    } else if (impact >= 0.4) {
      band.business_impact = ImpactCertainty::MEDIUM;
      std::strncpy(band.impact_label, "Medium", 31);
    } else if (impact > 0.0) {
      band.business_impact = ImpactCertainty::LOW;
      std::strncpy(band.impact_label, "Low", 31);
    } else {
      band.business_impact = ImpactCertainty::UNVERIFIED;
      std::strncpy(band.impact_label, "Unverified", 31);
    }

    // Duplicate risk
    band.duplicate_risk_pct = input.duplicate_risk;

    // Scope compliance
    band.scope_compliant = input.scope_valid;

    // ALWAYS require human review
    band.human_review_required = true;

    // Summary
    std::snprintf(band.summary, sizeof(band.summary),
                  "Confidence: %.0f%% (%s) | Evidence: %s | "
                  "Reproducibility: %.0f%% | Impact: %s | "
                  "Duplicate Risk: %.0f%% | Scope: %s | "
                  "HUMAN REVIEW REQUIRED",
                  band.confidence_pct, band.confidence_label,
                  band.evidence_label, band.reproducibility_pct,
                  band.impact_label, band.duplicate_risk_pct,
                  band.scope_compliant ? "Valid" : "INVALID");

    return band;
  }

  // --- Self-test ---
  static bool run_tests() {
    ConfidenceScorer scorer;
    int passed = 0, failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (cond) {
        ++passed;
      } else {
        ++failed;
      }
    };

    // Test 1: Strong finding
    ScoringInput strong = {0.97, 0.004, 0.95, 0.90, 0.95, 0.85,
                           0.90, 5.0,   true, true, true, true};
    auto r1 = scorer.score(strong);
    test(r1.confidence_pct >= 85.0, "Strong finding should be high");
    test(r1.human_review_required, "Should always require review");
    test(r1.evidence_strength >= EvidenceLevel::HIGH,
         "Should have high evidence");

    // Test 2: Weak finding
    ScoringInput weak = {0.65, 0.15, 0.50, 0.40,  0.30,  0.20,
                         0.30, 45.0, true, false, false, false};
    auto r2 = scorer.score(weak);
    test(r2.confidence_pct < 50.0, "Weak finding should be low");
    test(r2.human_review_required, "Should always require review");

    // Test 3: Out of scope
    ScoringInput oos = {0.97, 0.004, 0.95,  0.90, 0.95, 0.85,
                        0.90, 5.0,   false, true, true, true};
    auto r3 = scorer.score(oos);
    test(!r3.scope_compliant, "OOS should be marked invalid");

    // Test 4: High duplicate risk
    ScoringInput dup = {0.97, 0.004, 0.95, 0.90, 0.95, 0.85,
                        0.90, 85.0,  true, true, true, true};
    auto r4 = scorer.score(dup);
    test(r4.duplicate_risk_pct >= 80.0, "Should preserve duplicate risk");

    return failed == 0;
  }
};

} // namespace confidence_engine
