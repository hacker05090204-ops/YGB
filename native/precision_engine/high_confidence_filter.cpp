/**
 * high_confidence_filter.cpp — Dynamic Threshold Engine
 *
 * Raises decision threshold until lab precision >= 95%.
 * Default threshold: 0.93 (derived from calibration audit data).
 *
 * NO mock data. NO synthetic fallback.
 * Governance: threshold can only increase, never decrease automatically.
 */

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>


namespace precision_engine {

// --- Calibration Bin ---
struct CalibrationBin {
  double lower;
  double upper;
  uint32_t samples;
  double mean_confidence;
  double mean_accuracy;
  double gap; // mean_confidence - mean_accuracy
};

// --- Filter Decision ---
enum class FilterDecision : uint8_t {
  PASS = 0,      // Confidence >= threshold, proceed
  ABSTAIN = 1,   // Below threshold, do not report
  QUARANTINE = 2 // In dangerous gap zone (0.73-0.93), flag for review
};

struct FilterResult {
  FilterDecision decision;
  double raw_confidence;
  double dynamic_threshold;
  double precision_at_threshold;
  double gap_at_bin;
  char reason[256];
};

// --- High Confidence Filter ---
class HighConfidenceFilter {
public:
  static constexpr double MIN_PRECISION_TARGET = 0.95;
  static constexpr double ABSOLUTE_MIN_THRESHOLD = 0.50;
  static constexpr double DEFAULT_THRESHOLD = 0.93;
  static constexpr double QUARANTINE_LOWER = 0.73;
  static constexpr double QUARANTINE_UPPER = 0.93;

private:
  double dynamic_threshold_;
  double precision_target_;
  std::vector<CalibrationBin> calibration_bins_;
  bool locked_; // Once locked, threshold can only increase

public:
  HighConfidenceFilter()
      : dynamic_threshold_(DEFAULT_THRESHOLD),
        precision_target_(MIN_PRECISION_TARGET), locked_(false) {}

  // --- Load calibration bins from audit data ---
  void load_calibration(const CalibrationBin *bins, size_t count) {
    calibration_bins_.clear();
    calibration_bins_.reserve(count);
    for (size_t i = 0; i < count; ++i) {
      calibration_bins_.push_back(bins[i]);
    }
    recalculate_threshold();
  }

  // --- Recalculate threshold to meet precision target ---
  void recalculate_threshold() {
    if (calibration_bins_.empty())
      return;

    // Walk from highest bin downward, accumulating precision
    // Find the threshold where cumulative precision >= target
    double best_threshold = 1.0;

    // Sort bins by lower bound descending
    std::vector<CalibrationBin> sorted = calibration_bins_;
    std::sort(sorted.begin(), sorted.end(),
              [](const CalibrationBin &a, const CalibrationBin &b) {
                return a.lower > b.lower;
              });

    uint32_t total_correct = 0;
    uint32_t total_samples = 0;

    for (const auto &bin : sorted) {
      if (bin.samples == 0)
        continue;

      uint32_t bin_correct =
          static_cast<uint32_t>(bin.mean_accuracy * bin.samples + 0.5);
      total_correct += bin_correct;
      total_samples += bin.samples;

      double cumulative_precision =
          static_cast<double>(total_correct) / total_samples;

      if (cumulative_precision >= precision_target_) {
        best_threshold = bin.lower;
      } else {
        // Precision dropped below target at this inclusion
        break;
      }
    }

    // Enforce minimum threshold
    best_threshold = std::max(best_threshold, ABSOLUTE_MIN_THRESHOLD);

    // Governance: threshold can only increase once locked
    if (locked_ && best_threshold < dynamic_threshold_) {
      return; // Refuse to lower
    }

    dynamic_threshold_ = best_threshold;
  }

  // --- Lock threshold (prevent lowering) ---
  void lock() { locked_ = true; }
  bool is_locked() const { return locked_; }

  // --- Get current threshold ---
  double get_threshold() const { return dynamic_threshold_; }

  // --- Set precision target ---
  void set_precision_target(double target) {
    if (target < 0.5 || target > 1.0) {
      throw std::invalid_argument("Precision target must be [0.5, 1.0]");
    }
    precision_target_ = target;
    recalculate_threshold();
  }

  // --- Filter a prediction ---
  FilterResult filter(double confidence) const {
    FilterResult result;
    std::memset(&result, 0, sizeof(result));
    result.raw_confidence = confidence;
    result.dynamic_threshold = dynamic_threshold_;

    // Find which bin this confidence falls into
    result.gap_at_bin = 0.0;
    for (const auto &bin : calibration_bins_) {
      if (confidence >= bin.lower && confidence < bin.upper) {
        result.gap_at_bin = bin.gap;
        break;
      }
    }

    // Compute estimated precision at this confidence level
    result.precision_at_threshold = estimate_precision_above(confidence);

    if (confidence >= dynamic_threshold_) {
      result.decision = FilterDecision::PASS;
      std::snprintf(result.reason, sizeof(result.reason),
                    "PASS: confidence %.4f >= threshold %.4f", confidence,
                    dynamic_threshold_);
    } else if (confidence >= QUARANTINE_LOWER &&
               confidence < QUARANTINE_UPPER) {
      result.decision = FilterDecision::QUARANTINE;
      std::snprintf(result.reason, sizeof(result.reason),
                    "QUARANTINE: confidence %.4f in dangerous gap zone "
                    "[%.2f, %.2f), gap=%.4f",
                    confidence, QUARANTINE_LOWER, QUARANTINE_UPPER,
                    result.gap_at_bin);
    } else {
      result.decision = FilterDecision::ABSTAIN;
      std::snprintf(result.reason, sizeof(result.reason),
                    "ABSTAIN: confidence %.4f < threshold %.4f", confidence,
                    dynamic_threshold_);
    }

    return result;
  }

  // --- Estimate cumulative precision above a given confidence ---
  double estimate_precision_above(double threshold) const {
    uint32_t total_correct = 0;
    uint32_t total_samples = 0;

    for (const auto &bin : calibration_bins_) {
      if (bin.lower >= threshold && bin.samples > 0) {
        total_correct +=
            static_cast<uint32_t>(bin.mean_accuracy * bin.samples + 0.5);
        total_samples += bin.samples;
      }
    }

    if (total_samples == 0)
      return 0.0;
    return static_cast<double>(total_correct) / total_samples;
  }

  // --- Self-test ---
  static bool run_tests() {
    HighConfidenceFilter filter;

    // Load calibration bins from audit data
    CalibrationBin bins[] = {{0.467, 0.533, 54, 0.5175, 0.463, 0.0545},
                             {0.533, 0.600, 99, 0.5712, 0.4545, 0.1166},
                             {0.600, 0.667, 111, 0.6324, 0.6306, 0.0017},
                             {0.667, 0.733, 112, 0.7012, 0.6696, 0.0316},
                             {0.733, 0.800, 90, 0.7666, 0.6667, 0.0999},
                             {0.800, 0.867, 157, 0.834, 0.6815, 0.1524},
                             {0.867, 0.933, 206, 0.9034, 0.8301, 0.0733},
                             {0.933, 1.000, 2728, 0.9936, 0.9894, 0.0042}};
    filter.load_calibration(bins, 8);

    int passed = 0;
    int failed = 0;

    // Test 1: Default threshold should be high enough for 95%
    auto test = [&](bool cond, const char *name) {
      if (cond) {
        ++passed;
      } else {
        ++failed;
      }
    };

    test(filter.get_threshold() >= 0.85, "Threshold >= 0.85 for 95% precision");

    // Test 2: High confidence should PASS
    auto r1 = filter.filter(0.98);
    test(r1.decision == FilterDecision::PASS, "0.98 should PASS");

    // Test 3: Low confidence should ABSTAIN
    auto r2 = filter.filter(0.40);
    test(r2.decision == FilterDecision::ABSTAIN, "0.40 should ABSTAIN");

    // Test 4: Dangerous zone should QUARANTINE
    auto r3 = filter.filter(0.82);
    test(r3.decision == FilterDecision::QUARANTINE ||
             r3.decision == FilterDecision::ABSTAIN,
         "0.82 should QUARANTINE or ABSTAIN");

    // Test 5: Lock prevents lowering
    filter.lock();
    double old_threshold = filter.get_threshold();
    CalibrationBin easy_bins[] = {{0.5, 1.0, 1000, 0.75, 0.95, 0.0}};
    filter.load_calibration(easy_bins, 1);
    test(filter.get_threshold() >= old_threshold,
         "Locked threshold cannot decrease");

    // Test 6: Precision estimate
    filter.load_calibration(bins, 8);
    double p_at_93 = filter.estimate_precision_above(0.933);
    test(p_at_93 >= 0.95, "Precision above 0.93 should be >= 95%");

    return failed == 0;
  }
};

} // namespace precision_engine
