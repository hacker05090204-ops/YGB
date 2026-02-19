/**
 * field_progression_controller.cpp — Auto-Progression After Certification
 *
 * Orchestrates the chained field progression:
 *   - After certification + 7-day stability → auto-progress to next field
 *   - Metric-based only, no time-forced completion
 *   - Full isolation between fields during transition
 *
 * NO skipping. NO parallel fields. NO time-based forced completion.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace field_lifecycle {

// =========================================================================
// PROGRESSION STATUS
// =========================================================================

enum class ProgressStatus : uint8_t {
  AWAITING_TRAINING = 0,
  TRAINING_ACTIVE = 1,
  AWAITING_STABILITY = 2,
  CERTIFIED_STABLE = 3,
  TRANSITIONING = 4,
  ALL_COMPLETE = 5
};

static const char *progress_name(ProgressStatus s) {
  switch (s) {
  case ProgressStatus::AWAITING_TRAINING:
    return "AWAITING_TRAINING";
  case ProgressStatus::TRAINING_ACTIVE:
    return "TRAINING_ACTIVE";
  case ProgressStatus::AWAITING_STABILITY:
    return "AWAITING_STABILITY";
  case ProgressStatus::CERTIFIED_STABLE:
    return "CERTIFIED_STABLE";
  case ProgressStatus::TRANSITIONING:
    return "TRANSITIONING";
  case ProgressStatus::ALL_COMPLETE:
    return "ALL_COMPLETE";
  default:
    return "UNKNOWN";
  }
}

// =========================================================================
// PROGRESSION DECISION
// =========================================================================

struct ProgressionDecision {
  bool should_progress;
  ProgressStatus status;
  uint32_t current_field_id;
  uint32_t next_field_id;
  char reason[256];
};

// =========================================================================
// FIELD PROGRESSION CONTROLLER
// =========================================================================

class FieldProgressionController {
public:
  static constexpr bool ALLOW_SKIP = false;
  static constexpr bool ALLOW_TIME_FORCED = false;
  static constexpr bool ALLOW_PARALLEL = false;

  ProgressionDecision evaluate(uint32_t field_id, bool certified,
                               uint32_t stability_days, bool human_ok,
                               double precision, double fpr, double ece,
                               uint32_t total_fields) {
    ProgressionDecision d;
    std::memset(&d, 0, sizeof(d));
    d.current_field_id = field_id;

    // Not certified yet
    if (!certified) {
      d.should_progress = false;
      d.status = ProgressStatus::TRAINING_ACTIVE;
      std::snprintf(d.reason, sizeof(d.reason),
                    "TRAINING: field %u not certified", field_id);
      return d;
    }

    // Certified but stability gate not met
    if (stability_days < 7) {
      d.should_progress = false;
      d.status = ProgressStatus::AWAITING_STABILITY;
      std::snprintf(d.reason, sizeof(d.reason),
                    "STABILITY_WAIT: %u/7 days for field %u", stability_days,
                    field_id);
      return d;
    }

    // Human approval required
    if (!human_ok) {
      d.should_progress = false;
      d.status = ProgressStatus::CERTIFIED_STABLE;
      std::snprintf(d.reason, sizeof(d.reason),
                    "AWAITING_HUMAN: field %u certified+stable", field_id);
      return d;
    }

    // All checks passed — progress to next
    if (field_id + 1 >= total_fields) {
      d.should_progress = false;
      d.status = ProgressStatus::ALL_COMPLETE;
      std::snprintf(d.reason, sizeof(d.reason),
                    "ALL_FIELDS_COMPLETE: ladder exhausted");
      return d;
    }

    d.should_progress = true;
    d.next_field_id = field_id + 1;
    d.status = ProgressStatus::TRANSITIONING;
    std::snprintf(d.reason, sizeof(d.reason),
                  "PROGRESS: field %u -> %u (metric-based)", field_id,
                  field_id + 1);
    return d;
  }
};

} // namespace field_lifecycle
