/**
 * gradient_accumulator.cpp — Gradient Accumulation Engine
 *
 * When VRAM is limited (RTX 2050/3050), accumulate gradients over
 * multiple micro-batches to simulate larger effective batch sizes.
 * Deterministic accumulation with loss scaling.
 *
 * NO cross-field contamination. Same field only.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace performance {

// =========================================================================
// ACCUMULATOR CONFIG
// =========================================================================

struct AccumulatorConfig {
  uint32_t accumulation_steps; // how many micro-batches before update
  uint32_t micro_batch_size;   // per-step batch size
  double loss_scale;           // for mixed precision stability
  bool deterministic;          // enforce determinism
  uint32_t seed;
};

static AccumulatorConfig default_accumulator(uint32_t vram_mb) {
  AccumulatorConfig c;
  if (vram_mb <= 4096) {
    c.accumulation_steps = 8;
    c.micro_batch_size = 16;
  } else if (vram_mb <= 8192) {
    c.accumulation_steps = 4;
    c.micro_batch_size = 32;
  } else {
    c.accumulation_steps = 2;
    c.micro_batch_size = 64;
  }
  c.loss_scale = 1024.0;
  c.deterministic = true;
  c.seed = 42;
  return c;
}

// =========================================================================
// ACCUMULATION STATE
// =========================================================================

struct AccumulationState {
  uint32_t current_step; // 0 .. accumulation_steps-1
  double accumulated_loss;
  double accumulated_grad_norm;
  uint32_t effective_batch_size;
  bool ready_to_update; // true when current_step == steps
  uint32_t total_updates;
  uint32_t overflow_count;
};

// =========================================================================
// GRADIENT ACCUMULATOR
// =========================================================================

class GradientAccumulator {
public:
  explicit GradientAccumulator(AccumulatorConfig config) : config_(config) {
    std::memset(&state_, 0, sizeof(state_));
  }

  // Step: accumulate one micro-batch
  AccumulationState step(double micro_loss, double grad_norm) {
    state_.accumulated_loss += micro_loss / config_.accumulation_steps;
    state_.accumulated_grad_norm += grad_norm;
    state_.current_step++;

    state_.effective_batch_size =
        config_.micro_batch_size * config_.accumulation_steps;

    // Check for overflow (mixed precision)
    if (grad_norm > 1e6 || std::isnan(grad_norm) || std::isinf(grad_norm)) {
      state_.overflow_count++;
      // Skip this accumulation cycle
      reset_cycle();
      state_.ready_to_update = false;
      return state_;
    }

    if (state_.current_step >= config_.accumulation_steps) {
      state_.ready_to_update = true;
      // Normalize accumulated gradient
      state_.accumulated_grad_norm /= config_.accumulation_steps;
    } else {
      state_.ready_to_update = false;
    }

    return state_;
  }

  // After update, reset for next cycle
  void reset_cycle() {
    if (state_.ready_to_update)
      state_.total_updates++;
    state_.current_step = 0;
    state_.accumulated_loss = 0.0;
    state_.accumulated_grad_norm = 0.0;
    state_.ready_to_update = false;
  }

  const AccumulatorConfig &config() const { return config_; }
  const AccumulationState &state() const { return state_; }

private:
  AccumulatorConfig config_;
  AccumulationState state_;
};

} // namespace performance
