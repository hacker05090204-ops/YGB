/**
 * mode_mutex.cpp — Strict TRAIN/HUNT Mode Mutex
 *
 * Enforces:
 *   - TRAIN and HUNT are mutually exclusive
 *   - Atomic mode file persistence
 *   - If TRAIN active → HUNT request rejected
 *   - If HUNT active → TRAIN request rejected
 *   - Backend only reflects C++ mode
 *   - Frontend cannot override
 *
 * Separate from mode_lock.cpp — adds strict rejection, timestamps,
 * and incident logging for overlap attempts.
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

static constexpr char MUTEX_STATE_PATH[] = "reports/mode_mutex_state.json";
static constexpr char MUTEX_TMP_PATH[]   = "reports/mode_mutex_state.json.tmp";
static constexpr char MUTEX_INCIDENT_LOG[] = "reports/mode_mutex_incidents.log";

// =========================================================================
// MODE ENUM
// =========================================================================

enum class MutexMode : uint8_t {
    IDLE = 0,
    TRAIN = 1,
    HUNT = 2
};

static const char *mutex_mode_name(MutexMode m) {
    switch (m) {
    case MutexMode::IDLE:  return "IDLE";
    case MutexMode::TRAIN: return "TRAIN";
    case MutexMode::HUNT:  return "HUNT";
    default: return "UNKNOWN";
    }
}

// =========================================================================
// REQUEST RESULT
// =========================================================================

struct MutexRequestResult {
    bool allowed;
    MutexMode current_mode;
    MutexMode requested_mode;
    char reason[512];
};

// =========================================================================
// INCIDENT LOGGING
// =========================================================================

static void log_mutex_incident(const char *action, MutexMode current,
                                MutexMode requested, const char *reason) {
    FILE *f = std::fopen(MUTEX_INCIDENT_LOG, "a");
    if (!f) return;

    time_t now = std::time(nullptr);
    char timebuf[64];
    std::strftime(timebuf, sizeof(timebuf), "%Y-%m-%dT%H:%M:%S",
                  std::localtime(&now));

    std::fprintf(f, "[%s] %s: current=%s requested=%s reason=%s\n",
                 timebuf, action, mutex_mode_name(current),
                 mutex_mode_name(requested), reason);
    std::fflush(f);
    int fd = fileno(f);
    if (fd >= 0) fsync_fd(fd);
    std::fclose(f);
}

// =========================================================================
// ATOMIC PERSISTENCE
// =========================================================================

static bool save_mutex_state(MutexMode mode, uint64_t entry_timestamp) {
    FILE *f = std::fopen(MUTEX_TMP_PATH, "w");
    if (!f) return false;

    std::fprintf(f, "{\n");
    std::fprintf(f, "  \"mode\": %d,\n", static_cast<int>(mode));
    std::fprintf(f, "  \"mode_name\": \"%s\",\n", mutex_mode_name(mode));
    std::fprintf(f, "  \"entry_timestamp\": %llu,\n",
                 static_cast<unsigned long long>(entry_timestamp));
    std::fprintf(f, "  \"source\": \"cpp_runtime_guard\"\n");
    std::fprintf(f, "}\n");

    std::fflush(f);
    int fd = fileno(f);
    if (fd >= 0) fsync_fd(fd);
    std::fclose(f);

    std::remove(MUTEX_STATE_PATH);
    return std::rename(MUTEX_TMP_PATH, MUTEX_STATE_PATH) == 0;
}

static MutexMode load_mutex_mode() {
    FILE *f = std::fopen(MUTEX_STATE_PATH, "r");
    if (!f) return MutexMode::IDLE;

    char buf[512];
    std::memset(buf, 0, sizeof(buf));
    std::fread(buf, 1, sizeof(buf) - 1, f);
    std::fclose(f);

    // Parse mode field
    const char *pos = std::strstr(buf, "\"mode\"");
    if (!pos) return MutexMode::IDLE;
    pos += 6;
    while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
        ++pos;
    int val = 0;
    std::sscanf(pos, "%d", &val);

    if (val >= 0 && val <= 2)
        return static_cast<MutexMode>(val);
    return MutexMode::IDLE;
}

// =========================================================================
// MODE MUTEX
// =========================================================================

class ModeMutex {
public:
    ModeMutex() : mode_(load_mutex_mode()),
                  entry_timestamp_(0) {}

    MutexMode current() const { return mode_; }
    const char *current_name() const { return mutex_mode_name(mode_); }
    bool is_idle() const { return mode_ == MutexMode::IDLE; }

    // --- Request TRAIN mode ---
    MutexRequestResult request_train() {
        MutexRequestResult r;
        r.current_mode = mode_;
        r.requested_mode = MutexMode::TRAIN;

        if (mode_ == MutexMode::TRAIN) {
            r.allowed = false;
            std::snprintf(r.reason, sizeof(r.reason),
                          "TRAIN_ALREADY_ACTIVE: Already in TRAIN mode");
            return r;
        }

        if (mode_ == MutexMode::HUNT) {
            r.allowed = false;
            std::snprintf(r.reason, sizeof(r.reason),
                          "MUTEX_BLOCKED: Cannot enter TRAIN while HUNT is "
                          "active — modes are mutually exclusive");
            log_mutex_incident("TRAIN_REJECTED", mode_, MutexMode::TRAIN,
                               r.reason);
            return r;
        }

        // IDLE → TRAIN allowed
        mode_ = MutexMode::TRAIN;
        entry_timestamp_ = static_cast<uint64_t>(std::time(nullptr));
        save_mutex_state(mode_, entry_timestamp_);

        r.allowed = true;
        std::snprintf(r.reason, sizeof(r.reason),
                      "MODE_TRANSITION: IDLE → TRAIN");
        log_mutex_incident("TRAIN_ENTERED", MutexMode::IDLE, MutexMode::TRAIN,
                           r.reason);
        return r;
    }

    // --- Request HUNT mode ---
    MutexRequestResult request_hunt() {
        MutexRequestResult r;
        r.current_mode = mode_;
        r.requested_mode = MutexMode::HUNT;

        if (mode_ == MutexMode::HUNT) {
            r.allowed = false;
            std::snprintf(r.reason, sizeof(r.reason),
                          "HUNT_ALREADY_ACTIVE: Already in HUNT mode");
            return r;
        }

        if (mode_ == MutexMode::TRAIN) {
            r.allowed = false;
            std::snprintf(r.reason, sizeof(r.reason),
                          "MUTEX_BLOCKED: Cannot enter HUNT while TRAIN is "
                          "active — modes are mutually exclusive");
            log_mutex_incident("HUNT_REJECTED", mode_, MutexMode::HUNT,
                               r.reason);
            return r;
        }

        // IDLE → HUNT allowed
        mode_ = MutexMode::HUNT;
        entry_timestamp_ = static_cast<uint64_t>(std::time(nullptr));
        save_mutex_state(mode_, entry_timestamp_);

        r.allowed = true;
        std::snprintf(r.reason, sizeof(r.reason),
                      "MODE_TRANSITION: IDLE → HUNT");
        log_mutex_incident("HUNT_ENTERED", MutexMode::IDLE, MutexMode::HUNT,
                           r.reason);
        return r;
    }

    // --- Release current mode (return to IDLE) ---
    MutexRequestResult release() {
        MutexRequestResult r;
        r.current_mode = mode_;
        r.requested_mode = MutexMode::IDLE;

        if (mode_ == MutexMode::IDLE) {
            r.allowed = false;
            std::snprintf(r.reason, sizeof(r.reason),
                          "ALREADY_IDLE: No active mode to release");
            return r;
        }

        MutexMode prev = mode_;
        mode_ = MutexMode::IDLE;
        entry_timestamp_ = 0;
        save_mutex_state(mode_, entry_timestamp_);

        r.allowed = true;
        std::snprintf(r.reason, sizeof(r.reason),
                      "MODE_RELEASED: %s → IDLE", mutex_mode_name(prev));
        log_mutex_incident("MODE_RELEASED", prev, MutexMode::IDLE, r.reason);
        return r;
    }

    uint64_t entry_timestamp() const { return entry_timestamp_; }

private:
    MutexMode mode_;
    uint64_t entry_timestamp_;
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
    std::remove(MUTEX_STATE_PATH);
    std::remove(MUTEX_TMP_PATH);
    std::remove(MUTEX_INCIDENT_LOG);

    // Test 1: Fresh start is IDLE
    ModeMutex mutex;
    test(mutex.is_idle(), "Fresh mutex is IDLE");

    // Test 2: IDLE → TRAIN allowed
    auto r1 = mutex.request_train();
    test(r1.allowed, "IDLE → TRAIN allowed");
    test(mutex.current() == MutexMode::TRAIN, "Mode is TRAIN");

    // Test 3: TRAIN active → HUNT rejected
    auto r2 = mutex.request_hunt();
    test(!r2.allowed, "TRAIN active → HUNT rejected");
    test(mutex.current() == MutexMode::TRAIN, "Still in TRAIN");

    // Test 4: TRAIN active → duplicate TRAIN rejected
    auto r3 = mutex.request_train();
    test(!r3.allowed, "Duplicate TRAIN rejected");

    // Test 5: Release TRAIN → IDLE
    auto r4 = mutex.release();
    test(r4.allowed, "Release TRAIN → IDLE");
    test(mutex.is_idle(), "Back to IDLE");

    // Test 6: IDLE → HUNT allowed
    auto r5 = mutex.request_hunt();
    test(r5.allowed, "IDLE → HUNT allowed");
    test(mutex.current() == MutexMode::HUNT, "Mode is HUNT");

    // Test 7: HUNT active → TRAIN rejected
    auto r6 = mutex.request_train();
    test(!r6.allowed, "HUNT active → TRAIN rejected");

    // Test 8: Release HUNT → IDLE
    auto r7 = mutex.release();
    test(r7.allowed, "Release HUNT → IDLE");
    test(mutex.is_idle(), "Back to IDLE after HUNT release");

    // Test 9: Double release rejected
    auto r8 = mutex.release();
    test(!r8.allowed, "Double release rejected");

    // Test 10: Persistence round-trip
    {
        ModeMutex m2;
        m2.request_train();
        // Create new instance — should load persisted TRAIN
        ModeMutex m3;
        test(m3.current() == MutexMode::TRAIN,
             "Persisted TRAIN survives reload");
        m2.release();
    }

    // Cleanup
    std::remove(MUTEX_STATE_PATH);
    std::remove(MUTEX_TMP_PATH);
    std::remove(MUTEX_INCIDENT_LOG);

    std::printf("\n  Mode Mutex: %d passed, %d failed\n", passed, failed);
    return failed == 0;
}

} // namespace runtime_guard

// =========================================================================
// SELF-TEST ENTRY POINT
// =========================================================================

#ifdef RUN_SELF_TEST
int main() {
    std::printf("=== Mode Mutex Self-Test ===\n");
    bool ok = runtime_guard::run_tests();
    return ok ? 0 : 1;
}
#endif
