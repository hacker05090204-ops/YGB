/**
 * field_isolation_controller.cpp — Multi-Field Isolation Controller
 *
 * Prevents cross-field training overlap.
 *
 * Rules:
 *   - ONE active field at a time
 *   - After field certified: freeze → export representation → begin next
 *   - No simultaneous field training
 *   - No mid-training cross-field merge
 *
 * Timeline estimates:
 *   Field 1: 95%→14d, 97%→21-28d, 98%→30-40d
 *   Field 2: ~20-30 additional days
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace distributed {

// =========================================================================
// FIELD STATE
// =========================================================================

enum class FieldState : uint8_t {
  NOT_STARTED = 0,
  TRAINING = 1,
  CERTIFIED = 2,
  FROZEN = 3,
  EXPORTED = 4
};

static const char *field_state_name(FieldState s) {
  switch (s) {
  case FieldState::NOT_STARTED:
    return "NOT_STARTED";
  case FieldState::TRAINING:
    return "TRAINING";
  case FieldState::CERTIFIED:
    return "CERTIFIED";
  case FieldState::FROZEN:
    return "FROZEN";
  case FieldState::EXPORTED:
    return "EXPORTED";
  default:
    return "UNKNOWN";
  }
}

// =========================================================================
// FIELD RECORD
// =========================================================================

struct FieldRecord {
  char name[64];
  FieldState state;
  double precision;
  double ece;
  uint32_t training_days;
  uint32_t epochs_completed;
  bool representation_exported;
};

// =========================================================================
// FIELD ISOLATION CONTROLLER
// =========================================================================

static constexpr uint32_t MAX_FIELDS = 8;

class FieldIsolationController {
public:
  static constexpr bool ALLOW_PARALLEL_FIELDS = false;
  static constexpr bool ALLOW_MID_TRAINING_MERGE = false;

  FieldIsolationController() : count_(0), active_field_(-1) {
    std::memset(fields_, 0, sizeof(fields_));
  }

  // Register a new field
  int register_field(const char *name) {
    if (count_ >= MAX_FIELDS)
      return -1;
    FieldRecord &f = fields_[count_];
    std::strncpy(f.name, name, 63);
    f.name[63] = '\0';
    f.state = FieldState::NOT_STARTED;
    return static_cast<int>(count_++);
  }

  // Start training a field (only if no other field is active)
  bool start_training(uint32_t field_idx) {
    if (field_idx >= count_)
      return false;
    if (active_field_ >= 0)
      return false; // PARALLEL BLOCKED

    fields_[field_idx].state = FieldState::TRAINING;
    active_field_ = static_cast<int>(field_idx);
    return true;
  }

  // Certify a field (precision + ECE gates passed)
  bool certify(uint32_t field_idx, double precision, double ece) {
    if (field_idx >= count_)
      return false;
    if (fields_[field_idx].state != FieldState::TRAINING)
      return false;

    fields_[field_idx].precision = precision;
    fields_[field_idx].ece = ece;
    fields_[field_idx].state = FieldState::CERTIFIED;
    return true;
  }

  // Freeze certified field
  bool freeze(uint32_t field_idx) {
    if (field_idx >= count_)
      return false;
    if (fields_[field_idx].state != FieldState::CERTIFIED)
      return false;

    fields_[field_idx].state = FieldState::FROZEN;
    if (active_field_ == static_cast<int>(field_idx))
      active_field_ = -1;
    return true;
  }

  // Export and release for next field
  bool export_representation(uint32_t field_idx) {
    if (field_idx >= count_)
      return false;
    if (fields_[field_idx].state != FieldState::FROZEN)
      return false;

    fields_[field_idx].state = FieldState::EXPORTED;
    fields_[field_idx].representation_exported = true;
    return true;
  }

  bool has_active_field() const { return active_field_ >= 0; }
  int active_field() const { return active_field_; }
  uint32_t count() const { return count_; }

  const FieldRecord *field(uint32_t idx) const {
    return (idx < count_) ? &fields_[idx] : nullptr;
  }

private:
  FieldRecord fields_[MAX_FIELDS];
  uint32_t count_;
  int active_field_;
};

} // namespace distributed
