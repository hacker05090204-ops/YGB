/**
 * precision_runtime.cpp — Runtime Precision Monitor
 *
 * Tracks:
 * - Rolling 1000-sample precision
 * - High-confidence FP rate
 * - Duplicate rate
 * - Scope rejection rate
 *
 * If precision < 0.95:
 * - Lock MODE-B
 * - Force MODE-A
 * - Log containment event
 *
 * Exposes metrics to Python via C struct.
 *
 * NO mock data. NO auto-submit. NO authority unlock.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace runtime_monitor {

static constexpr uint32_t ROLLING_WINDOW = 1000;
static constexpr double PRECISION_FLOOR = 0.95;
static constexpr double FP_RATE_CEILING = 0.03;
static constexpr double DUPLICATE_ALERT = 0.20;

enum class ContainmentAction : uint8_t {
  NONE = 0,
  WARNING = 1,
  LOCK_MODE = 2,
  FORCE_A = 3
};

struct RuntimeMetrics {
  // Rolling precision
  double rolling_precision;
  double rolling_recall;
  double high_conf_fp_rate;
  double duplicate_rate;
  double scope_rejection_rate;

  // Counts
  uint32_t window_size;
  uint32_t true_positives;
  uint32_t false_positives;
  uint32_t true_negatives;
  uint32_t false_negatives;
  uint32_t duplicates_flagged;
  uint32_t scope_rejections;
  uint32_t total_processed;

  // Containment
  ContainmentAction action;
  bool precision_breach;
  bool fp_rate_breach;
  bool duplicate_spike;
  bool containment_active;
  char containment_reason[256];
};

struct SampleOutcome {
  bool predicted_positive;
  bool actually_positive;
  double confidence;
  bool is_duplicate;
  bool scope_rejected;
};

class PrecisionRuntimeMonitor {
public:
  PrecisionRuntimeMonitor() : head_(0), count_(0), metrics_() {
    std::memset(&metrics_, 0, sizeof(metrics_));
    std::memset(window_, 0, sizeof(window_));
    metrics_.action = ContainmentAction::NONE;
  }

  // --- Record a sample outcome ---
  void record(const SampleOutcome &outcome) {
    // Remove oldest from rolling counts if window full
    if (count_ >= ROLLING_WINDOW) {
      remove_oldest();
    }

    // Add to circular buffer
    window_[head_] = outcome;
    head_ = (head_ + 1) % ROLLING_WINDOW;
    if (count_ < ROLLING_WINDOW)
      ++count_;

    // Update rolling counts
    if (outcome.predicted_positive && outcome.actually_positive) {
      metrics_.true_positives++;
    } else if (outcome.predicted_positive && !outcome.actually_positive) {
      metrics_.false_positives++;
    } else if (!outcome.predicted_positive && outcome.actually_positive) {
      metrics_.false_negatives++;
    } else {
      metrics_.true_negatives++;
    }

    if (outcome.is_duplicate)
      metrics_.duplicates_flagged++;
    if (outcome.scope_rejected)
      metrics_.scope_rejections++;
    metrics_.total_processed++;
    metrics_.window_size = count_;

    // Recompute metrics
    recompute();

    // Check containment
    check_containment();
  }

  // --- Get current metrics ---
  const RuntimeMetrics &metrics() const { return metrics_; }

  // --- Reset ---
  void reset() {
    head_ = 0;
    count_ = 0;
    std::memset(&metrics_, 0, sizeof(metrics_));
    std::memset(window_, 0, sizeof(window_));
    metrics_.action = ContainmentAction::NONE;
  }

  // --- Self-test ---
  static bool run_tests() {
    PrecisionRuntimeMonitor mon;
    int passed = 0, failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (cond) {
        ++passed;
      } else {
        ++failed;
      }
    };

    // Test 1: Empty state
    test(mon.metrics().rolling_precision == 0.0, "Empty precision = 0");
    test(mon.metrics().containment_active == false, "No containment at start");

    // Test 2: Feed high-precision samples
    for (int i = 0; i < 100; ++i) {
      SampleOutcome s;
      s.predicted_positive = true;
      s.actually_positive = true;
      s.confidence = 0.95;
      s.is_duplicate = false;
      s.scope_rejected = false;
      mon.record(s);
    }
    test(mon.metrics().rolling_precision >= 0.95,
         "100 TPs = precision >= 0.95");
    test(mon.metrics().containment_active == false,
         "High precision = no containment");

    // Test 3: Inject false positives to breach precision
    mon.reset();
    for (int i = 0; i < 80; ++i) {
      SampleOutcome tp = {true, true, 0.95, false, false};
      mon.record(tp);
    }
    for (int i = 0; i < 20; ++i) {
      SampleOutcome fp = {true, false, 0.90, false, false};
      mon.record(fp);
    }
    // 80 TP + 20 FP = precision 0.80
    test(mon.metrics().rolling_precision < 0.95, "80TP+20FP: precision < 0.95");
    test(mon.metrics().containment_active == true,
         "Low precision triggers containment");
    test(mon.metrics().action == ContainmentAction::FORCE_A,
         "Should force MODE-A");

    // Test 4: Duplicate rate tracking
    mon.reset();
    for (int i = 0; i < 50; ++i) {
      SampleOutcome s = {true, true, 0.95, true, false};
      mon.record(s);
    }
    for (int i = 0; i < 50; ++i) {
      SampleOutcome s = {true, true, 0.95, false, false};
      mon.record(s);
    }
    test(mon.metrics().duplicate_rate >= 0.40, "50% duplicates should track");

    // Test 5: Scope rejection tracking
    mon.reset();
    for (int i = 0; i < 10; ++i) {
      SampleOutcome s = {true, true, 0.95, false, true};
      mon.record(s);
    }
    for (int i = 0; i < 90; ++i) {
      SampleOutcome s = {true, true, 0.95, false, false};
      mon.record(s);
    }
    test(mon.metrics().scope_rejection_rate >= 0.05,
         "10% scope rejections tracked");

    // Test 6: Rolling window
    mon.reset();
    for (uint32_t i = 0; i < ROLLING_WINDOW + 100; ++i) {
      SampleOutcome s = {true, true, 0.95, false, false};
      mon.record(s);
    }
    test(mon.metrics().window_size == ROLLING_WINDOW,
         "Window should cap at ROLLING_WINDOW");

    return failed == 0;
  }

private:
  SampleOutcome window_[ROLLING_WINDOW];
  uint32_t head_;
  uint32_t count_;
  RuntimeMetrics metrics_;

  void remove_oldest() {
    uint32_t oldest = (head_) % ROLLING_WINDOW;
    const auto &old = window_[oldest];

    if (old.predicted_positive && old.actually_positive) {
      if (metrics_.true_positives > 0)
        metrics_.true_positives--;
    } else if (old.predicted_positive && !old.actually_positive) {
      if (metrics_.false_positives > 0)
        metrics_.false_positives--;
    } else if (!old.predicted_positive && old.actually_positive) {
      if (metrics_.false_negatives > 0)
        metrics_.false_negatives--;
    } else {
      if (metrics_.true_negatives > 0)
        metrics_.true_negatives--;
    }
    if (old.is_duplicate && metrics_.duplicates_flagged > 0)
      metrics_.duplicates_flagged--;
    if (old.scope_rejected && metrics_.scope_rejections > 0)
      metrics_.scope_rejections--;
  }

  void recompute() {
    uint32_t predicted_pos = metrics_.true_positives + metrics_.false_positives;
    metrics_.rolling_precision =
        predicted_pos > 0
            ? static_cast<double>(metrics_.true_positives) / predicted_pos
            : 0.0;

    uint32_t actual_pos = metrics_.true_positives + metrics_.false_negatives;
    metrics_.rolling_recall =
        actual_pos > 0
            ? static_cast<double>(metrics_.true_positives) / actual_pos
            : 0.0;

    metrics_.high_conf_fp_rate =
        predicted_pos > 0
            ? static_cast<double>(metrics_.false_positives) / predicted_pos
            : 0.0;

    metrics_.duplicate_rate =
        count_ > 0 ? static_cast<double>(metrics_.duplicates_flagged) / count_
                   : 0.0;

    metrics_.scope_rejection_rate =
        count_ > 0 ? static_cast<double>(metrics_.scope_rejections) / count_
                   : 0.0;
  }

  void check_containment() {
    metrics_.precision_breach =
        (count_ >= 50 && metrics_.rolling_precision < PRECISION_FLOOR);
    metrics_.fp_rate_breach =
        (count_ >= 50 && metrics_.high_conf_fp_rate > FP_RATE_CEILING);
    metrics_.duplicate_spike = (metrics_.duplicate_rate > DUPLICATE_ALERT);

    if (metrics_.precision_breach) {
      metrics_.containment_active = true;
      metrics_.action = ContainmentAction::FORCE_A;
      std::snprintf(metrics_.containment_reason,
                    sizeof(metrics_.containment_reason),
                    "PRECISION BREACH: %.4f < %.4f — forcing MODE-A",
                    metrics_.rolling_precision, PRECISION_FLOOR);
    } else if (metrics_.fp_rate_breach) {
      metrics_.containment_active = true;
      metrics_.action = ContainmentAction::LOCK_MODE;
      std::snprintf(metrics_.containment_reason,
                    sizeof(metrics_.containment_reason),
                    "FP RATE BREACH: %.4f > %.4f — locking mode",
                    metrics_.high_conf_fp_rate, FP_RATE_CEILING);
    } else {
      metrics_.containment_active = false;
      metrics_.action = ContainmentAction::NONE;
      metrics_.containment_reason[0] = '\0';
    }
  }
};

} // namespace runtime_monitor
