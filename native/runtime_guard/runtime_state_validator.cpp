/**
 * runtime_state_validator.cpp — Runtime State Validator
 *
 * On load validates:
 *   1. JSON parses correctly
 *   2. Required fields present
 *   3. Schema version matches
 *   4. determinism_status == true
 *   5. freeze_status == true (if certified)
 *   6. CRC32 hash matches
 *
 * If ANY fail:
 *   - Set runtime_status = CORRUPTED
 *   - Force MODE_A
 *   - Disable HUNT
 *   - Log incident
 *
 * NO silent fallback. NO partial trust.
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

static constexpr int EXPECTED_SCHEMA_VERSION = 1;
static constexpr char TELEMETRY_PATH[] = "reports/training_telemetry.json";
static constexpr char INCIDENT_PATH[] = "reports/validation_incidents.log";
static constexpr char MODE_OVERRIDE_PATH[] = "reports/mode_override.json";

// =========================================================================
// ENUMS
// =========================================================================

enum class RuntimeStatus : uint8_t {
    OK = 0,
    CORRUPTED = 1,
    MISSING = 2,
    VERSION_MISMATCH = 3,
    FIELD_MISSING = 4,
    DETERMINISM_FAILED = 5,
    FREEZE_FAILED = 6,
    CRC_MISMATCH = 7,
    // Phase 9: Fail-safe enforcement
    HMAC_INVALID = 8,
    CLOCK_ROLLBACK = 9,
    THERMAL_HALT = 10,
    NOT_PAIRED = 11,
    GOVERNANCE_LOCKED = 12
};

static const char *status_name(RuntimeStatus s) {
    switch (s) {
    case RuntimeStatus::OK: return "OK";
    case RuntimeStatus::CORRUPTED: return "CORRUPTED";
    case RuntimeStatus::MISSING: return "MISSING";
    case RuntimeStatus::VERSION_MISMATCH: return "VERSION_MISMATCH";
    case RuntimeStatus::FIELD_MISSING: return "FIELD_MISSING";
    case RuntimeStatus::DETERMINISM_FAILED: return "DETERMINISM_FAILED";
    case RuntimeStatus::FREEZE_FAILED: return "FREEZE_FAILED";
    case RuntimeStatus::CRC_MISMATCH: return "CRC_MISMATCH";
    case RuntimeStatus::HMAC_INVALID: return "HMAC_INVALID";
    case RuntimeStatus::CLOCK_ROLLBACK: return "CLOCK_ROLLBACK";
    case RuntimeStatus::THERMAL_HALT: return "THERMAL_HALT";
    case RuntimeStatus::NOT_PAIRED: return "NOT_PAIRED";
    case RuntimeStatus::GOVERNANCE_LOCKED: return "GOVERNANCE_LOCKED";
    default: return "UNKNOWN";
    }
}

// =========================================================================
// CRC32 (same table-based impl as training_telemetry.cpp)
// =========================================================================

static uint32_t crc32_table[256];
static bool crc32_table_init = false;

static void init_crc32_table() {
    if (crc32_table_init) return;
    for (uint32_t i = 0; i < 256; ++i) {
        uint32_t crc = i;
        for (int j = 0; j < 8; ++j) {
            if (crc & 1)
                crc = (crc >> 1) ^ 0xEDB88320;
            else
                crc >>= 1;
        }
        crc32_table[i] = crc;
    }
    crc32_table_init = true;
}

static uint32_t compute_crc32(const char *data, size_t length) {
    init_crc32_table();
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < length; ++i) {
        uint8_t byte = static_cast<uint8_t>(data[i]);
        crc = (crc >> 8) ^ crc32_table[(crc ^ byte) & 0xFF];
    }
    return crc ^ 0xFFFFFFFF;
}

// =========================================================================
// JSON PARSERS (no external deps)
// =========================================================================

static bool has_field(const char *buf, const char *key) {
    return std::strstr(buf, key) != nullptr;
}

static int parse_int_after(const char *buf, const char *key) {
    const char *pos = std::strstr(buf, key);
    if (!pos) return -1;
    pos += std::strlen(key);
    while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
        ++pos;
    int val = 0;
    std::sscanf(pos, "%d", &val);
    return val;
}

static uint32_t parse_uint32_after(const char *buf, const char *key) {
    const char *pos = std::strstr(buf, key);
    if (!pos) return 0;
    pos += std::strlen(key);
    while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
        ++pos;
    unsigned int val = 0;
    std::sscanf(pos, "%u", &val);
    return static_cast<uint32_t>(val);
}

static bool parse_bool_after(const char *buf, const char *key) {
    const char *pos = std::strstr(buf, key);
    if (!pos) return false;
    pos += std::strlen(key);
    while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
        ++pos;
    return (std::strncmp(pos, "true", 4) == 0);
}

static double parse_double_after(const char *buf, const char *key) {
    const char *pos = std::strstr(buf, key);
    if (!pos) return 0.0;
    pos += std::strlen(key);
    while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
        ++pos;
    double val = 0.0;
    std::sscanf(pos, "%lf", &val);
    return val;
}

static uint64_t parse_uint64_after(const char *buf, const char *key) {
    const char *pos = std::strstr(buf, key);
    if (!pos) return 0;
    pos += std::strlen(key);
    while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
        ++pos;
    unsigned long long val = 0;
    std::sscanf(pos, "%llu", &val);
    return static_cast<uint64_t>(val);
}

// =========================================================================
// RECOMPUTE CRC (must match training_telemetry.cpp format)
// =========================================================================

static uint32_t recompute_crc(const char *buf) {
    int schema_version = parse_int_after(buf, "schema_version");
    bool determinism = parse_bool_after(buf, "determinism_status");
    bool freeze = parse_bool_after(buf, "freeze_status");
    double precision = parse_double_after(buf, "precision");
    double recall = parse_double_after(buf, "recall");
    double kl = parse_double_after(buf, "kl_divergence");
    double ece = parse_double_after(buf, "ece");
    double loss = parse_double_after(buf, "loss");
    double temp = parse_double_after(buf, "gpu_temperature");
    int epoch = parse_int_after(buf, "epoch");
    int batch = parse_int_after(buf, "batch_size");
    uint64_t timestamp = parse_uint64_after(buf, "timestamp");
    uint64_t mono = parse_uint64_after(buf, "monotonic_timestamp");
    uint64_t start = parse_uint64_after(buf, "monotonic_start_time");
    uint64_t wall = parse_uint64_after(buf, "wall_clock_unix");
    double dur = parse_double_after(buf, "training_duration_seconds");
    double rate = parse_double_after(buf, "samples_per_second");

    char payload[2048];
    int len = std::snprintf(payload, sizeof(payload),
        "v%d|det:%d|frz:%d|prec:%.8f|rec:%.8f|kl:%.8f|ece:%.8f|"
        "loss:%.8f|temp:%.8f|epoch:%d|batch:%d|ts:%llu|mono:%llu|"
        "start:%llu|wall:%llu|dur:%.8f|rate:%.8f",
        schema_version,
        determinism ? 1 : 0,
        freeze ? 1 : 0,
        precision, recall, kl, ece,
        loss, temp,
        epoch, batch,
        static_cast<unsigned long long>(timestamp),
        static_cast<unsigned long long>(mono),
        static_cast<unsigned long long>(start),
        static_cast<unsigned long long>(wall),
        dur, rate);
    return compute_crc32(payload, static_cast<size_t>(len));
}

// =========================================================================
// VALIDATION RESULT
// =========================================================================

struct ValidationResult {
    RuntimeStatus status;
    char reason[512];
    bool hunt_disabled;
    bool mode_a_forced;
};

// =========================================================================
// INCIDENT LOGGING
// =========================================================================

static void log_incident(RuntimeStatus status, const char *reason) {
    FILE *f = std::fopen(INCIDENT_PATH, "a");
    if (!f) return;

    time_t now = std::time(nullptr);
    char timebuf[64];
    std::strftime(timebuf, sizeof(timebuf), "%Y-%m-%dT%H:%M:%S",
                  std::localtime(&now));

    std::fprintf(f, "[%s] VALIDATION_INCIDENT: status=%s reason=%s\n",
                 timebuf, status_name(status), reason);
    std::fflush(f);
    int fd = fileno(f);
    if (fd >= 0) fsync_fd(fd);
    std::fclose(f);
}

// =========================================================================
// FORCE MODE_A (write override file)
// =========================================================================

static void force_mode_a() {
    FILE *f = std::fopen(MODE_OVERRIDE_PATH, "w");
    if (!f) return;

    time_t now = std::time(nullptr);
    std::fprintf(f, "{\n");
    std::fprintf(f, "  \"forced_mode\": \"MODE_A\",\n");
    std::fprintf(f, "  \"hunt_disabled\": true,\n");
    std::fprintf(f, "  \"reason\": \"runtime_state_validation_failed\",\n");
    std::fprintf(f, "  \"timestamp\": %lld\n",
                 static_cast<long long>(now));
    std::fprintf(f, "}\n");

    std::fflush(f);
    int fd = fileno(f);
    if (fd >= 0) fsync_fd(fd);
    std::fclose(f);
}

// =========================================================================
// VALIDATE RUNTIME STATE
// =========================================================================

static ValidationResult validate() {
    ValidationResult result;
    std::memset(&result, 0, sizeof(result));
    result.status = RuntimeStatus::OK;
    result.hunt_disabled = false;
    result.mode_a_forced = false;

    // Step 1: Load file
    FILE *f = std::fopen(TELEMETRY_PATH, "r");
    if (!f) {
        result.status = RuntimeStatus::MISSING;
        std::snprintf(result.reason, sizeof(result.reason),
                      "Telemetry file missing: %s", TELEMETRY_PATH);
        result.hunt_disabled = true;
        result.mode_a_forced = true;
        log_incident(result.status, result.reason);
        force_mode_a();
        return result;
    }

    char buf[4096];
    std::memset(buf, 0, sizeof(buf));
    size_t n = std::fread(buf, 1, sizeof(buf) - 1, f);
    std::fclose(f);

    // Step 2: Validate JSON parses (basic check)
    if (n == 0 || !std::strchr(buf, '{') || !std::strchr(buf, '}')) {
        result.status = RuntimeStatus::CORRUPTED;
        std::snprintf(result.reason, sizeof(result.reason),
                      "JSON parse failed: empty or malformed");
        result.hunt_disabled = true;
        result.mode_a_forced = true;
        log_incident(result.status, result.reason);
        force_mode_a();
        return result;
    }

    // Step 3: Validate required fields
    const char *required[] = {
        "schema_version", "determinism_status", "freeze_status", "crc32"
    };
    for (int i = 0; i < 4; ++i) {
        if (!has_field(buf, required[i])) {
            result.status = RuntimeStatus::FIELD_MISSING;
            std::snprintf(result.reason, sizeof(result.reason),
                          "Required field missing: %s", required[i]);
            result.hunt_disabled = true;
            result.mode_a_forced = true;
            log_incident(result.status, result.reason);
            force_mode_a();
            return result;
        }
    }

    // Step 4: Validate schema version
    int version = parse_int_after(buf, "schema_version");
    if (version != EXPECTED_SCHEMA_VERSION) {
        result.status = RuntimeStatus::VERSION_MISMATCH;
        std::snprintf(result.reason, sizeof(result.reason),
                      "Schema version mismatch: got %d, expected %d",
                      version, EXPECTED_SCHEMA_VERSION);
        result.hunt_disabled = true;
        result.mode_a_forced = true;
        log_incident(result.status, result.reason);
        force_mode_a();
        return result;
    }

    // Step 5: Validate determinism_status == true
    bool determinism = parse_bool_after(buf, "determinism_status");
    if (!determinism) {
        result.status = RuntimeStatus::DETERMINISM_FAILED;
        std::snprintf(result.reason, sizeof(result.reason),
                      "determinism_status is false — runtime not deterministic");
        result.hunt_disabled = true;
        result.mode_a_forced = true;
        log_incident(result.status, result.reason);
        force_mode_a();
        return result;
    }

    // Step 6: Validate freeze_status == true (if certified)
    bool freeze = parse_bool_after(buf, "freeze_status");
    if (!freeze) {
        result.status = RuntimeStatus::FREEZE_FAILED;
        std::snprintf(result.reason, sizeof(result.reason),
                      "freeze_status is false — model not frozen for deployment");
        result.hunt_disabled = true;
        result.mode_a_forced = true;
        log_incident(result.status, result.reason);
        force_mode_a();
        return result;
    }

    // Step 7: Validate CRC32
    uint32_t stored_crc = parse_uint32_after(buf, "crc32");
    uint32_t computed_crc = recompute_crc(buf);
    if (stored_crc != computed_crc) {
        result.status = RuntimeStatus::CRC_MISMATCH;
        std::snprintf(result.reason, sizeof(result.reason),
                      "CRC32 mismatch: stored=%u computed=%u — "
                      "telemetry corrupted or tampered",
                      stored_crc, computed_crc);
        result.hunt_disabled = true;
        result.mode_a_forced = true;
        log_incident(result.status, result.reason);
        force_mode_a();
        return result;
    }

    // All core checks passed — now Phase 9 fail-safe enforcement

    // Step 8: HMAC field must be present (unsigned telemetry = rejected)
    if (!has_field(buf, "hmac")) {
        result.status = RuntimeStatus::HMAC_INVALID;
        std::snprintf(result.reason, sizeof(result.reason),
                      "HMAC field missing — unsigned telemetry rejected");
        result.hunt_disabled = true;
        result.mode_a_forced = true;
        log_incident(result.status, result.reason);
        force_mode_a();
        return result;
    }

    // Step 9: Clock rollback detection (monotonic_timestamp must increase)
    uint64_t mono_ts = parse_uint64_after(buf, "monotonic_timestamp");
    uint64_t start_ts = parse_uint64_after(buf, "monotonic_start_time");
    if (mono_ts > 0 && start_ts > 0 && mono_ts < start_ts) {
        result.status = RuntimeStatus::CLOCK_ROLLBACK;
        std::snprintf(result.reason, sizeof(result.reason),
                      "Clock rollback detected: monotonic=%llu < start=%llu",
                      static_cast<unsigned long long>(mono_ts),
                      static_cast<unsigned long long>(start_ts));
        result.hunt_disabled = true;
        result.mode_a_forced = true;
        log_incident(result.status, result.reason);
        force_mode_a();
        return result;
    }

    // Step 10: Thermal over 88°C → HALT training
    double gpu_temp = parse_double_after(buf, "gpu_temperature");
    if (gpu_temp > 88.0) {
        result.status = RuntimeStatus::THERMAL_HALT;
        std::snprintf(result.reason, sizeof(result.reason),
                      "GPU temperature %.1f°C exceeds 88°C thermal limit — HALT",
                      gpu_temp);
        result.hunt_disabled = true;
        result.mode_a_forced = true;
        log_incident(result.status, result.reason);
        force_mode_a();
        return result;
    }

    // Step 11: Governance lock check
    {
        FILE *gov = std::fopen("reports/governance_lock.json", "r");
        if (gov) {
            char gov_buf[256];
            std::memset(gov_buf, 0, sizeof(gov_buf));
            std::fread(gov_buf, 1, sizeof(gov_buf) - 1, gov);
            std::fclose(gov);
            if (std::strstr(gov_buf, "\"locked\": true") ||
                std::strstr(gov_buf, "\"locked\":true")) {
                result.status = RuntimeStatus::GOVERNANCE_LOCKED;
                std::snprintf(result.reason, sizeof(result.reason),
                              "Governance lock active — training blocked");
                result.hunt_disabled = true;
                result.mode_a_forced = true;
                log_incident(result.status, result.reason);
                force_mode_a();
                return result;
            }
        }
    }

    // All checks passed
    std::snprintf(result.reason, sizeof(result.reason),
                  "All validation checks passed (including Phase 9 fail-safe)");
    return result;
}

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

    // Test 1: Missing file → MISSING status
    std::remove(TELEMETRY_PATH);
    std::remove(MODE_OVERRIDE_PATH);
    ValidationResult r1 = validate();
    test(r1.status == RuntimeStatus::MISSING, "Missing file → MISSING");
    test(r1.hunt_disabled, "Missing file → hunt disabled");
    test(r1.mode_a_forced, "Missing file → MODE_A forced");

    // Test 2: Corrupted JSON → CORRUPTED
    {
        FILE *f = std::fopen(TELEMETRY_PATH, "w");
        std::fprintf(f, "this is not json");
        std::fclose(f);
    }
    std::remove(MODE_OVERRIDE_PATH);
    ValidationResult r2 = validate();
    test(r2.status == RuntimeStatus::CORRUPTED, "Malformed JSON → CORRUPTED");

    // Test 3: Missing required field → FIELD_MISSING
    {
        FILE *f = std::fopen(TELEMETRY_PATH, "w");
        std::fprintf(f, "{\n  \"schema_version\": 1\n}\n");
        std::fclose(f);
    }
    std::remove(MODE_OVERRIDE_PATH);
    ValidationResult r3 = validate();
    test(r3.status == RuntimeStatus::FIELD_MISSING,
         "Missing field → FIELD_MISSING");

    // Test 4: Wrong schema version → VERSION_MISMATCH
    {
        FILE *f = std::fopen(TELEMETRY_PATH, "w");
        std::fprintf(f, "{\n"
                        "  \"schema_version\": 99,\n"
                        "  \"determinism_status\": true,\n"
                        "  \"freeze_status\": true,\n"
                        "  \"crc32\": 0\n"
                        "}\n");
        std::fclose(f);
    }
    std::remove(MODE_OVERRIDE_PATH);
    ValidationResult r4 = validate();
    test(r4.status == RuntimeStatus::VERSION_MISMATCH,
         "Wrong schema → VERSION_MISMATCH");

    // Test 5: determinism_status false → DETERMINISM_FAILED
    {
        FILE *f = std::fopen(TELEMETRY_PATH, "w");
        std::fprintf(f, "{\n"
                        "  \"schema_version\": 1,\n"
                        "  \"determinism_status\": false,\n"
                        "  \"freeze_status\": true,\n"
                        "  \"crc32\": 0\n"
                        "}\n");
        std::fclose(f);
    }
    std::remove(MODE_OVERRIDE_PATH);
    ValidationResult r5 = validate();
    test(r5.status == RuntimeStatus::DETERMINISM_FAILED,
         "Determinism false → DETERMINISM_FAILED");

    // Test 6: freeze_status false → FREEZE_FAILED
    {
        FILE *f = std::fopen(TELEMETRY_PATH, "w");
        std::fprintf(f, "{\n"
                        "  \"schema_version\": 1,\n"
                        "  \"determinism_status\": true,\n"
                        "  \"freeze_status\": false,\n"
                        "  \"crc32\": 0\n"
                        "}\n");
        std::fclose(f);
    }
    std::remove(MODE_OVERRIDE_PATH);
    ValidationResult r6 = validate();
    test(r6.status == RuntimeStatus::FREEZE_FAILED,
         "Freeze false → FREEZE_FAILED");

    // Test 7: CRC mismatch → CRC_MISMATCH
    {
        FILE *f = std::fopen(TELEMETRY_PATH, "w");
        std::fprintf(f, "{\n"
                        "  \"schema_version\": 1,\n"
                        "  \"determinism_status\": true,\n"
                        "  \"freeze_status\": true,\n"
                        "  \"precision\": 0.96000000,\n"
                        "  \"recall\": 0.93000000,\n"
                        "  \"kl_divergence\": 0.01500000,\n"
                        "  \"ece\": 0.01200000,\n"
                        "  \"loss\": 0.04500000,\n"
                        "  \"gpu_temperature\": 72.50000000,\n"
                        "  \"epoch\": 42,\n"
                        "  \"batch_size\": 64,\n"
                        "  \"timestamp\": 1700000000,\n"
                        "  \"crc32\": 12345\n"
                        "}\n");
        std::fclose(f);
    }
    std::remove(MODE_OVERRIDE_PATH);
    ValidationResult r7 = validate();
    test(r7.status == RuntimeStatus::CRC_MISMATCH,
         "Wrong CRC → CRC_MISMATCH");

    // Cleanup
    std::remove(TELEMETRY_PATH);
    std::remove(MODE_OVERRIDE_PATH);
    std::remove(INCIDENT_PATH);

    std::printf("\n  Runtime State Validator: %d passed, %d failed\n",
                passed, failed);
    return failed == 0;
}

} // namespace runtime_guard

// =========================================================================
// SELF-TEST ENTRY POINT
// =========================================================================

#ifdef RUN_SELF_TEST
int main() {
    std::printf("=== Runtime State Validator Self-Test ===\n");
    bool ok = runtime_guard::run_tests();
    return ok ? 0 : 1;
}
#endif
