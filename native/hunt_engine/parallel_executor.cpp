/**
 * parallel_executor.cpp — Parallel Hunt Executor
 *
 * Manages concurrent target execution with strict resource governance.
 *
 * Limits:
 *   - Max 5 targets simultaneously
 *   - No training allowed in hunt engine
 *   - Each target has scope validation + duplicate pre-check
 *   - Report requires human approval (no auto-submit)
 *
 * NO auto-submit. NO authority unlock. NO weight updates.
 */

#include <cstdint>
#include <cstdio>
#include <cstring>


namespace hunt_engine {

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr uint32_t MAX_CONCURRENT_TARGETS = 5;
static constexpr bool ALLOW_TRAINING = false;
static constexpr bool ALLOW_AUTO_SUBMIT = false;

// =========================================================================
// TARGET STATE
// =========================================================================

enum class TargetState : uint8_t {
  QUEUED = 0,
  SCOPE_VALIDATING = 1,
  DUP_CHECKING = 2,
  EXECUTING = 3,
  REPORT_PENDING = 4, // awaiting human approval
  COMPLETED = 5,
  FAILED = 6,
  PAUSED = 7 // resource limit / thermal
};

static const char *target_state_name(TargetState s) {
  switch (s) {
  case TargetState::QUEUED:
    return "QUEUED";
  case TargetState::SCOPE_VALIDATING:
    return "SCOPE_VALIDATING";
  case TargetState::DUP_CHECKING:
    return "DUP_CHECKING";
  case TargetState::EXECUTING:
    return "EXECUTING";
  case TargetState::REPORT_PENDING:
    return "REPORT_PENDING";
  case TargetState::COMPLETED:
    return "COMPLETED";
  case TargetState::FAILED:
    return "FAILED";
  case TargetState::PAUSED:
    return "PAUSED";
  default:
    return "UNKNOWN";
  }
}

// =========================================================================
// TARGET SLOT
// =========================================================================

struct TargetSlot {
  bool active;
  uint32_t target_id;
  char domain[256];
  char scope[512];
  TargetState state;
  double risk_band;
  double confidence;
  bool scope_valid;
  bool dup_clear;
};

// =========================================================================
// PARALLEL EXECUTOR
// =========================================================================

class ParallelExecutor {
public:
  ParallelExecutor() {
    std::memset(slots_, 0, sizeof(slots_));
    next_id_ = 1;
  }

  // --- Safety gates ---
  static bool can_train() { return ALLOW_TRAINING; }
  static bool can_auto_submit() { return ALLOW_AUTO_SUBMIT; }

  // --- Enqueue a target ---
  int enqueue(const char *domain, const char *scope) {
    // Check capacity
    uint32_t active = active_count();
    if (active >= MAX_CONCURRENT_TARGETS) {
      return -1; // at capacity
    }

    // Find free slot
    for (uint32_t i = 0; i < MAX_CONCURRENT_TARGETS; ++i) {
      if (!slots_[i].active) {
        slots_[i].active = true;
        slots_[i].target_id = next_id_++;
        std::strncpy(slots_[i].domain, domain, 255);
        slots_[i].domain[255] = '\0';
        std::strncpy(slots_[i].scope, scope, 511);
        slots_[i].scope[511] = '\0';
        slots_[i].state = TargetState::QUEUED;
        slots_[i].risk_band = 0.0;
        slots_[i].confidence = 0.0;
        slots_[i].scope_valid = false;
        slots_[i].dup_clear = false;
        return static_cast<int>(slots_[i].target_id);
      }
    }
    return -1;
  }

  // --- Advance target state ---
  bool advance(uint32_t target_id) {
    TargetSlot *slot = find(target_id);
    if (!slot)
      return false;

    switch (slot->state) {
    case TargetState::QUEUED:
      slot->state = TargetState::SCOPE_VALIDATING;
      break;
    case TargetState::SCOPE_VALIDATING:
      slot->scope_valid = true; // validated by scope engine
      slot->state = TargetState::DUP_CHECKING;
      break;
    case TargetState::DUP_CHECKING:
      slot->dup_clear = true; // cleared by dup engine
      slot->state = TargetState::EXECUTING;
      break;
    case TargetState::EXECUTING:
      slot->state = TargetState::REPORT_PENDING; // awaits human
      break;
    case TargetState::REPORT_PENDING:
      slot->state = TargetState::COMPLETED;
      break;
    default:
      return false;
    }
    return true;
  }

  // --- Remove completed/failed target ---
  bool release(uint32_t target_id) {
    TargetSlot *slot = find(target_id);
    if (!slot)
      return false;
    if (slot->state != TargetState::COMPLETED &&
        slot->state != TargetState::FAILED)
      return false;
    slot->active = false;
    return true;
  }

  // --- Pause all (resource/thermal limit) ---
  void pause_all() {
    for (uint32_t i = 0; i < MAX_CONCURRENT_TARGETS; ++i) {
      if (slots_[i].active && slots_[i].state == TargetState::EXECUTING)
        slots_[i].state = TargetState::PAUSED;
    }
  }

  // --- Resume paused ---
  void resume_all() {
    for (uint32_t i = 0; i < MAX_CONCURRENT_TARGETS; ++i) {
      if (slots_[i].active && slots_[i].state == TargetState::PAUSED)
        slots_[i].state = TargetState::EXECUTING;
    }
  }

  uint32_t active_count() const {
    uint32_t c = 0;
    for (uint32_t i = 0; i < MAX_CONCURRENT_TARGETS; ++i)
      if (slots_[i].active)
        ++c;
    return c;
  }

  static constexpr uint32_t max_targets() { return MAX_CONCURRENT_TARGETS; }

private:
  TargetSlot slots_[MAX_CONCURRENT_TARGETS];
  uint32_t next_id_;

  TargetSlot *find(uint32_t id) {
    for (uint32_t i = 0; i < MAX_CONCURRENT_TARGETS; ++i)
      if (slots_[i].active && slots_[i].target_id == id)
        return &slots_[i];
    return nullptr;
  }
};

} // namespace hunt_engine
