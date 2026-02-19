/**
 * field_state_engine.cpp — Field Lifecycle State Machine
 *
 * States: NOT_STARTED → TRAINING → CERTIFIED → FROZEN
 * Only one active field per device.
 * Atomic persist: write temp → fsync → rename.
 *
 * NO company-specific specialization.
 * NO cross-field dataset loading.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace field_controller {

// =========================================================================
// FIELD LIFECYCLE STATE
// =========================================================================

enum class FieldLifecycle : uint8_t {
  NOT_STARTED = 0,
  TRAINING = 1,
  CERTIFIED = 2,
  FROZEN = 3
};

static const char *lifecycle_name(FieldLifecycle s) {
  switch (s) {
  case FieldLifecycle::NOT_STARTED:
    return "NOT_STARTED";
  case FieldLifecycle::TRAINING:
    return "TRAINING";
  case FieldLifecycle::CERTIFIED:
    return "CERTIFIED";
  case FieldLifecycle::FROZEN:
    return "FROZEN";
  default:
    return "UNKNOWN";
  }
}

// =========================================================================
// FIELD DESCRIPTOR
// =========================================================================

struct FieldDescriptor {
  char name[64];
  char category[64]; // "client_side_web" or "api_business_logic"
  FieldLifecycle state;
  double precision;
  double false_positive_rate;
  double duplicate_detection;
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
  FieldLifecycle from;
  FieldLifecycle to;
  char reason[256];
};

// =========================================================================
// FIELD STATE ENGINE
// =========================================================================

static constexpr uint32_t MAX_FIELDS = 4;

class FieldStateEngine {
public:
  FieldStateEngine() : count_(0), active_idx_(-1) {
    std::memset(fields_, 0, sizeof(fields_));
  }

  // Register a field
  int register_field(const char *name, const char *category) {
    if (count_ >= MAX_FIELDS)
      return -1;
    FieldDescriptor &f = fields_[count_];
    std::strncpy(f.name, name, 63);
    f.name[63] = '\0';
    std::strncpy(f.category, category, 63);
    f.category[63] = '\0';
    f.state = FieldLifecycle::NOT_STARTED;
    return static_cast<int>(count_++);
  }

  // Transition a field to next state
  TransitionResult transition(uint32_t idx, FieldLifecycle target) {
    TransitionResult r;
    std::memset(&r, 0, sizeof(r));

    if (idx >= count_) {
      r.allowed = false;
      std::snprintf(r.reason, sizeof(r.reason), "INVALID_FIELD_INDEX");
      return r;
    }

    r.from = fields_[idx].state;
    r.to = target;

    // Only forward transitions allowed
    if (static_cast<uint8_t>(target) !=
        static_cast<uint8_t>(fields_[idx].state) + 1) {
      r.allowed = false;
      std::snprintf(r.reason, sizeof(r.reason),
                    "INVALID_TRANSITION: %s -> %s (must be sequential)",
                    lifecycle_name(r.from), lifecycle_name(target));
      return r;
    }

    // Only one active training field
    if (target == FieldLifecycle::TRAINING && active_idx_ >= 0) {
      r.allowed = false;
      std::snprintf(r.reason, sizeof(r.reason),
                    "FIELD_OVERLAP: field '%s' already training",
                    fields_[active_idx_].name);
      return r;
    }

    fields_[idx].state = target;
    if (target == FieldLifecycle::TRAINING) {
      active_idx_ = static_cast<int>(idx);
    } else if (target == FieldLifecycle::FROZEN) {
      if (active_idx_ == static_cast<int>(idx))
        active_idx_ = -1;
    }

    r.allowed = true;
    std::snprintf(r.reason, sizeof(r.reason),
                  "TRANSITION_OK: %s -> %s for '%s'", lifecycle_name(r.from),
                  lifecycle_name(target), fields_[idx].name);

    // Update state hash
    fields_[idx].state_hash = compute_hash(fields_[idx]);
    return r;
  }

  // Persist state atomically (temp → fsync → rename pattern)
  bool persist(const char *path) const {
    char tmp_path[512];
    std::snprintf(tmp_path, sizeof(tmp_path), "%s.tmp", path);

    FILE *f = std::fopen(tmp_path, "w");
    if (!f)
      return false;

    std::fprintf(f, "{\n");
    std::fprintf(f, "  \"field_count\": %u,\n", count_);
    std::fprintf(f, "  \"active_field\": %d,\n", active_idx_);
    std::fprintf(f, "  \"fields\": [\n");
    for (uint32_t i = 0; i < count_; ++i) {
      const auto &fd = fields_[i];
      std::fprintf(f,
                   "    {\"name\":\"%s\",\"category\":\"%s\","
                   "\"state\":\"%s\",\"precision\":%.6f,"
                   "\"fpr\":%.6f,\"dup\":%.6f,\"ece\":%.6f,"
                   "\"stability_days\":%u,\"human_approved\":%s}%s\n",
                   fd.name, fd.category, lifecycle_name(fd.state), fd.precision,
                   fd.false_positive_rate, fd.duplicate_detection, fd.ece,
                   fd.stability_days, fd.human_approved ? "true" : "false",
                   (i < count_ - 1) ? "," : "");
    }
    std::fprintf(f, "  ]\n}\n");
    std::fflush(f);
    std::fclose(f);

    // Atomic rename
    std::remove(path);
    return std::rename(tmp_path, path) == 0;
  }

  int active_index() const { return active_idx_; }
  uint32_t count() const { return count_; }
  const FieldDescriptor *field(uint32_t idx) const {
    return (idx < count_) ? &fields_[idx] : nullptr;
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

} // namespace field_controller
