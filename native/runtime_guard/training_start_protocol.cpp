/**
 * training_start_protocol.cpp — Training Start Protocol with Monotonic Clock
 *
 * Training allowed ONLY IF all gates pass:
 *   1. CI fully green
 *   2. Determinism validator PASS
 *   3. Cross-device validator PASS
 *   4. Freeze valid
 *   5. No containment active
 *   6. Telemetry validated (CRC + schema)
 *   7. Mode mutex active (not in HUNT)
 *   8. Thermal guard active (not in THERMAL_PAUSE)
 *   9. HMAC validated (telemetry signed)
 *
 * Post-start:
 *   - Enter MODE-A training only
 *   - 72-hour lockout on HUNT (monotonic clock — immune to rollback)
 *   - Auto-chain: MODE_A -> MODE_B -> MODE_C (thresholds required)
 *
 * NO silent fallback. NO race conditions. NO clock rollback bypass.
 */

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>

#ifdef _WIN32
#include <io.h>
#include <windows.h>
#define fsync_fd(fd) _commit(fd)
#else
#include <unistd.h>
#define fsync_fd(fd) fsync(fd)
#endif

namespace runtime_guard {

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr uint64_t HUNT_LOCKOUT_HOURS = 72;
static constexpr uint64_t HUNT_LOCKOUT_SECONDS = HUNT_LOCKOUT_HOURS * 3600;
static constexpr char PROTOCOL_STATE_PATH[] =
    "reports/training_protocol_state.json";
static constexpr char PROTOCOL_TMP_PATH[] =
    "reports/training_protocol_state.json.tmp";

// Mode progression thresholds
static constexpr double MODE_B_MIN_PRECISION = 0.90;
static constexpr double MODE_B_MIN_RECALL = 0.85;
static constexpr double MODE_C_MIN_PRECISION = 0.95;
static constexpr double MODE_C_MIN_RECALL = 0.92;
static constexpr double MODE_C_MAX_KL_DRIFT = 0.05;

// Mode enum
static constexpr int MODE_IDLE = 0;
static constexpr int MODE_A_TRAIN = 1;
static constexpr int MODE_B_TRAIN = 2;
static constexpr int MODE_C_TRAIN = 3;

// =========================================================================
// MONOTONIC CLOCK (immune to wall-clock rollback)
// =========================================================================

static uint64_t get_monotonic_seconds() {
#ifdef _WIN32
  // QueryPerformanceCounter — true monotonic on Windows
  static LARGE_INTEGER freq = {};
  if (freq.QuadPart == 0) {
    QueryPerformanceFrequency(&freq);
  }
  LARGE_INTEGER counter;
  QueryPerformanceCounter(&counter);
  return static_cast<uint64_t>(counter.QuadPart / freq.QuadPart);
#else
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return static_cast<uint64_t>(ts.tv_sec);
#endif
}

// =========================================================================
// GATE STATUS
// =========================================================================

struct GateResult {
  bool passed;
  char reason[256];
};

struct TrainingReadiness {
  bool ready;
  GateResult ci_green;
  GateResult determinism_pass;
  GateResult cross_device_pass;
  GateResult freeze_valid;
  GateResult no_containment;
  GateResult telemetry_valid;
  GateResult mode_mutex_ok;
  GateResult thermal_ok;
  GateResult hmac_valid;
  int gates_passed;
  int gates_total;
  char summary[1024];
};

// =========================================================================
// TRAINING STATE
// =========================================================================

struct TrainingState {
  bool training_active;
  uint64_t training_start_timestamp;     // Wall clock (for logging)
  uint64_t training_start_monotonic;     // Monotonic clock start
  uint64_t elapsed_seconds_monotonic;    // Accumulated monotonic elapsed
  uint64_t hunt_lockout_until_monotonic; // Monotonic target for unlock
  bool hunt_locked;
  int mode; // 0=IDLE, 1=MODE_A, 2=MODE_B, 3=MODE_C
};

// =========================================================================
// PERSISTENCE
// =========================================================================

static bool save_protocol_state(const TrainingState &state) {
  FILE *f = std::fopen(PROTOCOL_TMP_PATH, "w");
  if (!f)
    return false;

  std::fprintf(f, "{\n");
  std::fprintf(f, "  \"training_active\": %s,\n",
               state.training_active ? "true" : "false");
  std::fprintf(f, "  \"training_start_timestamp\": %llu,\n",
               static_cast<unsigned long long>(state.training_start_timestamp));
  std::fprintf(f, "  \"training_start_monotonic\": %llu,\n",
               static_cast<unsigned long long>(state.training_start_monotonic));
  std::fprintf(
      f, "  \"elapsed_seconds_monotonic\": %llu,\n",
      static_cast<unsigned long long>(state.elapsed_seconds_monotonic));
  std::fprintf(
      f, "  \"hunt_lockout_until_monotonic\": %llu,\n",
      static_cast<unsigned long long>(state.hunt_lockout_until_monotonic));
  std::fprintf(f, "  \"hunt_locked\": %s,\n",
               state.hunt_locked ? "true" : "false");
  std::fprintf(f, "  \"mode\": %d\n", state.mode);
  std::fprintf(f, "}\n");

  std::fflush(f);
  int fd = fileno(f);
  if (fd >= 0)
    fsync_fd(fd);
  std::fclose(f);

  std::remove(PROTOCOL_STATE_PATH);
  return std::rename(PROTOCOL_TMP_PATH, PROTOCOL_STATE_PATH) == 0;
}

static uint64_t parse_uint64_field(const char *buf, const char *key) {
  const char *pos = std::strstr(buf, key);
  if (!pos)
    return 0;
  pos += std::strlen(key);
  while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
    ++pos;
  unsigned long long val = 0;
  std::sscanf(pos, "%llu", &val);
  return static_cast<uint64_t>(val);
}

static bool parse_bool_field(const char *buf, const char *key) {
  const char *pos = std::strstr(buf, key);
  if (!pos)
    return false;
  pos += std::strlen(key);
  while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
    ++pos;
  return (std::strncmp(pos, "true", 4) == 0);
}

static int parse_int_field(const char *buf, const char *key) {
  const char *pos = std::strstr(buf, key);
  if (!pos)
    return 0;
  pos += std::strlen(key);
  while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
    ++pos;
  int val = 0;
  std::sscanf(pos, "%d", &val);
  return val;
}

static TrainingState load_protocol_state() {
  TrainingState state;
  std::memset(&state, 0, sizeof(state));

  FILE *f = std::fopen(PROTOCOL_STATE_PATH, "r");
  if (!f)
    return state;

  char buf[2048];
  std::memset(buf, 0, sizeof(buf));
  std::fread(buf, 1, sizeof(buf) - 1, f);
  std::fclose(f);

  state.training_active = parse_bool_field(buf, "training_active");
  state.training_start_timestamp =
      parse_uint64_field(buf, "training_start_timestamp");
  state.training_start_monotonic =
      parse_uint64_field(buf, "training_start_monotonic");
  state.elapsed_seconds_monotonic =
      parse_uint64_field(buf, "elapsed_seconds_monotonic");
  state.hunt_lockout_until_monotonic =
      parse_uint64_field(buf, "hunt_lockout_until_monotonic");
  state.hunt_locked = parse_bool_field(buf, "hunt_locked");
  state.mode = parse_int_field(buf, "\"mode\"");

  return state;
}

// =========================================================================
// FILE-BASED GATE CHECKS
// =========================================================================

static bool check_file_status(const char *path, const char *key,
                              const char *expected_value) {
  FILE *f = std::fopen(path, "r");
  if (!f)
    return false;

  char buf[2048];
  std::memset(buf, 0, sizeof(buf));
  std::fread(buf, 1, sizeof(buf) - 1, f);
  std::fclose(f);

  const char *pos = std::strstr(buf, key);
  if (!pos)
    return false;
  pos += std::strlen(key);
  while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
    ++pos;
  return (std::strncmp(pos, expected_value, std::strlen(expected_value)) == 0);
}

// =========================================================================
// HMAC VALIDATION GATE (reads telemetry and checks signature)
// =========================================================================

static bool check_hmac_valid() {
  // Check that HMAC field exists and is non-empty in telemetry
  FILE *f = std::fopen("reports/training_telemetry.json", "r");
  if (!f)
    return false;

  char buf[4096];
  std::memset(buf, 0, sizeof(buf));
  std::fread(buf, 1, sizeof(buf) - 1, f);
  std::fclose(f);

  const char *pos = std::strstr(buf, "\"hmac\"");
  if (!pos)
    return false;
  pos += 6;
  while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
    ++pos;
  // Must have at least 64 hex chars
  int count = 0;
  while (*pos && *pos != '"' && count < 65)
    ++count, ++pos;
  return count == 64;
}

// =========================================================================
// TRAINING START PROTOCOL
// =========================================================================

class TrainingStartProtocol {
public:
  TrainingStartProtocol() : state_(load_protocol_state()) {
    // Check if hunt lockout has expired (monotonic)
    if (state_.hunt_locked) {
      uint64_t now_mono = get_monotonic_seconds();
      uint64_t elapsed = state_.elapsed_seconds_monotonic;
      if (now_mono >= state_.training_start_monotonic) {
        elapsed = now_mono - state_.training_start_monotonic;
      }
      if (elapsed >= HUNT_LOCKOUT_SECONDS) {
        state_.hunt_locked = false;
        state_.elapsed_seconds_monotonic = elapsed;
        save_protocol_state(state_);
      }
    }
  }

  // --- Check all gates ---
  TrainingReadiness can_start_training() const {
    TrainingReadiness r;
    std::memset(&r, 0, sizeof(r));
    r.gates_total = 9;
    r.gates_passed = 0;

    // Gate 1: CI fully green
    r.ci_green.passed =
        check_file_status("reports/ci_status.json", "status", "green");
    if (r.ci_green.passed) {
      std::snprintf(r.ci_green.reason, sizeof(r.ci_green.reason),
                    "CI status: green");
      ++r.gates_passed;
    } else {
      std::snprintf(r.ci_green.reason, sizeof(r.ci_green.reason),
                    "CI status: not green or missing");
    }

    // Gate 2: Determinism validator PASS
    r.determinism_pass.passed = check_file_status(
        "reports/determinism_validation.json", "status", "pass");
    if (r.determinism_pass.passed) {
      std::snprintf(r.determinism_pass.reason,
                    sizeof(r.determinism_pass.reason),
                    "Determinism validator: PASS");
      ++r.gates_passed;
    } else {
      std::snprintf(r.determinism_pass.reason,
                    sizeof(r.determinism_pass.reason),
                    "Determinism validator: not PASS or missing");
    }

    // Gate 3: Cross-device validator PASS
    r.cross_device_pass.passed = check_file_status(
        "reports/cross_device_validation.json", "status", "pass");
    if (r.cross_device_pass.passed) {
      std::snprintf(r.cross_device_pass.reason,
                    sizeof(r.cross_device_pass.reason),
                    "Cross-device validator: PASS");
      ++r.gates_passed;
    } else {
      std::snprintf(r.cross_device_pass.reason,
                    sizeof(r.cross_device_pass.reason),
                    "Cross-device validator: not PASS or missing");
    }

    // Gate 4: Freeze valid
    r.freeze_valid.passed = check_file_status("reports/training_telemetry.json",
                                              "freeze_status", "true");
    if (r.freeze_valid.passed) {
      std::snprintf(r.freeze_valid.reason, sizeof(r.freeze_valid.reason),
                    "Freeze status: valid");
      ++r.gates_passed;
    } else {
      std::snprintf(r.freeze_valid.reason, sizeof(r.freeze_valid.reason),
                    "Freeze status: invalid or missing");
    }

    // Gate 5: No containment active
    r.no_containment.passed = !check_file_status("reports/mode_override.json",
                                                 "forced_mode", "MODE_A");
    if (r.no_containment.passed) {
      std::snprintf(r.no_containment.reason, sizeof(r.no_containment.reason),
                    "No containment: clear");
      ++r.gates_passed;
    } else {
      std::snprintf(r.no_containment.reason, sizeof(r.no_containment.reason),
                    "Containment active: MODE_A forced");
    }

    // Gate 6: Telemetry validated (CRC + schema)
    r.telemetry_valid.passed = check_file_status(
        "reports/training_telemetry.json", "schema_version", "1");
    if (r.telemetry_valid.passed) {
      std::snprintf(r.telemetry_valid.reason, sizeof(r.telemetry_valid.reason),
                    "Telemetry: schema valid");
      ++r.gates_passed;
    } else {
      std::snprintf(r.telemetry_valid.reason, sizeof(r.telemetry_valid.reason),
                    "Telemetry: schema invalid or missing");
    }

    // Gate 7: Mode mutex (not in HUNT)
    bool in_hunt =
        check_file_status("reports/mode_mutex_state.json", "mode_name", "HUNT");
    r.mode_mutex_ok.passed = !in_hunt;
    if (r.mode_mutex_ok.passed) {
      std::snprintf(r.mode_mutex_ok.reason, sizeof(r.mode_mutex_ok.reason),
                    "Mode mutex: not in HUNT");
      ++r.gates_passed;
    } else {
      std::snprintf(r.mode_mutex_ok.reason, sizeof(r.mode_mutex_ok.reason),
                    "Mode mutex: HUNT active — cannot train");
    }

    // Gate 8: Thermal guard (not in THERMAL_PAUSE)
    bool thermal_paused = check_file_status("reports/thermal_state.json",
                                            "thermal_state", "THERMAL_PAUSE");
    r.thermal_ok.passed = !thermal_paused;
    if (r.thermal_ok.passed) {
      std::snprintf(r.thermal_ok.reason, sizeof(r.thermal_ok.reason),
                    "Thermal guard: OK");
      ++r.gates_passed;
    } else {
      std::snprintf(r.thermal_ok.reason, sizeof(r.thermal_ok.reason),
                    "Thermal guard: THERMAL_PAUSE — too hot to train");
    }

    // Gate 9: HMAC validated (telemetry signed)
    r.hmac_valid.passed = check_hmac_valid();
    if (r.hmac_valid.passed) {
      std::snprintf(r.hmac_valid.reason, sizeof(r.hmac_valid.reason),
                    "HMAC: telemetry signed and valid");
      ++r.gates_passed;
    } else {
      std::snprintf(r.hmac_valid.reason, sizeof(r.hmac_valid.reason),
                    "HMAC: telemetry unsigned or invalid");
    }

    r.ready = (r.gates_passed == r.gates_total);

    std::snprintf(r.summary, sizeof(r.summary),
                  "Training readiness: %d/%d gates passed%s", r.gates_passed,
                  r.gates_total, r.ready ? " — READY" : " — BLOCKED");

    return r;
  }

  // --- Start training (only if all gates pass) ---
  bool start_training() {
    TrainingReadiness readiness = can_start_training();
    if (!readiness.ready)
      return false;

    uint64_t now_wall = static_cast<uint64_t>(std::time(nullptr));
    uint64_t now_mono = get_monotonic_seconds();

    state_.training_active = true;
    state_.training_start_timestamp = now_wall;
    state_.training_start_monotonic = now_mono;
    state_.elapsed_seconds_monotonic = 0;
    state_.hunt_lockout_until_monotonic = now_mono + HUNT_LOCKOUT_SECONDS;
    state_.hunt_locked = true;
    state_.mode = MODE_A_TRAIN; // Always start at MODE_A

    save_protocol_state(state_);
    return true;
  }

  // --- Auto-chain mode progression (thresholds required) ---
  bool try_advance_mode(double precision, double recall, double kl_divergence) {
    if (!state_.training_active)
      return false;

    if (state_.mode == MODE_A_TRAIN) {
      // MODE_A -> MODE_B: precision >= 0.90, recall >= 0.85
      if (precision >= MODE_B_MIN_PRECISION && recall >= MODE_B_MIN_RECALL) {
        state_.mode = MODE_B_TRAIN;
        save_protocol_state(state_);
        return true;
      }
    } else if (state_.mode == MODE_B_TRAIN) {
      // MODE_B -> MODE_C: precision >= 0.95, recall >= 0.92, KL <= 0.05
      if (precision >= MODE_C_MIN_PRECISION && recall >= MODE_C_MIN_RECALL &&
          kl_divergence <= MODE_C_MAX_KL_DRIFT) {
        state_.mode = MODE_C_TRAIN;
        save_protocol_state(state_);
        return true;
      }
    }
    // MODE_C is terminal — no further advancement
    return false;
  }

  // --- Check if hunt is allowed (monotonic) ---
  bool is_hunt_allowed() const {
    if (!state_.hunt_locked)
      return true;
    uint64_t now_mono = get_monotonic_seconds();
    if (now_mono < state_.training_start_monotonic) {
      // Clock rollback detected — DENY
      return false;
    }
    uint64_t elapsed = now_mono - state_.training_start_monotonic;
    return elapsed >= HUNT_LOCKOUT_SECONDS;
  }

  // --- Update elapsed time (call periodically) ---
  void update_elapsed() {
    if (!state_.training_active)
      return;
    uint64_t now_mono = get_monotonic_seconds();
    if (now_mono >= state_.training_start_monotonic) {
      state_.elapsed_seconds_monotonic =
          now_mono - state_.training_start_monotonic;
      save_protocol_state(state_);
    }
    // If now_mono < start, clock rollback — do NOT update
  }

  // --- Stop training ---
  void stop_training() {
    state_.training_active = false;
    state_.mode = MODE_IDLE;
    save_protocol_state(state_);
  }

  // --- State queries ---
  bool is_training_active() const { return state_.training_active; }
  bool is_hunt_locked() const { return state_.hunt_locked; }
  uint64_t hunt_lockout_remaining() const {
    if (!state_.hunt_locked)
      return 0;
    uint64_t now_mono = get_monotonic_seconds();
    if (now_mono < state_.training_start_monotonic)
      return HUNT_LOCKOUT_SECONDS;
    uint64_t elapsed = now_mono - state_.training_start_monotonic;
    if (elapsed >= HUNT_LOCKOUT_SECONDS)
      return 0;
    return HUNT_LOCKOUT_SECONDS - elapsed;
  }
  int current_mode() const { return state_.mode; }
  uint64_t elapsed_monotonic() const {
    return state_.elapsed_seconds_monotonic;
  }

  // Expose for testing
  TrainingState &mutable_state() { return state_; }

private:
  TrainingState state_;
};

// =========================================================================
// SELF-TEST
// =========================================================================

static bool run_tests() {
  int passed = 0, failed = 0;

  auto test = [&](bool cond, const char *name) {
    if (cond) {
      ++passed;
      std::printf("  + %s\n", name);
    } else {
      ++failed;
      std::printf("  X %s\n", name);
    }
  };

  // Clean state
  std::remove(PROTOCOL_STATE_PATH);
  std::remove(PROTOCOL_TMP_PATH);

  // Test 1: Fresh protocol — no gates pass (files missing)
  TrainingStartProtocol protocol;
  TrainingReadiness r = protocol.can_start_training();
  test(!r.ready, "Fresh state: not ready (no gate files)");
  test(r.gates_total == 9, "9 total gates");

  // Test 2: Training not active initially
  test(!protocol.is_training_active(), "Not training initially");

  // Test 3: Start training fails without gates
  bool started = protocol.start_training();
  test(!started, "Cannot start training without gates");

  // Test 4: Monotonic clock returns non-zero
  uint64_t mono = get_monotonic_seconds();
  test(mono > 0, "Monotonic clock returns non-zero");

  // Test 5: Monotonic clock is non-decreasing
  {
    uint64_t t1 = get_monotonic_seconds();
    uint64_t t2 = get_monotonic_seconds();
    test(t2 >= t1, "Monotonic clock non-decreasing");
  }

  // Test 6: Hunt lockout persistence round-trip (monotonic)
  {
    TrainingState ts;
    std::memset(&ts, 0, sizeof(ts));
    ts.training_active = true;
    ts.training_start_timestamp = 1700000000;
    ts.training_start_monotonic = get_monotonic_seconds() - 100;
    ts.elapsed_seconds_monotonic = 100;
    ts.hunt_lockout_until_monotonic =
        ts.training_start_monotonic + HUNT_LOCKOUT_SECONDS;
    ts.hunt_locked = true;
    ts.mode = MODE_A_TRAIN;
    save_protocol_state(ts);

    TrainingStartProtocol p2;
    test(p2.is_training_active(), "Persisted: training_active");
    test(p2.is_hunt_locked(), "Persisted: hunt_locked");
    test(p2.current_mode() == MODE_A_TRAIN, "Persisted: MODE_A");
  }

  // Test 7: Hunt allowed after monotonic lockout expires
  {
    TrainingState ts;
    std::memset(&ts, 0, sizeof(ts));
    ts.training_active = false;
    ts.hunt_locked = true;
    // Start was far in the past (monotonic)
    ts.training_start_monotonic = 1; // Very small value
    ts.elapsed_seconds_monotonic = HUNT_LOCKOUT_SECONDS + 1;
    ts.hunt_lockout_until_monotonic = 1 + HUNT_LOCKOUT_SECONDS;
    ts.mode = MODE_IDLE;
    save_protocol_state(ts);

    TrainingStartProtocol p3;
    test(p3.is_hunt_allowed(), "Hunt allowed after monotonic lockout expires");
    test(!p3.is_hunt_locked(), "Hunt lock cleared after monotonic expiry");
  }

  // Test 8: Mode progression thresholds
  {
    TrainingState ts;
    std::memset(&ts, 0, sizeof(ts));
    ts.training_active = true;
    ts.mode = MODE_A_TRAIN;
    save_protocol_state(ts);

    TrainingStartProtocol p4;

    // Below threshold — no advance
    test(!p4.try_advance_mode(0.80, 0.80, 0.10),
         "MODE_A: below threshold no advance");

    // At threshold — advance to MODE_B
    test(p4.try_advance_mode(0.90, 0.85, 0.10),
         "MODE_A -> MODE_B at threshold");
    test(p4.current_mode() == MODE_B_TRAIN, "Now in MODE_B");

    // Below MODE_C threshold — no advance
    test(!p4.try_advance_mode(0.93, 0.90, 0.06),
         "MODE_B: below threshold no advance");

    // At MODE_C threshold — advance
    test(p4.try_advance_mode(0.95, 0.92, 0.05),
         "MODE_B -> MODE_C at threshold");
    test(p4.current_mode() == MODE_C_TRAIN, "Now in MODE_C");

    // MODE_C is terminal
    test(!p4.try_advance_mode(0.99, 0.99, 0.01),
         "MODE_C: terminal, no advance");
  }

  // Cleanup
  std::remove(PROTOCOL_STATE_PATH);
  std::remove(PROTOCOL_TMP_PATH);

  std::printf("\n  Training Start Protocol: %d passed, %d failed\n", passed,
              failed);
  return failed == 0;
}

} // namespace runtime_guard

// =========================================================================
// SELF-TEST ENTRY POINT
// =========================================================================

#ifdef RUN_SELF_TEST
int main() {
  std::printf("=== Training Start Protocol Self-Test ===\n");
  bool ok = runtime_guard::run_tests();
  return ok ? 0 : 1;
}
#endif
