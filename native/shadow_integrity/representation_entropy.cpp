/**
 * Representation Entropy Monitor — Per-Class Entropy Tracking
 *
 * Monitors Shannon entropy of confidence distributions per class.
 * Alerts if entropy collapses >10% from baseline — indicates
 * representation collapse (model becoming degenerate).
 *
 * Collapse detection prevents silent degradation of model diversity.
 */

#include <algorithm>
#include <cmath>
#include <vector>

struct EntropyStats {
  std::vector<double> class_entropy;      // Shannon entropy per class
  std::vector<double> baseline_entropy;   // Baseline from gate pass
  std::vector<double> entropy_change_pct; // % change from baseline
  double overall_entropy;
  double max_collapse_pct; // Worst-case collapse
  bool alert;              // True if collapse > threshold
  int n_classes;
  int n_samples;
};

class RepresentationEntropyMonitor {
private:
  int n_classes_;
  int n_bins_;
  double collapse_threshold_; // Default 0.10 (10%)

  // Per-class confidence histograms
  std::vector<std::vector<int>> class_histograms_;
  std::vector<int> class_counts_;

  // Baseline entropy
  std::vector<double> baseline_entropy_;
  bool has_baseline_;

  double compute_histogram_entropy(const std::vector<int> &histogram,
                                   int total) const {
    if (total <= 0)
      return 0.0;
    double entropy = 0.0;
    for (int b = 0; b < n_bins_; b++) {
      if (histogram[b] > 0) {
        double p = static_cast<double>(histogram[b]) / total;
        entropy -= p * std::log2(p);
      }
    }
    return entropy;
  }

public:
  RepresentationEntropyMonitor()
      : n_classes_(2), n_bins_(50), collapse_threshold_(0.10),
        has_baseline_(false) {}

  void initialize(int n_classes, int n_bins = 50,
                  double collapse_threshold = 0.10) {
    n_classes_ = n_classes;
    n_bins_ = n_bins;
    collapse_threshold_ = collapse_threshold;
    class_histograms_.assign(n_classes, std::vector<int>(n_bins, 0));
    class_counts_.assign(n_classes, 0);
    has_baseline_ = false;
  }

  void set_baseline(const double *baseline_entropy, int n_classes) {
    baseline_entropy_.assign(baseline_entropy, baseline_entropy + n_classes);
    has_baseline_ = true;
  }

  void record_prediction(int predicted_class, double confidence) {
    if (predicted_class < 0 || predicted_class >= n_classes_)
      return;

    // Bin the confidence [0, 1] into n_bins_ bins
    int bin = static_cast<int>(confidence * (n_bins_ - 1));
    bin = std::max(0, std::min(n_bins_ - 1, bin));

    class_histograms_[predicted_class][bin]++;
    class_counts_[predicted_class]++;
  }

  void record_batch(const int *predictions, const double *confidences, int n) {
    for (int i = 0; i < n; i++) {
      record_prediction(predictions[i], confidences[i]);
    }
  }

  EntropyStats get_stats() const {
    EntropyStats stats;
    stats.n_classes = n_classes_;
    stats.n_samples = 0;
    stats.overall_entropy = 0.0;
    stats.max_collapse_pct = 0.0;
    stats.alert = false;

    stats.class_entropy.resize(n_classes_);
    stats.entropy_change_pct.resize(n_classes_, 0.0);

    for (int c = 0; c < n_classes_; c++) {
      stats.n_samples += class_counts_[c];
      stats.class_entropy[c] =
          compute_histogram_entropy(class_histograms_[c], class_counts_[c]);
    }

    // Overall entropy (weighted by class count)
    int total = stats.n_samples;
    if (total > 0) {
      for (int c = 0; c < n_classes_; c++) {
        double weight = static_cast<double>(class_counts_[c]) / total;
        stats.overall_entropy += weight * stats.class_entropy[c];
      }
    }

    // Check for collapse
    if (has_baseline_) {
      stats.baseline_entropy = baseline_entropy_;
      for (int c = 0; c < n_classes_; c++) {
        double base = std::max(baseline_entropy_[c], 1e-10);
        double change = (base - stats.class_entropy[c]) / base;
        stats.entropy_change_pct[c] = change;
        if (change > stats.max_collapse_pct)
          stats.max_collapse_pct = change;
      }
      stats.alert = (stats.max_collapse_pct > collapse_threshold_);
    }

    return stats;
  }

  void reset() {
    for (auto &h : class_histograms_)
      std::fill(h.begin(), h.end(), 0);
    std::fill(class_counts_.begin(), class_counts_.end(), 0);
  }

  bool is_alert() const { return get_stats().alert; }
};
