/**
 * phase_state_engine.cpp — Lifecycle Phase State Engine
 *
 * Prevents backward phase execution or re-trigger of Phase 1–7 after freeze.
 *
 * Rules:
 *   - Phase number can only increase (one-way transitions).
 *   - Backward execution logs PHASE_REENTRY_BLOCKED.
 *   - If MODE_A_FROZEN: disable training, baseline recalc, phases 1–7.
 *   - Allow only: runtime monitoring, drift tracking, dup tracking, voice.
 *
 * NO weight modification. NO authority change. NO governance change.
 */

#include <cmath>
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

namespace lifecycle {

// =========================================================================
// PHASE STATE ENUM
// =========================================================================

enum class PhaseState : uint8_t {
  PHASE_1_COMPLETE = 1,
  PHASE_2_COMPLETE = 2,
  PHASE_3_COMPLETE = 3,
  PHASE_4_COMPLETE = 4,
  PHASE_5_COMPLETE = 5,
  PHASE_6_COMPLETE = 6,
  PHASE_7_COMPLETE = 7,
  PHASE_MODE_A_FROZEN = 10,
  PHASE_MODE_B_SHADOW = 11,
  PHASE_MODE_C_LAB = 12
};

static const char *phase_state_name(PhaseState s) {
  switch (s) {
  case PhaseState::PHASE_1_COMPLETE:
    return "PHASE_1_COMPLETE";
  case PhaseState::PHASE_2_COMPLETE:
    return "PHASE_2_COMPLETE";
  case PhaseState::PHASE_3_COMPLETE:
    return "PHASE_3_COMPLETE";
  case PhaseState::PHASE_4_COMPLETE:
    return "PHASE_4_COMPLETE";
  case PhaseState::PHASE_5_COMPLETE:
    return "PHASE_5_COMPLETE";
  case PhaseState::PHASE_6_COMPLETE:
    return "PHASE_6_COMPLETE";
  case PhaseState::PHASE_7_COMPLETE:
    return "PHASE_7_COMPLETE";
  case PhaseState::PHASE_MODE_A_FROZEN:
    return "PHASE_MODE_A_FROZEN";
  case PhaseState::PHASE_MODE_B_SHADOW:
    return "PHASE_MODE_B_SHADOW";
  case PhaseState::PHASE_MODE_C_LAB:
    return "PHASE_MODE_C_LAB";
  default:
    return "UNKNOWN";
  }
}

// =========================================================================
// TRANSITION RESULT
// =========================================================================

struct TransitionResult {
  bool allowed;
  PhaseState from;
  PhaseState to;
  char reason[256];
};

// =========================================================================
// PERSISTENCE
// =========================================================================

static constexpr char STATE_PATH[] = "reports/phase_state.json";
static constexpr char STATE_TMP[] = "reports/phase_state.json.tmp";

static bool save_phase_state(PhaseState state) {
  FILE *f = std::fopen(STATE_TMP, "w");
  if (!f)
    return false;

  std::fprintf(f, "{\n");
  std::fprintf(f, "  \"version\": 1,\n");
  std::fprintf(f, "  \"phase_state\": %d,\n", static_cast<int>(state));
  std::fprintf(f, "  \"phase_name\": \"%s\"\n", phase_state_name(state));
  std::fprintf(f, "}\n");

  std::fflush(f);
  int fd = fileno(f);
  if (fd >= 0)
    fsync_fd(fd);
  std::fclose(f);

  std::remove(STATE_PATH);
  return std::rename(STATE_TMP, STATE_PATH) == 0;
}

static PhaseState load_phase_state() {
  FILE *f = std::fopen(STATE_PATH, "r");
  if (!f)
    return PhaseState::PHASE_1_COMPLETE; // baseline

  char buf[1024];
  std::memset(buf, 0, sizeof(buf));
  std::fread(buf, 1, sizeof(buf) - 1, f);
  std::fclose(f);

  // Parse "phase_state": N
  const char *pos = std::strstr(buf, "\"phase_state\"");
  if (!pos)
    return PhaseState::PHASE_1_COMPLETE;
  pos += 13; // skip key
  while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
    ++pos;
  int val = 0;
  std::sscanf(pos, "%d", &val);

  if (val >= 1 && val <= 12)
    return static_cast<PhaseState>(val);
  return PhaseState::PHASE_1_COMPLETE;
}

// =========================================================================
// PHASE STATE ENGINE
// =========================================================================

class PhaseStateEngine {
public:
  PhaseStateEngine() { current_ = load_phase_state(); }

  PhaseState current() const { return current_; }
  const char *current_name() const { return phase_state_name(current_); }

  // --- One-way transition (Phase 2 rules) ---
  TransitionResult transition(PhaseState new_state) {
    TransitionResult r;
    r.from = current_;
    r.to = new_state;

    uint8_t cur = static_cast<uint8_t>(current_);
    uint8_t req = static_cast<uint8_t>(new_state);

    // Rule: phase number can only increase
    if (req <= cur) {
      r.allowed = false;
      std::snprintf(r.reason, sizeof(r.reason),
                    "PHASE_REENTRY_BLOCKED: %s(%d) -> %s(%d) denied — "
                    "backward or same-phase transition",
                    phase_state_name(current_), cur,
                    phase_state_name(new_state), req);
      return r;
    }

    // Forward transition allowed
    current_ = new_state;
    save_phase_state(current_);
    r.allowed = true;
    std::snprintf(r.reason, sizeof(r.reason), "PHASE_TRANSITION: %s -> %s",
                  phase_state_name(r.from), phase_state_name(new_state));
    return r;
  }

  // --- Check if a specific phase routine is allowed (Phase 2) ---
  bool is_phase_allowed(int phase_number) const {
    if (phase_number < 1 || phase_number > 7)
      return false;

    // If frozen, no phase 1-7 routines allowed (Phase 3)
    if (is_frozen())
      return false;

    // Phase can only run if current state hasn't passed it
    uint8_t cur = static_cast<uint8_t>(current_);
    return phase_number >= static_cast<int>(cur);
  }

  // --- Freeze lock (Phase 3) ---
  bool is_frozen() const { return current_ == PhaseState::PHASE_MODE_A_FROZEN; }

  // --- What's allowed when frozen ---
  bool is_monitoring_allowed() const { return true; } // always
  bool is_drift_tracking_allowed() const { return true; }
  bool is_duplicate_tracking_allowed() const { return true; }
  bool is_voice_allowed() const { return true; }
  bool is_browser_curriculum_allowed() const { return true; }
  bool is_training_allowed() const { return !is_frozen(); }
  bool is_baseline_recalc_allowed() const { return !is_frozen(); }

  // --- Persist current state ---
  bool save() const { return save_phase_state(current_); }

  // --- Reset (for testing only) ---
  void reset_for_test() {
    current_ = PhaseState::PHASE_1_COMPLETE;
    std::remove(STATE_PATH);
  }

  // =====================================================================
  // SELF-TESTS
  // =====================================================================

  static bool run_tests() {
    int passed = 0, failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (cond)
        ++passed;
      else {
        ++failed;
        std::fprintf(stderr, "  FAIL: %s\n", name);
      }
    };

    // Clean state for tests
    std::remove(STATE_PATH);
    std::remove(STATE_TMP);

    PhaseStateEngine engine;

    // Test 1: Initial state is PHASE_1_COMPLETE
    test(engine.current() == PhaseState::PHASE_1_COMPLETE,
         "Initial state = PHASE_1_COMPLETE");

    // Test 2: Forward transition allowed
    auto r1 = engine.transition(PhaseState::PHASE_3_COMPLETE);
    test(r1.allowed, "Forward 1->3 allowed");
    test(engine.current() == PhaseState::PHASE_3_COMPLETE,
         "State is now PHASE_3_COMPLETE");

    // Test 3: Backward transition BLOCKED
    auto r2 = engine.transition(PhaseState::PHASE_2_COMPLETE);
    test(!r2.allowed, "Backward 3->2 blocked");
    test(engine.current() == PhaseState::PHASE_3_COMPLETE,
         "State unchanged after backward attempt");

    // Test 4: Same-phase transition BLOCKED
    auto r3 = engine.transition(PhaseState::PHASE_3_COMPLETE);
    test(!r3.allowed, "Same-phase 3->3 blocked");

    // Test 5: Forward to PHASE_7_COMPLETE
    auto r4 = engine.transition(PhaseState::PHASE_7_COMPLETE);
    test(r4.allowed, "Forward 3->7 allowed");

    // Test 6: is_phase_allowed checks
    test(!engine.is_phase_allowed(1), "Phase 1 not allowed (past it)");
    test(!engine.is_phase_allowed(6), "Phase 6 not allowed (past it)");
    test(engine.is_phase_allowed(7), "Phase 7 allowed (current)");

    // Test 7: Transition to FROZEN
    auto r5 = engine.transition(PhaseState::PHASE_MODE_A_FROZEN);
    test(r5.allowed, "Forward 7->FROZEN allowed");
    test(engine.is_frozen(), "Engine reports frozen");

    // Test 8: Freeze lock — no phases allowed
    test(!engine.is_phase_allowed(1), "Frozen: phase 1 blocked");
    test(!engine.is_phase_allowed(7), "Frozen: phase 7 blocked");
    test(!engine.is_training_allowed(), "Frozen: training blocked");
    test(!engine.is_baseline_recalc_allowed(),
         "Frozen: baseline recalc blocked");

    // Test 9: Monitoring still allowed when frozen
    test(engine.is_monitoring_allowed(), "Frozen: monitoring allowed");
    test(engine.is_drift_tracking_allowed(), "Frozen: drift tracking allowed");
    test(engine.is_duplicate_tracking_allowed(),
         "Frozen: dup tracking allowed");
    test(engine.is_voice_allowed(), "Frozen: voice allowed");

    // Test 10: Backward from frozen BLOCKED
    auto r6 = engine.transition(PhaseState::PHASE_7_COMPLETE);
    test(!r6.allowed, "Backward FROZEN->7 blocked");

    // Test 11: Persistence round-trip
    {
      PhaseStateEngine engine2; // should load from file
      test(engine2.current() == PhaseState::PHASE_MODE_A_FROZEN,
           "Persistence: state loaded from file");
      test(engine2.is_frozen(), "Persistence: frozen state loaded");
    }

    // Test 12: Missing file → baseline
    std::remove(STATE_PATH);
    {
      PhaseStateEngine engine3;
      test(engine3.current() == PhaseState::PHASE_1_COMPLETE,
           "Missing file → PHASE_1_COMPLETE baseline");
    }

    // Cleanup
    std::remove(STATE_PATH);
    std::remove(STATE_TMP);

    std::fprintf(stdout, "  Phase State Engine: %d passed, %d failed\n", passed,
                 failed);
    return failed == 0;
  }

private:
  PhaseState current_;
};

} // namespace lifecycle
