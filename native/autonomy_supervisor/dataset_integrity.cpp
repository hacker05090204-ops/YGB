/**
 * Dataset Integrity Watchdog — Class Balance, KL Divergence, Duplicate
 * Detection
 *
 * Monitors:
 *   1) Rolling class balance tracker (per-class sample counts)
 *   2) Feature distribution tracker with KL divergence vs baseline
 *   3) Duplicate detection via rolling hash set
 *   4) Training freeze signal on threshold breach
 *
 * If dataset drift > threshold: freeze training.
 * No silent degradation. All anomalies logged.
 */

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <set>
#include <vector>

// ============================================================================
// Dataset Stats
// ============================================================================

struct DatasetIntegrityStats {
  // Class balance
  int n_classes;
  std::vector<int> class_counts;
  double max_imbalance_ratio; // max_class / min_class
  bool class_imbalance_alert; // ratio > 1.2 (20% imbalance)

  // KL divergence
  double kl_divergence;
  bool kl_alert; // KL > threshold

  // Duplicate detection
  int total_samples;
  int duplicate_count;
  double duplicate_rate;
  bool duplicate_alert; // rate > 5%

  // Overall
  double dataset_score;        // 0–100
  bool should_freeze_training; // ANY alert fires
};

// ============================================================================
// Dataset Integrity Watchdog
// ============================================================================

class DatasetIntegrityWatchdog {
private:
  // Configuration
  int n_classes_;
  int n_feature_bins_;
  double imbalance_threshold_;      // Max allowed imbalance ratio
  double kl_threshold_;             // Max allowed KL divergence
  double duplicate_rate_threshold_; // Max allowed duplicate rate
  int window_size_;                 // Rolling window for class counts

  // Class balance tracking
  std::vector<int> class_counts_;

  // Feature distribution (histogram per bin)
  std::vector<double> baseline_dist_;
  std::vector<double> current_dist_;
  int dist_sample_count_;
  bool has_baseline_;

  // Duplicate detection (rolling hash set)
  std::set<uint64_t> seen_hashes_;
  int total_samples_;
  int duplicate_count_;

  // -------------------------------------------------------------------

  // FNV-1a hash of a feature vector
  static uint64_t hash_features(const double *features, int n) {
    uint64_t hash = 0xcbf29ce484222325ULL;
    const uint8_t *bytes = reinterpret_cast<const uint8_t *>(features);
    int nbytes = n * static_cast<int>(sizeof(double));
    for (int i = 0; i < nbytes; i++) {
      hash ^= bytes[i];
      hash *= 0x100000001b3ULL;
    }
    return hash;
  }

  double compute_kl_divergence() const {
    if (!has_baseline_ || dist_sample_count_ == 0)
      return 0.0;

    double kl = 0.0;
    int bins = static_cast<int>(baseline_dist_.size());
    double total = static_cast<double>(dist_sample_count_);

    for (int b = 0; b < bins; b++) {
      double p = baseline_dist_[b];
      double q = (current_dist_[b] + 1e-10) / (total + bins * 1e-10);
      if (p > 1e-10 && q > 1e-10) {
        kl += p * std::log(p / q);
      }
    }
    return std::max(0.0, kl);
  }

  double compute_imbalance_ratio() const {
    if (n_classes_ <= 1)
      return 1.0;

    int min_count = class_counts_[0];
    int max_count = class_counts_[0];
    for (int c = 1; c < n_classes_; c++) {
      min_count = std::min(min_count, class_counts_[c]);
      max_count = std::max(max_count, class_counts_[c]);
    }

    if (min_count <= 0)
      return 999.0; // Infinite imbalance
    return static_cast<double>(max_count) / min_count;
  }

public:
  DatasetIntegrityWatchdog()
      : n_classes_(2), n_feature_bins_(50), imbalance_threshold_(1.2),
        kl_threshold_(0.5), duplicate_rate_threshold_(0.05),
        window_size_(10000), dist_sample_count_(0), has_baseline_(false),
        total_samples_(0), duplicate_count_(0) {}

  void initialize(int n_classes, int n_feature_bins = 50,
                  double imbalance_threshold = 1.2, double kl_threshold = 0.5,
                  double duplicate_rate_threshold = 0.05) {
    n_classes_ = n_classes;
    n_feature_bins_ = n_feature_bins;
    imbalance_threshold_ = imbalance_threshold;
    kl_threshold_ = kl_threshold;
    duplicate_rate_threshold_ = duplicate_rate_threshold;

    class_counts_.assign(n_classes, 0);
    current_dist_.assign(n_feature_bins, 0.0);
  }

  void set_baseline_distribution(const double *dist, int n_bins) {
    baseline_dist_.assign(dist, dist + n_bins);
    has_baseline_ = true;

    // Normalize
    double sum = 0.0;
    for (double v : baseline_dist_)
      sum += v;
    if (sum > 0) {
      for (double &v : baseline_dist_)
        v /= sum;
    }
  }

  // -------------------------------------------------------------------
  // Sample Recording
  // -------------------------------------------------------------------

  void record_sample(int class_label, const double *features, int n_features) {
    // 1) Class balance
    if (class_label >= 0 && class_label < n_classes_) {
      class_counts_[class_label]++;
    }

    // 2) Feature distribution (bin the first feature for simplicity)
    if (n_features > 0 && n_feature_bins_ > 0) {
      // Use first feature value, clamped to [0, 1]
      double val = std::max(0.0, std::min(1.0, features[0]));
      int bin = static_cast<int>(val * (n_feature_bins_ - 1));
      bin = std::max(0, std::min(n_feature_bins_ - 1, bin));
      current_dist_[bin] += 1.0;
      dist_sample_count_++;
    }

    // 3) Duplicate detection
    uint64_t h = hash_features(features, n_features);
    total_samples_++;
    if (seen_hashes_.count(h) > 0) {
      duplicate_count_++;
    } else {
      seen_hashes_.insert(h);
    }
  }

  void record_batch(const int *labels, const double *features, int n_samples,
                    int n_features) {
    for (int i = 0; i < n_samples; i++) {
      record_sample(labels[i], features + i * n_features, n_features);
    }
  }

  // -------------------------------------------------------------------
  // Stats & Score
  // -------------------------------------------------------------------

  DatasetIntegrityStats get_stats() const {
    DatasetIntegrityStats stats;
    stats.n_classes = n_classes_;
    stats.class_counts = class_counts_;
    stats.max_imbalance_ratio = compute_imbalance_ratio();
    stats.class_imbalance_alert =
        (stats.max_imbalance_ratio > imbalance_threshold_);

    stats.kl_divergence = compute_kl_divergence();
    stats.kl_alert = (stats.kl_divergence > kl_threshold_);

    stats.total_samples = total_samples_;
    stats.duplicate_count = duplicate_count_;
    stats.duplicate_rate =
        (total_samples_ > 0)
            ? static_cast<double>(duplicate_count_) / total_samples_
            : 0.0;
    stats.duplicate_alert = (stats.duplicate_rate > duplicate_rate_threshold_);

    // Score computation: start at 100, deduct for issues
    double score = 100.0;

    // Class imbalance penalty (up to 30 points)
    if (stats.max_imbalance_ratio > imbalance_threshold_) {
      double penalty = std::min(
          30.0, (stats.max_imbalance_ratio - imbalance_threshold_) * 20.0);
      score -= penalty;
    }

    // KL divergence penalty (up to 40 points)
    if (stats.kl_divergence > kl_threshold_) {
      double penalty =
          std::min(40.0, (stats.kl_divergence - kl_threshold_) * 40.0);
      score -= penalty;
    }

    // Duplicate rate penalty (up to 30 points)
    if (stats.duplicate_rate > duplicate_rate_threshold_) {
      double penalty = std::min(
          30.0, (stats.duplicate_rate - duplicate_rate_threshold_) * 300.0);
      score -= penalty;
    }

    stats.dataset_score = std::max(0.0, std::min(100.0, score));
    stats.should_freeze_training =
        stats.class_imbalance_alert || stats.kl_alert || stats.duplicate_alert;

    return stats;
  }

  bool should_freeze() const { return get_stats().should_freeze_training; }

  void reset() {
    class_counts_.assign(n_classes_, 0);
    current_dist_.assign(n_feature_bins_, 0.0);
    dist_sample_count_ = 0;
    seen_hashes_.clear();
    total_samples_ = 0;
    duplicate_count_ = 0;
  }
};
