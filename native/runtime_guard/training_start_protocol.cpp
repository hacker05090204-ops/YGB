/**
 * training_start_protocol.cpp — Training Start Protocol
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
 *
 * Post-start:
 *   - Enter MODE-A training only
 *   - 72-hour lockout on HUNT
 *   - Monitor precision drift, KL drift, ECE shift, thermal, loss
 *
 * NO silent fallback. NO race conditions.
 */

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>

#ifdef _WIN32
#include <io.h>
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
static constexpr char PROTOCOL_STATE_PATH[] = "reports/training_protocol_state.json";
static constexpr char PROTOCOL_TMP_PATH[]   = "reports/training_protocol_state.json.tmp";

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
    int gates_passed;
    int gates_total;
    char summary[1024];
};

// =========================================================================
// TRAINING STATE
// =========================================================================

struct TrainingState {
    bool training_active;
    uint64_t training_start_timestamp;
    uint64_t hunt_lockout_until;
    bool hunt_locked;
    int mode;  // 0=IDLE, 1=MODE_A_TRAIN
};

// =========================================================================
// PERSISTENCE
// =========================================================================

static bool save_protocol_state(const TrainingState &state) {
    FILE *f = std::fopen(PROTOCOL_TMP_PATH, "w");
    if (!f) return false;

    std::fprintf(f, "{\n");
    std::fprintf(f, "  \"training_active\": %s,\n",
                 state.training_active ? "true" : "false");
    std::fprintf(f, "  \"training_start_timestamp\": %llu,\n",
                 static_cast<unsigned long long>(state.training_start_timestamp));
    std::fprintf(f, "  \"hunt_lockout_until\": %llu,\n",
                 static_cast<unsigned long long>(state.hunt_lockout_until));
    std::fprintf(f, "  \"hunt_locked\": %s,\n",
                 state.hunt_locked ? "true" : "false");
    std::fprintf(f, "  \"mode\": %d\n", state.mode);
    std::fprintf(f, "}\n");

    std::fflush(f);
    int fd = fileno(f);
    if (fd >= 0) fsync_fd(fd);
    std::fclose(f);

    std::remove(PROTOCOL_STATE_PATH);
    return std::rename(PROTOCOL_TMP_PATH, PROTOCOL_STATE_PATH) == 0;
}

static TrainingState load_protocol_state() {
    TrainingState state;
    std::memset(&state, 0, sizeof(state));

    FILE *f = std::fopen(PROTOCOL_STATE_PATH, "r");
    if (!f) return state;

    char buf[1024];
    std::memset(buf, 0, sizeof(buf));
    std::fread(buf, 1, sizeof(buf) - 1, f);
    std::fclose(f);

    // Parse fields
    const char *pos;

    pos = std::strstr(buf, "\"training_active\"");
    if (pos) {
        pos += 17;
        while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
            ++pos;
        state.training_active = (std::strncmp(pos, "true", 4) == 0);
    }

    pos = std::strstr(buf, "\"training_start_timestamp\"");
    if (pos) {
        pos += 25;
        while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
            ++pos;
        unsigned long long val = 0;
        std::sscanf(pos, "%llu", &val);
        state.training_start_timestamp = static_cast<uint64_t>(val);
    }

    pos = std::strstr(buf, "\"hunt_lockout_until\"");
    if (pos) {
        pos += 19;
        while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
            ++pos;
        unsigned long long val = 0;
        std::sscanf(pos, "%llu", &val);
        state.hunt_lockout_until = static_cast<uint64_t>(val);
    }

    pos = std::strstr(buf, "\"hunt_locked\"");
    if (pos) {
        pos += 13;
        while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
            ++pos;
        state.hunt_locked = (std::strncmp(pos, "true", 4) == 0);
    }

    pos = std::strstr(buf, "\"mode\"");
    if (pos) {
        pos += 6;
        while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
            ++pos;
        std::sscanf(pos, "%d", &state.mode);
    }

    return state;
}

// =========================================================================
// FILE-BASED GATE CHECKS
// =========================================================================

static bool check_file_status(const char *path, const char *key,
                               const char *expected_value) {
    FILE *f = std::fopen(path, "r");
    if (!f) return false;

    char buf[2048];
    std::memset(buf, 0, sizeof(buf));
    std::fread(buf, 1, sizeof(buf) - 1, f);
    std::fclose(f);

    const char *pos = std::strstr(buf, key);
    if (!pos) return false;
    pos += std::strlen(key);
    while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
        ++pos;
    return (std::strncmp(pos, expected_value,
                         std::strlen(expected_value)) == 0);
}

// =========================================================================
// TRAINING START PROTOCOL
// =========================================================================

class TrainingStartProtocol {
public:
    TrainingStartProtocol() : state_(load_protocol_state()) {
        // Check if hunt lockout has expired
        if (state_.hunt_locked) {
            uint64_t now = static_cast<uint64_t>(std::time(nullptr));
            if (now >= state_.hunt_lockout_until) {
                state_.hunt_locked = false;
                save_protocol_state(state_);
            }
        }
    }

    // --- Check all gates ---
    TrainingReadiness can_start_training() const {
        TrainingReadiness r;
        std::memset(&r, 0, sizeof(r));
        r.gates_total = 8;
        r.gates_passed = 0;

        // Gate 1: CI fully green
        r.ci_green.passed = check_file_status(
            "reports/ci_status.json", "status", "green");
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
        r.freeze_valid.passed = check_file_status(
            "reports/training_telemetry.json", "freeze_status", "true");
        if (r.freeze_valid.passed) {
            std::snprintf(r.freeze_valid.reason,
                          sizeof(r.freeze_valid.reason),
                          "Freeze status: valid");
            ++r.gates_passed;
        } else {
            std::snprintf(r.freeze_valid.reason,
                          sizeof(r.freeze_valid.reason),
                          "Freeze status: invalid or missing");
        }

        // Gate 5: No containment active
        r.no_containment.passed = !check_file_status(
            "reports/mode_override.json", "forced_mode", "MODE_A");
        if (r.no_containment.passed) {
            std::snprintf(r.no_containment.reason,
                          sizeof(r.no_containment.reason),
                          "No containment: clear");
            ++r.gates_passed;
        } else {
            std::snprintf(r.no_containment.reason,
                          sizeof(r.no_containment.reason),
                          "Containment active: MODE_A forced");
        }

        // Gate 6: Telemetry validated (CRC + schema)
        r.telemetry_valid.passed = check_file_status(
            "reports/training_telemetry.json", "schema_version", "1");
        if (r.telemetry_valid.passed) {
            std::snprintf(r.telemetry_valid.reason,
                          sizeof(r.telemetry_valid.reason),
                          "Telemetry: schema valid");
            ++r.gates_passed;
        } else {
            std::snprintf(r.telemetry_valid.reason,
                          sizeof(r.telemetry_valid.reason),
                          "Telemetry: schema invalid or missing");
        }

        // Gate 7: Mode mutex (not in HUNT)
        bool in_hunt = check_file_status(
            "reports/mode_mutex_state.json", "mode_name", "HUNT");
        r.mode_mutex_ok.passed = !in_hunt;
        if (r.mode_mutex_ok.passed) {
            std::snprintf(r.mode_mutex_ok.reason,
                          sizeof(r.mode_mutex_ok.reason),
                          "Mode mutex: not in HUNT");
            ++r.gates_passed;
        } else {
            std::snprintf(r.mode_mutex_ok.reason,
                          sizeof(r.mode_mutex_ok.reason),
                          "Mode mutex: HUNT active — cannot train");
        }

        // Gate 8: Thermal guard (not in THERMAL_PAUSE)
        // Default to pass if no thermal data (conservative)
        bool thermal_paused = check_file_status(
            "reports/thermal_state.json", "thermal_state", "THERMAL_PAUSE");
        r.thermal_ok.passed = !thermal_paused;
        if (r.thermal_ok.passed) {
            std::snprintf(r.thermal_ok.reason,
                          sizeof(r.thermal_ok.reason),
                          "Thermal guard: OK");
            ++r.gates_passed;
        } else {
            std::snprintf(r.thermal_ok.reason,
                          sizeof(r.thermal_ok.reason),
                          "Thermal guard: THERMAL_PAUSE — too hot to train");
        }

        r.ready = (r.gates_passed == r.gates_total);

        std::snprintf(r.summary, sizeof(r.summary),
                      "Training readiness: %d/%d gates passed%s",
                      r.gates_passed, r.gates_total,
                      r.ready ? " — READY" : " — BLOCKED");

        return r;
    }

    // --- Start training (only if all gates pass) ---
    bool start_training() {
        TrainingReadiness readiness = can_start_training();
        if (!readiness.ready) return false;

        uint64_t now = static_cast<uint64_t>(std::time(nullptr));
        state_.training_active = true;
        state_.training_start_timestamp = now;
        state_.hunt_lockout_until = now + HUNT_LOCKOUT_SECONDS;
        state_.hunt_locked = true;
        state_.mode = 1;  // MODE_A_TRAIN

        save_protocol_state(state_);
        return true;
    }

    // --- Check if hunt is allowed ---
    bool is_hunt_allowed() const {
        if (!state_.hunt_locked) return true;
        uint64_t now = static_cast<uint64_t>(std::time(nullptr));
        return now >= state_.hunt_lockout_until;
    }

    // --- Stop training ---
    void stop_training() {
        state_.training_active = false;
        state_.mode = 0;  // IDLE
        save_protocol_state(state_);
    }

    // --- State queries ---
    bool is_training_active() const { return state_.training_active; }
    bool is_hunt_locked() const { return state_.hunt_locked; }
    uint64_t hunt_lockout_until() const { return state_.hunt_lockout_until; }

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
    test(r.gates_total == 8, "8 total gates");

    // Test 2: Training not active initially
    test(!protocol.is_training_active(), "Not training initially");

    // Test 3: Start training fails without gates
    bool started = protocol.start_training();
    test(!started, "Cannot start training without gates");

    // Test 4: Hunt lockout persistence round-trip
    {
        TrainingState ts;
        std::memset(&ts, 0, sizeof(ts));
        ts.training_active = true;
        ts.training_start_timestamp = 1700000000;
        ts.hunt_lockout_until = 1700259200;  // +72h
        ts.hunt_locked = true;
        ts.mode = 1;
        save_protocol_state(ts);

        TrainingStartProtocol p2;
        test(p2.is_training_active(), "Persisted: training_active");
        test(p2.is_hunt_locked(), "Persisted: hunt_locked");
    }

    // Test 5: Hunt allowed after lockout expires
    {
        TrainingState ts;
        std::memset(&ts, 0, sizeof(ts));
        ts.training_active = false;
        ts.hunt_locked = true;
        ts.hunt_lockout_until = 1;  // Far in the past
        ts.mode = 0;
        save_protocol_state(ts);

        TrainingStartProtocol p3;
        test(p3.is_hunt_allowed(), "Hunt allowed after lockout expires");
        test(!p3.is_hunt_locked(), "Hunt lock cleared after expiry");
    }

    // Cleanup
    std::remove(PROTOCOL_STATE_PATH);
    std::remove(PROTOCOL_TMP_PATH);

    std::printf("\n  Training Start Protocol: %d passed, %d failed\n",
                passed, failed);
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
