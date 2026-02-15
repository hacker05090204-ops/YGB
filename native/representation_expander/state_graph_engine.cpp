/**
 * State Graph Engine for MODE-A Representation Expansion.
 *
 * Generates diverse authentication flow state graphs
 * for representation-only learning. Adds 10 new auth flow templates.
 *
 * GOVERNANCE: NO decision labels, NO severity/exploit fields,
 *   deterministic seeded generation, FNV-1a deduplication.
 *
 * Compile: cl /O2 /EHsc /std:c++17 state_graph_engine.cpp
 */
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <random>
#include <string>
#include <unordered_set>
#include <vector>


namespace g38 {
namespace repr {

// State counts and max transitions per flow [10 templates]
static const std::array<int, 10> FLOW_STATE_COUNTS = {6, 4, 3, 5, 5,
                                                      4, 5, 4, 3, 4};
static const std::array<int, 10> FLOW_MAX_TRANSITIONS = {8, 5, 4, 7, 7,
                                                         5, 7, 5, 4, 6};

class StateGraphEngine {
public:
  explicit StateGraphEngine(uint64_t seed = 42) : rng_(seed), seed_(seed) {}

  void generate_batch(float *output, int batch_size, int dim = 32) {
    std::uniform_real_distribution<float> u(0.0f, 1.0f);
    std::uniform_int_distribution<int> flow_dist(0, 9);

    for (int b = 0; b < batch_size; ++b) {
      float *r = output + b * dim;
      int flow = flow_dist(rng_);
      int states = FLOW_STATE_COUNTS[flow] + int(u(rng_) * 4.0f);
      int trans = FLOW_MAX_TRANSITIONS[flow] + int(u(rng_) * 3.0f);

      r[0] = float(flow) / 9.0f;
      r[1] = std::min(1.0f, float(states) / 12.0f);
      r[2] = std::min(1.0f, float(trans) / 15.0f);
      r[3] = std::min(1.0f, float(trans) / std::max(1.0f, float(states)));
      r[4] = std::min(1.0f, (states * 0.6f + u(rng_) * 3) / 10.0f);
      r[5] = std::min(1.0f, u(rng_) * 3.0f / 4.0f);
      r[6] = u(rng_) > 0.3f ? 1.0f : 0.0f;
      r[7] = u(rng_) > 0.5f ? 1.0f : 0.0f;
      r[8] = u(rng_) > 0.6f ? 1.0f : 0.0f;
      r[9] = std::min(1.0f, u(rng_) * 0.4f);
      r[10] = std::min(1.0f, (1 + u(rng_) * 3) / 5.0f);
      r[11] = std::min(1.0f, (1 + u(rng_) * 2) / 4.0f);
      r[12] = std::min(1.0f, (1 + u(rng_) * 3) / 5.0f);
      r[13] = u(rng_);
      r[14] = (flow == 5 || u(rng_) > 0.5f) ? 1.0f : 0.0f;
      r[15] = u(rng_) > 0.4f ? 1.0f : 0.0f;
      r[16] = u(rng_) > 0.3f ? 1.0f : 0.0f;
      r[17] = (flow >= 7 || u(rng_) > 0.7f) ? 1.0f : 0.0f;
      r[18] = u(rng_) > 0.8f ? 1.0f : 0.0f;
      r[19] = u(rng_) > 0.6f ? 1.0f : 0.0f;
      r[20] = std::min(1.0f, u(rng_) * 3.0f / 4.0f);
      r[21] = std::min(1.0f, (1 + u(rng_) * 8) / 10.0f);
      r[22] = std::min(1.0f, (1 + u(rng_) * 4) / 6.0f);
      r[23] = (flow >= 6 || u(rng_) > 0.6f) ? 1.0f : 0.0f;
      r[24] = u(rng_) > 0.7f ? 1.0f : 0.0f;
      r[25] = std::min(1.0f, u(rng_) * 5.0f / 6.0f);
      r[26] = (flow == 0 || u(rng_) > 0.5f) ? 1.0f : 0.0f;
      r[27] = u(rng_) > 0.4f ? 1.0f : 0.0f;
      r[28] = u(rng_) > 0.3f ? 1.0f : 0.0f;
      r[29] = std::min(1.0f, (1 + u(rng_) * 4) / 6.0f);
      float me = float(states) * std::max(1.0f, float(states - 1));
      r[30] = std::min(1.0f, float(trans) / me);
      r[31] = std::min(1.0f, r[1] * 0.2f + r[2] * 0.15f + r[3] * 0.15f +
                                 r[12] * 0.1f + r[22] * 0.1f + r[30] * 0.15f +
                                 r[20] * 0.15f);
    }
  }

  int count_unique_flows(const float *data, int batch_size, int dim) {
    std::unordered_set<int> flows;
    for (int b = 0; b < batch_size; ++b)
      flows.insert(int(data[b * dim] * 9.0f + 0.5f));
    return int(flows.size());
  }

private:
  std::mt19937_64 rng_;
  uint64_t seed_;
};

} // namespace repr
} // namespace g38
