/**
 * Temperature Scaling & Monotonicity Enforcement for Calibration.
 * 
 * Compile: cl /O2 /EHsc /std:c++17 temperature_scaling.cpp
 */
#include <vector>
#include <cmath>
#include <algorithm>
#include <numeric>
#include <cstdint>

namespace g38 {
namespace calibration {

/**
 * Apply temperature scaling to logits.
 * logits: (batch_size, n_classes) flattened
 */
void apply_temperature(float* logits, int batch_size, int n_classes, float temperature) {
    float inv_t = 1.0f / std::max(temperature, 0.01f);
    for (int i = 0; i < batch_size * n_classes; ++i) {
        logits[i] *= inv_t;
    }
}

/**
 * Compute calibration penalty for a minibatch.
 * Returns average (confidence - accuracy) when confidence > accuracy.
 */
float compute_calibration_penalty(
    const float* probs, const int* predictions, const int* labels,
    int batch_size, int n_classes) {
    
    float total_conf = 0.0f;
    float total_correct = 0.0f;
    
    for (int b = 0; b < batch_size; ++b) {
        // Find max prob
        float max_prob = 0.0f;
        for (int c = 0; c < n_classes; ++c) {
            max_prob = std::max(max_prob, probs[b * n_classes + c]);
        }
        total_conf += max_prob;
        total_correct += (predictions[b] == labels[b]) ? 1.0f : 0.0f;
    }
    
    float avg_conf = total_conf / batch_size;
    float avg_acc = total_correct / batch_size;
    
    return std::max(0.0f, avg_conf - avg_acc);
}

/**
 * Compute monotonicity penalty.
 * Bins confidences and checks if accuracy increases with confidence.
 * Returns penalty > 0 if not monotonic.
 */
float compute_monotonicity_penalty(
    const float* confidences, const int* correct, int n, int n_bins) {
    
    std::vector<float> bin_conf(n_bins, 0.0f);
    std::vector<float> bin_acc(n_bins, 0.0f);
    std::vector<int> bin_count(n_bins, 0);
    
    for (int i = 0; i < n; ++i) {
        int bin = std::min(static_cast<int>(confidences[i] * n_bins), n_bins - 1);
        bin_conf[bin] += confidences[i];
        bin_acc[bin] += correct[i];
        bin_count[bin]++;
    }
    
    float penalty = 0.0f;
    float prev_acc = -1.0f;
    
    for (int b = 0; b < n_bins; ++b) {
        if (bin_count[b] < 5) continue;
        float acc = bin_acc[b] / bin_count[b];
        if (prev_acc >= 0.0f && acc < prev_acc) {
            penalty += (prev_acc - acc);  // Non-monotonic drop
        }
        prev_acc = acc;
    }
    
    return penalty;
}

} // namespace calibration
} // namespace g38
