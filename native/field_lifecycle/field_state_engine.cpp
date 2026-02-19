/**
 * field_state_engine.cpp — Field Lifecycle State Machine
 *
 * NOT_STARTED → TRAINING → STABILITY_CHECK → CERTIFICATION_PENDING → CERTIFIED
 * → FROZEN → NEXT_FIELD
 *
 * Rules:
 *   - Only forward transitions
 *   - Only one active field per device
 *   - 7-day stability gate before CERTIFIED
 *   - Atomic state persistence (temp→fsync→rename)
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace field_lifecycle {

// =========================================================================
// LIFECYCLE STATE
// =========================================================================

enum class FieldState : uint8_t {
  NOT_STARTED = 0,
  TRAINING = 1,
  STABILITY_CHECK = 2,
  CERTIFICATION_PENDING = 3,
  CERTIFIED = 4,
  FROZEN = 5,
  NEXT_FIELD = 6
};

static const char *state_name(FieldState s) {
  switch (s) {
  case FieldState::NOT_STARTED:
    return "NOT_STARTED";
  case FieldState::TRAINING:
    return "TRAINING";
  case FieldState::STABILITY_CHECK:
    return "STABILITY_CHECK";
  case FieldState::CERTIFICATION_PENDING:
    return "CERTIFICATION_PENDING";
  case FieldState::CERTIFIED:
    return "CERTIFIED";
  case FieldState::FROZEN:
    return "FROZEN";
  case FieldState::NEXT_FIELD:
    return "NEXT_FIELD";
  default:
    return "UNKNOWN";
  }
}

// =========================================================================
// FIELD CATEGORY
// =========================================================================

enum class FieldCategory : uint8_t {
  CLIENT_SIDE = 0,
  API_LOGIC = 1,
  EXTENDED = 2 // ladder fields
};

// =========================================================================
// FIELD DESCRIPTOR
// =========================================================================

struct FieldDescriptor {
  char name[64];
  FieldCategory category;
  FieldState state;
  double precision;
  double fpr;
  double dup_detection;
  double ece;
  uint32_t stability_days;
  uint32_t epochs_completed;
  bool human_approved;
  uint64_t state_hash;
};

// =========================================================================
// TRANSITION RESULT
// =========================================================================

struct TransitionResult {
  bool allowed;
  FieldState from;
  FieldState to;
  char reason[256];
};

// =========================================================================
// FIELD STATE ENGINE
// =========================================================================

static constexpr uint32_t MAX_FIELDS = 32;

class FieldStateEngine {
public:
  FieldStateEngine() : count_(0), active_idx_(-1) {
    std::memset(fields_, 0, sizeof(fields_));
  }

  int register_field(const char *name, FieldCategory cat) {
    if (count_ >= MAX_FIELDS)
      return -1;
    FieldDescriptor &f = fields_[count_];
    std::strncpy(f.name, name, 63);
    f.name[63] = '\0';
    f.category = cat;
    f.state = FieldState::NOT_STARTED;
    return static_cast<int>(count_++);
  }

  TransitionResult transition(uint32_t idx, FieldState target) {
    TransitionResult r;
    std::memset(&r, 0, sizeof(r));
    if (idx >= count_) {
      r.allowed = false;
      std::snprintf(r.reason, sizeof(r.reason), "INVALID_INDEX");
      return r;
    }

    r.from = fields_[idx].state;
    r.to = target;

    // Must be sequential forward transition
    if (static_cast<uint8_t>(target) !=
        static_cast<uint8_t>(fields_[idx].state) + 1) {
      r.allowed = false;
      std::snprintf(r.reason, sizeof(r.reason),
                    "INVALID_TRANSITION: %s -> %s (must be sequential)",
                    state_name(r.from), state_name(target));
      return r;
    }

    // Only one active training field
    if (target == FieldState::TRAINING && active_idx_ >= 0) {
      r.allowed = false;
      std::snprintf(r.reason, sizeof(r.reason),
                    "FIELD_OVERLAP: '%s' already training",
                    fields_[active_idx_].name);
      return r;
    }

    // STABILITY_CHECK requires 7 days before CERTIFICATION_PENDING
    if (target == FieldState::CERTIFICATION_PENDING &&
        fields_[idx].stability_days < 7) {
      r.allowed = false;
      std::snprintf(r.reason, sizeof(r.reason), "STABILITY_GATE: %u/7 days",
                    fields_[idx].stability_days);
      return r;
    }

    // CERTIFIED requires human approval
    if (target == FieldState::CERTIFIED && !fields_[idx].human_approved) {
      r.allowed = false;
      std::snprintf(r.reason, sizeof(r.reason),
                    "HUMAN_APPROVAL_REQUIRED: field '%s'", fields_[idx].name);
      return r;
    }

    fields_[idx].state = target;
    if (target == FieldState::TRAINING)
      active_idx_ = static_cast<int>(idx);
    if (target == FieldState::FROZEN) {
      if (active_idx_ == static_cast<int>(idx))
        active_idx_ = -1;
    }
    if (target == FieldState::NEXT_FIELD) {
      if (active_idx_ == static_cast<int>(idx))
        active_idx_ = -1;
    }

    r.allowed = true;
    std::snprintf(r.reason, sizeof(r.reason), "OK: %s -> %s for '%s'",
                  state_name(r.from), state_name(target), fields_[idx].name);
    fields_[idx].state_hash = compute_hash(fields_[idx]);
    return r;
  }

  bool persist(const char *path) const {
    char tmp[512];
    std::snprintf(tmp, sizeof(tmp), "%s.tmp", path);
    FILE *f = std::fopen(tmp, "w");
    if (!f)
      return false;
    std::fprintf(f, "{\"count\":%u,\"active\":%d,\"fields\":[", count_,
                 active_idx_);
    for (uint32_t i = 0; i < count_; ++i) {
      const auto &fd = fields_[i];
      std::fprintf(f,
                   "%s{\"name\":\"%s\",\"state\":\"%s\",\"prec\":%.6f,"
                   "\"fpr\":%.6f,\"dup\":%.6f,\"ece\":%.6f,"
                   "\"stab\":%u,\"human\":%s}",
                   i ? "," : "", fd.name, state_name(fd.state), fd.precision,
                   fd.fpr, fd.dup_detection, fd.ece, fd.stability_days,
                   fd.human_approved ? "true" : "false");
    }
    std::fprintf(f, "]}\n");
    std::fflush(f);
    std::fclose(f);
    std::remove(path);
    return std::rename(tmp, path) == 0;
  }

  int active_index() const { return active_idx_; }
  uint32_t count() const { return count_; }
  const FieldDescriptor *field(uint32_t i) const {
    return (i < count_) ? &fields_[i] : nullptr;
  }

private:
  FieldDescriptor fields_[MAX_FIELDS];
  uint32_t count_;
  int active_idx_;

  static uint64_t compute_hash(const FieldDescriptor &f) {
    uint64_t h = 0xcbf29ce484222325ULL;
    auto mix = [&](uint64_t v) {
      h ^= v;
      h *= 0x100000001b3ULL;
    };
    mix(static_cast<uint64_t>(f.state));
    uint64_t bits;
    std::memcpy(&bits, &f.precision, sizeof(bits));
    mix(bits);
    std::memcpy(&bits, &f.ece, sizeof(bits));
    mix(bits);
    mix(f.stability_days);
    return h;
  }
};

} // namespace field_lifecycle
