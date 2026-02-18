/**
 * mode_lock.cpp — Strict TRAIN/HUNT Mode Lock
 *
 * Enforces mutual exclusion between training and hunting modes.
 *
 * Rules:
 *   - TRAIN_MODE blocks all external target input
 *   - HUNT_MODE blocks all weight updates
 *   - Cannot overlap (mutex-style)
 *   - Transition requires idle state
 *
 * Atomic persistence: reports/mode_state.json
 *
 * NO uncontrolled live learning. NO training on real targets.
 */

#include <cstdint>
#include <cstdio>
#include <cstring>


#ifdef _WIN32
#include <io.h>
#define fsync_fd(fd) _commit(fd)
#else
#include <unistd.h>
#define fsync_fd(fd) fsync(fd)
#endif

namespace mode_runtime {

// =========================================================================
// MODE ENUM
// =========================================================================

enum class RuntimeMode : uint8_t { IDLE = 0, TRAIN_MODE = 1, HUNT_MODE = 2 };

static const char *mode_name(RuntimeMode m) {
  switch (m) {
  case RuntimeMode::IDLE:
    return "IDLE";
  case RuntimeMode::TRAIN_MODE:
    return "TRAIN_MODE";
  case RuntimeMode::HUNT_MODE:
    return "HUNT_MODE";
  default:
    return "UNKNOWN";
  }
}

// =========================================================================
// TRANSITION RESULT
// =========================================================================

struct ModeTransitionResult {
  bool allowed;
  RuntimeMode from;
  RuntimeMode to;
  char reason[256];
};

// =========================================================================
// PERSISTENCE
// =========================================================================

static constexpr char MODE_PATH[] = "reports/mode_state.json";
static constexpr char MODE_TMP[] = "reports/mode_state.json.tmp";

static bool save_mode(RuntimeMode mode) {
  FILE *f = std::fopen(MODE_TMP, "w");
  if (!f)
    return false;

  std::fprintf(f, "{\n");
  std::fprintf(f, "  \"version\": 1,\n");
  std::fprintf(f, "  \"mode\": %d,\n", static_cast<int>(mode));
  std::fprintf(f, "  \"mode_name\": \"%s\"\n", mode_name(mode));
  std::fprintf(f, "}\n");

  std::fflush(f);
  int fd = fileno(f);
  if (fd >= 0)
    fsync_fd(fd);
  std::fclose(f);

  std::remove(MODE_PATH);
  return std::rename(MODE_TMP, MODE_PATH) == 0;
}

static RuntimeMode load_mode() {
  FILE *f = std::fopen(MODE_PATH, "r");
  if (!f)
    return RuntimeMode::IDLE;

  char buf[512];
  std::memset(buf, 0, sizeof(buf));
  std::fread(buf, 1, sizeof(buf) - 1, f);
  std::fclose(f);

  const char *pos = std::strstr(buf, "\"mode\"");
  if (!pos)
    return RuntimeMode::IDLE;
  pos += 6;
  while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
    ++pos;
  int val = 0;
  std::sscanf(pos, "%d", &val);

  if (val >= 0 && val <= 2)
    return static_cast<RuntimeMode>(val);
  return RuntimeMode::IDLE;
}

// =========================================================================
// MODE LOCK
// =========================================================================

class ModeLock {
public:
  ModeLock() : mode_(load_mode()), active_tasks_(0) {}

  RuntimeMode current() const { return mode_; }
  const char *current_name() const { return mode_name(mode_); }
  bool is_idle() const { return mode_ == RuntimeMode::IDLE; }

  // --- Permission checks ---
  bool can_access_external_targets() const {
    return mode_ == RuntimeMode::HUNT_MODE;
  }

  bool can_update_weights() const { return mode_ == RuntimeMode::TRAIN_MODE; }

  bool can_train() const { return mode_ == RuntimeMode::TRAIN_MODE; }

  bool can_hunt() const { return mode_ == RuntimeMode::HUNT_MODE; }

  // --- Transitions (require idle state) ---
  ModeTransitionResult enter_train() {
    return transition_to(RuntimeMode::TRAIN_MODE);
  }

  ModeTransitionResult enter_hunt() {
    return transition_to(RuntimeMode::HUNT_MODE);
  }

  ModeTransitionResult enter_idle() {
    ModeTransitionResult r;
    r.from = mode_;
    r.to = RuntimeMode::IDLE;

    if (active_tasks_ > 0) {
      r.allowed = false;
      std::snprintf(r.reason, sizeof(r.reason),
                    "MODE_TRANSITION_BLOCKED: %u active tasks must complete",
                    active_tasks_);
      return r;
    }

    mode_ = RuntimeMode::IDLE;
    save_mode(mode_);
    r.allowed = true;
    std::snprintf(r.reason, sizeof(r.reason), "MODE_TRANSITION: %s -> IDLE",
                  mode_name(r.from));
    return r;
  }

  // --- Task tracking (for idle detection) ---
  void begin_task() { ++active_tasks_; }
  void end_task() {
    if (active_tasks_ > 0)
      --active_tasks_;
  }
  uint32_t active_tasks() const { return active_tasks_; }

private:
  RuntimeMode mode_;
  uint32_t active_tasks_;

  ModeTransitionResult transition_to(RuntimeMode target) {
    ModeTransitionResult r;
    r.from = mode_;
    r.to = target;

    // Must be idle to transition
    if (mode_ != RuntimeMode::IDLE) {
      r.allowed = false;
      std::snprintf(r.reason, sizeof(r.reason),
                    "MODE_OVERLAP_BLOCKED: Cannot enter %s while in %s — "
                    "must be IDLE first",
                    mode_name(target), mode_name(mode_));
      return r;
    }

    mode_ = target;
    save_mode(mode_);
    r.allowed = true;
    std::snprintf(r.reason, sizeof(r.reason), "MODE_TRANSITION: IDLE -> %s",
                  mode_name(target));
    return r;
  }
};

} // namespace mode_runtime
