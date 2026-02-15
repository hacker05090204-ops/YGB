/**
 * Catastrophic Forgetting Detector — Sequential Expansion Monitor.
 *
 * Simulates 5 sequential representation expansions, each mutating 10%
 * of one feature group. Tracks per-expansion accuracy on frozen
 * validation snapshots to detect catastrophic forgetting.
 *
 * Detection: accuracy drop > 5% on any previous expansion's patterns.
 * Uses ring buffer of last 5 expansion snapshots.
 *
 * GOVERNANCE: No decision labels. Deterministic seeded.
 * Compile: cl /O2 /EHsc /std:c++17 catastrophic_forgetting_detector.cpp
 */
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <deque>
#include <random>
#include <vector>


namespace g38 {
namespace temporal {

static constexpr int MAX_SNAPSHOTS = 5;
static constexpr float ACCURACY_DROP_THRESHOLD = 0.05f;
static constexpr float MUTATION_RATE = 0.10f;

// Per-expansion result
struct ExpansionResult {
  int expansion_id;
  int mutated_group;          // Which group was mutated (0-3)
  float mutation_rate;        // Actual mutation rate applied
  float accuracy_on_current;  // Accuracy on current expansion data
  float accuracy_on_original; // Accuracy on original (frozen) data
  float worst_previous_drop;  // Max accuracy drop on any previous snapshot
  bool forgetting_detected;   // Any drop > 5%
};

// Snapshot of validation data at a point in time
struct ValidationSnapshot {
  int expansion_id;
  std::vector<float> features; // Flattened [N x dim]
  std::vector<int> labels;     // [N]
  int N;
  int dim;
  float baseline_accuracy; // Accuracy when snapshot was taken
};

// ============================================================================
// Catastrophic Forgetting Detector
// ============================================================================

class CatastrophicForgettingDetector {
public:
  explicit CatastrophicForgettingDetector(uint64_t seed = 42)
      : rng_(seed), seed_(seed) {}

  /**
   * Apply a 10% mutation to a specific feature group.
   * Replaces mutation_rate fraction of values in the group with
   * random values drawn from [0, 1].
   */
  void apply_group_mutation(float *features, int N, int dim, int group_idx,
                            float rate = MUTATION_RATE) {
    static const int GSTART[4] = {0, 64, 128, 192};
    static const int GEND[4] = {64, 128, 192, 256};

    int gs = GSTART[group_idx];
    int ge = GEND[group_idx];

    std::uniform_real_distribution<float> uniform(0.0f, 1.0f);
    std::bernoulli_distribution mutate(rate);

    for (int i = 0; i < N; ++i) {
      for (int d = gs; d < ge; ++d) {
        if (mutate(rng_)) {
          features[i * dim + d] = uniform(rng_);
        }
      }
    }
  }

  /**
   * Create a validation snapshot from current data.
   */
  void create_snapshot(const float *features, const int *labels, int N, int dim,
                       int expansion_id, float baseline_accuracy) {
    ValidationSnapshot snap;
    snap.expansion_id = expansion_id;
    snap.features.assign(features, features + N * dim);
    snap.labels.assign(labels, labels + N);
    snap.N = N;
    snap.dim = dim;
    snap.baseline_accuracy = baseline_accuracy;

    snapshots_.push_back(snap);
    if (static_cast<int>(snapshots_.size()) > MAX_SNAPSHOTS) {
      snapshots_.pop_front();
    }
  }

  /**
   * Evaluate accuracy of a simple linear classifier on a snapshot.
   * Uses dot-product similarity with group centroids as a fast proxy.
   *
   * This is a lightweight O(N*D) evaluation without full NN training.
   */
  float evaluate_on_snapshot(const float *current_features,
                             const int *current_labels, int N_current, int dim,
                             const ValidationSnapshot &snap) {
    // Compute class centroids from current data
    std::vector<double> centroid_pos(dim, 0.0);
    std::vector<double> centroid_neg(dim, 0.0);
    int n_pos = 0, n_neg = 0;

    for (int i = 0; i < N_current; ++i) {
      if (current_labels[i] == 1) {
        for (int d = 0; d < dim; ++d)
          centroid_pos[d] += current_features[i * dim + d];
        n_pos++;
      } else {
        for (int d = 0; d < dim; ++d)
          centroid_neg[d] += current_features[i * dim + d];
        n_neg++;
      }
    }
    if (n_pos > 0)
      for (int d = 0; d < dim; ++d)
        centroid_pos[d] /= n_pos;
    if (n_neg > 0)
      for (int d = 0; d < dim; ++d)
        centroid_neg[d] /= n_neg;

    // Classify snapshot data using nearest centroid
    int correct = 0;
    for (int i = 0; i < snap.N; ++i) {
      double dist_pos = 0, dist_neg = 0;
      for (int d = 0; d < dim; ++d) {
        double dp = snap.features[i * dim + d] - centroid_pos[d];
        double dn = snap.features[i * dim + d] - centroid_neg[d];
        dist_pos += dp * dp;
        dist_neg += dn * dn;
      }
      int pred = (dist_pos < dist_neg) ? 1 : 0;
      if (pred == snap.labels[i])
        correct++;
    }
    return static_cast<float>(correct) / snap.N;
  }

  /**
   * Run one expansion step and check for forgetting.
   */
  ExpansionResult run_expansion(float *features, int *labels, int N, int dim,
                                int expansion_id) {
    ExpansionResult result;
    result.expansion_id = expansion_id;
    result.mutated_group = expansion_id % 4;
    result.mutation_rate = MUTATION_RATE;

    // Apply mutation
    apply_group_mutation(features, N, dim, result.mutated_group);

    // Accuracy on current data (self-evaluation via leave-one-out proxy)
    float current_acc = evaluate_self(features, labels, N, dim);
    result.accuracy_on_current = current_acc;

    // Check accuracy on all previous snapshots
    result.worst_previous_drop = 0.0f;
    result.forgetting_detected = false;

    for (const auto &snap : snapshots_) {
      float acc = evaluate_on_snapshot(features, labels, N, dim, snap);
      float drop = snap.baseline_accuracy - acc;
      if (drop > result.worst_previous_drop) {
        result.worst_previous_drop = drop;
      }
      if (drop > ACCURACY_DROP_THRESHOLD) {
        result.forgetting_detected = true;
      }
    }

    // Accuracy on original (first snapshot if available)
    if (!snapshots_.empty()) {
      result.accuracy_on_original =
          evaluate_on_snapshot(features, labels, N, dim, snapshots_.front());
    } else {
      result.accuracy_on_original = current_acc;
    }

    // Save current as snapshot
    create_snapshot(features, labels, N, dim, expansion_id, current_acc);

    return result;
  }

  int snapshot_count() const { return static_cast<int>(snapshots_.size()); }

private:
  /**
   * Quick self-evaluation: nearest centroid accuracy.
   */
  float evaluate_self(const float *features, const int *labels, int N,
                      int dim) {
    // Compute centroids on first half, evaluate on second half
    int half = N / 2;
    std::vector<double> cp(dim, 0), cn(dim, 0);
    int np = 0, nn = 0;
    for (int i = 0; i < half; ++i) {
      if (labels[i] == 1) {
        for (int d = 0; d < dim; ++d)
          cp[d] += features[i * dim + d];
        np++;
      } else {
        for (int d = 0; d < dim; ++d)
          cn[d] += features[i * dim + d];
        nn++;
      }
    }
    if (np > 0)
      for (int d = 0; d < dim; ++d)
        cp[d] /= np;
    if (nn > 0)
      for (int d = 0; d < dim; ++d)
        cn[d] /= nn;

    int correct = 0;
    for (int i = half; i < N; ++i) {
      double dp = 0, dn = 0;
      for (int d = 0; d < dim; ++d) {
        double dpp = features[i * dim + d] - cp[d];
        double dnn = features[i * dim + d] - cn[d];
        dp += dpp * dpp;
        dn += dnn * dnn;
      }
      int pred = (dp < dn) ? 1 : 0;
      if (pred == labels[i])
        correct++;
    }
    return static_cast<float>(correct) / (N - half);
  }

  std::mt19937_64 rng_;
  uint64_t seed_;
  std::deque<ValidationSnapshot> snapshots_;
};

} // namespace temporal
} // namespace g38
