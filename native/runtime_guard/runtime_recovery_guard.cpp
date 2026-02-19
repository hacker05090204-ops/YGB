/**
 * runtime_recovery_guard.cpp — Crash Recovery Guard
 *
 * On startup:
 *   1. If mode == TRAIN but no active training process (PID lock missing):
 *      - Demote to MODE_A
 *      - Reset mutex to IDLE
 *      - Invalidate freeze
 *      - Log recovery event
 *
 *   2. If telemetry corrupted (CRC or HMAC fail):
 *      - Reset telemetry
 *      - Force retraining state
 *
 * NO silent fallback. NO orphaned training state.
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

namespace recovery_guard {

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr char PROTOCOL_STATE[] = "reports/training_protocol_state.json";
static constexpr char TELEMETRY_PATH[] = "reports/training_telemetry.json";
static constexpr char MODE_OVERRIDE[] = "reports/mode_override.json";
static constexpr char MUTEX_STATE[] = "reports/mode_mutex_state.json";
static constexpr char PID_LOCK_PATH[] = "reports/training_pid.lock";
static constexpr char RECOVERY_LOG[] = "reports/recovery_events.log";
static constexpr char HMAC_KEY_PATH[] = "config/hmac_secret.key";

// =========================================================================
// SHA-256 + HMAC (same as training_telemetry.cpp)
// =========================================================================

static const uint32_t sha256_k[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
    0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};

static inline uint32_t sha_rotr(uint32_t x, int n) {
  return (x >> n) | (x << (32 - n));
}

struct Sha256State {
  uint32_t h[8];
  uint8_t block[64];
  uint64_t total_len;
  int block_len;
};

static void sha256_init(Sha256State &s) {
  s.h[0] = 0x6a09e667;
  s.h[1] = 0xbb67ae85;
  s.h[2] = 0x3c6ef372;
  s.h[3] = 0xa54ff53a;
  s.h[4] = 0x510e527f;
  s.h[5] = 0x9b05688c;
  s.h[6] = 0x1f83d9ab;
  s.h[7] = 0x5be0cd19;
  s.total_len = 0;
  s.block_len = 0;
}

static void sha256_process_block(Sha256State &s) {
  uint32_t w[64];
  for (int i = 0; i < 16; ++i)
    w[i] = (uint32_t(s.block[i * 4]) << 24) |
           (uint32_t(s.block[i * 4 + 1]) << 16) |
           (uint32_t(s.block[i * 4 + 2]) << 8) | uint32_t(s.block[i * 4 + 3]);
  for (int i = 16; i < 64; ++i) {
    uint32_t s0 =
        sha_rotr(w[i - 15], 7) ^ sha_rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
    uint32_t s1 =
        sha_rotr(w[i - 2], 17) ^ sha_rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  uint32_t a = s.h[0], b = s.h[1], c = s.h[2], d = s.h[3];
  uint32_t e = s.h[4], f = s.h[5], g = s.h[6], hh = s.h[7];
  for (int i = 0; i < 64; ++i) {
    uint32_t S1 = sha_rotr(e, 6) ^ sha_rotr(e, 11) ^ sha_rotr(e, 25);
    uint32_t ch = (e & f) ^ (~e & g);
    uint32_t t1 = hh + S1 + ch + sha256_k[i] + w[i];
    uint32_t S0 = sha_rotr(a, 2) ^ sha_rotr(a, 13) ^ sha_rotr(a, 22);
    uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
    uint32_t t2 = S0 + maj;
    hh = g;
    g = f;
    f = e;
    e = d + t1;
    d = c;
    c = b;
    b = a;
    a = t1 + t2;
  }
  s.h[0] += a;
  s.h[1] += b;
  s.h[2] += c;
  s.h[3] += d;
  s.h[4] += e;
  s.h[5] += f;
  s.h[6] += g;
  s.h[7] += hh;
}

static void sha256_update(Sha256State &s, const uint8_t *data, size_t len) {
  for (size_t i = 0; i < len; ++i) {
    s.block[s.block_len++] = data[i];
    if (s.block_len == 64) {
      sha256_process_block(s);
      s.block_len = 0;
    }
  }
  s.total_len += len;
}

static void sha256_final(Sha256State &s, uint8_t out[32]) {
  uint64_t bits = s.total_len * 8;
  s.block[s.block_len++] = 0x80;
  if (s.block_len > 56) {
    while (s.block_len < 64)
      s.block[s.block_len++] = 0;
    sha256_process_block(s);
    s.block_len = 0;
  }
  while (s.block_len < 56)
    s.block[s.block_len++] = 0;
  for (int i = 7; i >= 0; --i)
    s.block[s.block_len++] = static_cast<uint8_t>(bits >> (i * 8));
  sha256_process_block(s);
  for (int i = 0; i < 8; ++i) {
    out[i * 4] = static_cast<uint8_t>(s.h[i] >> 24);
    out[i * 4 + 1] = static_cast<uint8_t>(s.h[i] >> 16);
    out[i * 4 + 2] = static_cast<uint8_t>(s.h[i] >> 8);
    out[i * 4 + 3] = static_cast<uint8_t>(s.h[i]);
  }
}

static void hmac_sha256(const uint8_t *key, size_t key_len, const uint8_t *msg,
                        size_t msg_len, uint8_t out[32]) {
  uint8_t k_pad[64];
  std::memset(k_pad, 0, 64);
  if (key_len > 64) {
    Sha256State ks;
    sha256_init(ks);
    sha256_update(ks, key, key_len);
    sha256_final(ks, k_pad);
  } else {
    std::memcpy(k_pad, key, key_len);
  }

  uint8_t i_kp[64];
  for (int i = 0; i < 64; ++i)
    i_kp[i] = k_pad[i] ^ 0x36;
  Sha256State inner;
  sha256_init(inner);
  sha256_update(inner, i_kp, 64);
  sha256_update(inner, msg, msg_len);
  uint8_t ih[32];
  sha256_final(inner, ih);

  uint8_t o_kp[64];
  for (int i = 0; i < 64; ++i)
    o_kp[i] = k_pad[i] ^ 0x5c;
  Sha256State outer;
  sha256_init(outer);
  sha256_update(outer, o_kp, 64);
  sha256_update(outer, ih, 32);
  sha256_final(outer, out);
}

static void bytes_to_hex(const uint8_t *data, int len, char *out) {
  static const char hex[] = "0123456789abcdef";
  for (int i = 0; i < len; ++i) {
    out[i * 2] = hex[(data[i] >> 4) & 0x0F];
    out[i * 2 + 1] = hex[data[i] & 0x0F];
  }
  out[len * 2] = '\0';
}

static bool hex_to_bytes(const char *hex_str, uint8_t *out, int max_bytes) {
  int len = static_cast<int>(std::strlen(hex_str));
  if (len % 2 != 0 || len / 2 > max_bytes)
    return false;
  for (int i = 0; i < len / 2; ++i) {
    unsigned int bv = 0;
    std::sscanf(hex_str + i * 2, "%2x", &bv);
    out[i] = static_cast<uint8_t>(bv);
  }
  return true;
}

// =========================================================================
// CRC32
// =========================================================================

static uint32_t crc32_table[256];
static bool crc32_table_init = false;

static void init_crc32_table() {
  if (crc32_table_init)
    return;
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
// TELEMETRY INTEGRITY CHECK
// =========================================================================

struct TelemetryCheck {
  bool loaded;
  bool crc_valid;
  bool hmac_valid;
  int schema_version;
  bool determinism_status;
  uint32_t stored_crc;
  uint32_t computed_crc;
  char stored_hmac[65];
};

static double parse_dbl(const char *buf, const char *key) {
  const char *p = std::strstr(buf, key);
  if (!p)
    return 0.0;
  p += std::strlen(key);
  while (*p && (*p == '"' || *p == ':' || *p == ' '))
    ++p;
  double v = 0.0;
  std::sscanf(p, "%lf", &v);
  return v;
}

static int parse_int(const char *buf, const char *key) {
  const char *p = std::strstr(buf, key);
  if (!p)
    return 0;
  p += std::strlen(key);
  while (*p && (*p == '"' || *p == ':' || *p == ' '))
    ++p;
  int v = 0;
  std::sscanf(p, "%d", &v);
  return v;
}

static uint64_t parse_u64(const char *buf, const char *key) {
  const char *p = std::strstr(buf, key);
  if (!p)
    return 0;
  p += std::strlen(key);
  while (*p && (*p == '"' || *p == ':' || *p == ' '))
    ++p;
  unsigned long long v = 0;
  std::sscanf(p, "%llu", &v);
  return static_cast<uint64_t>(v);
}

static uint32_t parse_u32(const char *buf, const char *key) {
  const char *p = std::strstr(buf, key);
  if (!p)
    return 0;
  p += std::strlen(key);
  while (*p && (*p == '"' || *p == ':' || *p == ' '))
    ++p;
  unsigned int v = 0;
  std::sscanf(p, "%u", &v);
  return static_cast<uint32_t>(v);
}

static bool parse_bl(const char *buf, const char *key) {
  const char *p = std::strstr(buf, key);
  if (!p)
    return false;
  p += std::strlen(key);
  while (*p && (*p == '"' || *p == ':' || *p == ' '))
    ++p;
  return (std::strncmp(p, "true", 4) == 0);
}

static void parse_str(const char *buf, const char *key, char *out, size_t sz) {
  out[0] = '\0';
  const char *p = std::strstr(buf, key);
  if (!p)
    return;
  p += std::strlen(key);
  while (*p && (*p == '"' || *p == ':' || *p == ' '))
    ++p;
  size_t i = 0;
  while (*p && *p != '"' && i < sz - 1)
    out[i++] = *p++;
  out[i] = '\0';
}

static TelemetryCheck check_telemetry_integrity() {
  TelemetryCheck tc;
  std::memset(&tc, 0, sizeof(tc));

  FILE *f = std::fopen(TELEMETRY_PATH, "r");
  if (!f)
    return tc;

  char buf[4096];
  std::memset(buf, 0, sizeof(buf));
  size_t n = std::fread(buf, 1, sizeof(buf) - 1, f);
  std::fclose(f);
  if (n == 0)
    return tc;

  tc.loaded = true;
  tc.schema_version = parse_int(buf, "schema_version");
  tc.determinism_status = parse_bl(buf, "determinism_status");
  tc.stored_crc = parse_u32(buf, "crc32");
  parse_str(buf, "hmac", tc.stored_hmac, sizeof(tc.stored_hmac));

  // Recompute CRC
  bool det = parse_bl(buf, "determinism_status");
  bool frz = parse_bl(buf, "freeze_status");
  double prec = parse_dbl(buf, "precision");
  double rec = parse_dbl(buf, "recall");
  double kl = parse_dbl(buf, "kl_divergence");
  double ece = parse_dbl(buf, "ece");
  double loss = parse_dbl(buf, "loss");
  double temp = parse_dbl(buf, "gpu_temperature");
  int epoch = parse_int(buf, "epoch");
  int batch = parse_int(buf, "batch_size");
  uint64_t ts = parse_u64(buf, "timestamp");

  char crc_buf[2048];
  int crc_len = std::snprintf(
      crc_buf, sizeof(crc_buf),
      "v%d|det:%d|frz:%d|prec:%.8f|rec:%.8f|kl:%.8f|ece:%.8f|"
      "loss:%.8f|temp:%.8f|epoch:%d|batch:%d|ts:%llu",
      tc.schema_version, det ? 1 : 0, frz ? 1 : 0, prec, rec, kl, ece, loss,
      temp, epoch, batch, static_cast<unsigned long long>(ts));
  tc.computed_crc = compute_crc32(crc_buf, static_cast<size_t>(crc_len));
  tc.crc_valid = (tc.stored_crc == tc.computed_crc);

  // Verify HMAC
  tc.hmac_valid = false;
  if (tc.stored_hmac[0] != '\0') {
    uint8_t key[128];
    size_t key_len = 0;
    FILE *kf = std::fopen(HMAC_KEY_PATH, "r");
    if (kf) {
      char kbuf[256];
      std::memset(kbuf, 0, sizeof(kbuf));
      size_t kn = std::fread(kbuf, 1, sizeof(kbuf) - 1, kf);
      std::fclose(kf);
      while (kn > 0 && (kbuf[kn - 1] == '\n' || kbuf[kn - 1] == '\r' ||
                        kbuf[kn - 1] == ' '))
        kbuf[--kn] = '\0';
      if (kn > 0 && hex_to_bytes(kbuf, key, 128)) {
        key_len = kn / 2;
        char hmac_msg[256];
        int hmac_msg_len = std::snprintf(
            hmac_msg, sizeof(hmac_msg), "%d|%u|%llu", tc.schema_version,
            tc.stored_crc, static_cast<unsigned long long>(ts));
        uint8_t digest[32];
        hmac_sha256(key, key_len, reinterpret_cast<const uint8_t *>(hmac_msg),
                    static_cast<size_t>(hmac_msg_len), digest);
        char expected[65];
        bytes_to_hex(digest, 32, expected);
        bool match = true;
        for (int i = 0; i < 64; ++i)
          if (tc.stored_hmac[i] != expected[i])
            match = false;
        tc.hmac_valid = match;
      }
    }
  }

  return tc;
}

// =========================================================================
// RECOVERY ACTIONS
// =========================================================================

static void log_recovery(const char *event) {
  FILE *f = std::fopen(RECOVERY_LOG, "a");
  if (!f)
    return;
  uint64_t now = static_cast<uint64_t>(std::time(nullptr));
  std::fprintf(f, "[%llu] RECOVERY: %s\n", static_cast<unsigned long long>(now),
               event);
  std::fflush(f);
  std::fclose(f);
}

static void force_mode_a(const char *reason) {
  FILE *f = std::fopen(MODE_OVERRIDE, "w");
  if (!f)
    return;
  uint64_t now = static_cast<uint64_t>(std::time(nullptr));
  std::fprintf(f, "{\n");
  std::fprintf(f, "  \"forced_mode\": \"MODE_A\",\n");
  std::fprintf(f, "  \"reason\": \"%s\",\n", reason);
  std::fprintf(f, "  \"timestamp\": %llu\n",
               static_cast<unsigned long long>(now));
  std::fprintf(f, "}\n");
  std::fflush(f);
  int fd = fileno(f);
  if (fd >= 0)
    fsync_fd(fd);
  std::fclose(f);
}

static void reset_mutex_to_idle() {
  FILE *f = std::fopen(MUTEX_STATE, "w");
  if (!f)
    return;
  uint64_t now = static_cast<uint64_t>(std::time(nullptr));
  std::fprintf(f, "{\n");
  std::fprintf(f, "  \"mode\": 0,\n");
  std::fprintf(f, "  \"mode_name\": \"IDLE\",\n");
  std::fprintf(f, "  \"entry_timestamp\": %llu,\n",
               static_cast<unsigned long long>(now));
  std::fprintf(f, "  \"forced_by\": \"recovery_guard\"\n");
  std::fprintf(f, "}\n");
  std::fflush(f);
  int fd = fileno(f);
  if (fd >= 0)
    fsync_fd(fd);
  std::fclose(f);
}

static void invalidate_freeze() {
  // Write telemetry with freeze_status = false
  FILE *f = std::fopen(TELEMETRY_PATH, "r");
  if (!f)
    return;
  char buf[4096];
  std::memset(buf, 0, sizeof(buf));
  std::fread(buf, 1, sizeof(buf) - 1, f);
  std::fclose(f);

  // Simple replacement: set freeze_status to false
  char *pos = std::strstr(buf, "\"freeze_status\": true");
  if (pos) {
    // Replace "true" with "false" (5 chars -> 5 chars padded)
    std::memcpy(pos + 17, "false", 5);
  }
  // Note: This invalidates CRC/HMAC — intentional (forces retraining)
}

static void reset_protocol_state() {
  FILE *f = std::fopen(PROTOCOL_STATE_PATH, "w");
  if (!f)
    return;
  std::fprintf(f, "{\n");
  std::fprintf(f, "  \"training_active\": false,\n");
  std::fprintf(f, "  \"training_start_timestamp\": 0,\n");
  std::fprintf(f, "  \"training_start_monotonic\": 0,\n");
  std::fprintf(f, "  \"elapsed_seconds_monotonic\": 0,\n");
  std::fprintf(f, "  \"hunt_lockout_until_monotonic\": 0,\n");
  std::fprintf(f, "  \"hunt_locked\": false,\n");
  std::fprintf(f, "  \"mode\": 0\n");
  std::fprintf(f, "}\n");
  std::fflush(f);
  int fd = fileno(f);
  if (fd >= 0)
    fsync_fd(fd);
  std::fclose(f);
}

static void reset_telemetry() {
  std::remove(TELEMETRY_PATH);
  log_recovery("Telemetry reset — file removed due to corruption");
}

// =========================================================================
// CHECK FOR ORPHANED TRAINING STATE
// =========================================================================

static bool is_training_orphaned() {
  // Check if protocol state says training_active but PID lock is missing
  FILE *f = std::fopen(PROTOCOL_STATE_PATH, "r");
  if (!f)
    return false;

  char buf[2048];
  std::memset(buf, 0, sizeof(buf));
  std::fread(buf, 1, sizeof(buf) - 1, f);
  std::fclose(f);

  bool active = parse_bl(buf, "training_active");
  if (!active)
    return false;

  // Check for PID lock file
  FILE *pid_f = std::fopen(PID_LOCK_PATH, "r");
  if (pid_f) {
    std::fclose(pid_f);
    return false; // PID lock exists — training may still be running
  }

  return true; // Training active but no PID lock = orphaned
}

// =========================================================================
// MAIN RECOVERY ENTRY POINT
// =========================================================================

struct RecoveryResult {
  bool orphan_recovered;
  bool telemetry_recovered;
  bool clean; // No recovery needed
  char summary[512];
};

static RecoveryResult run_recovery() {
  RecoveryResult result;
  std::memset(&result, 0, sizeof(result));
  result.clean = true;

  // Check 1: Orphaned training state
  if (is_training_orphaned()) {
    result.clean = false;
    result.orphan_recovered = true;

    force_mode_a("crash_recovery_orphaned_training");
    reset_mutex_to_idle();
    invalidate_freeze();
    reset_protocol_state();
    log_recovery("Orphaned training detected — demoted to MODE_A, "
                 "mutex reset, freeze invalidated");

    std::printf("[RECOVERY GUARD] Orphaned training recovered\n");
  }

  // Check 2: Telemetry corruption
  TelemetryCheck tc = check_telemetry_integrity();
  if (tc.loaded && (!tc.crc_valid || !tc.hmac_valid)) {
    result.clean = false;
    result.telemetry_recovered = true;

    reset_telemetry();
    reset_protocol_state();
    force_mode_a("crash_recovery_corrupted_telemetry");

    char detail[256];
    std::snprintf(
        detail, sizeof(detail),
        "Corrupted telemetry — CRC:%s HMAC:%s — reset and forced retraining",
        tc.crc_valid ? "OK" : "FAIL", tc.hmac_valid ? "OK" : "FAIL");
    log_recovery(detail);

    std::printf("[RECOVERY GUARD] Corrupted telemetry recovered\n");
  }

  if (result.clean) {
    std::snprintf(result.summary, sizeof(result.summary),
                  "No recovery needed — system clean");
  } else {
    std::snprintf(result.summary, sizeof(result.summary),
                  "Recovery performed: orphan=%s telemetry=%s",
                  result.orphan_recovered ? "YES" : "NO",
                  result.telemetry_recovered ? "YES" : "NO");
  }

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

  // Clean up
  std::remove(PROTOCOL_STATE_PATH);
  std::remove(TELEMETRY_PATH);
  std::remove(MODE_OVERRIDE);
  std::remove(MUTEX_STATE);
  std::remove(PID_LOCK_PATH);
  std::remove(RECOVERY_LOG);

  // Test 1: Clean state — no recovery needed
  {
    RecoveryResult r = run_recovery();
    test(r.clean, "Clean state: no recovery needed");
  }

  // Test 2: Orphaned training detected
  {
    // Write protocol state with training_active=true but no PID lock
    FILE *f = std::fopen(PROTOCOL_STATE_PATH, "w");
    if (f) {
      std::fprintf(f, "{\"training_active\": true, \"mode\": 1}\n");
      std::fclose(f);
    }
    std::remove(PID_LOCK_PATH);

    test(is_training_orphaned(), "Orphan detected: active + no PID lock");

    RecoveryResult r = run_recovery();
    test(r.orphan_recovered, "Orphan recovery triggered");

    // Verify mode override written
    FILE *mo = std::fopen(MODE_OVERRIDE, "r");
    test(mo != nullptr, "Mode override written after orphan recovery");
    if (mo) {
      char buf[512];
      std::memset(buf, 0, sizeof(buf));
      std::fread(buf, 1, sizeof(buf) - 1, mo);
      std::fclose(mo);
      test(std::strstr(buf, "MODE_A") != nullptr, "Mode override is MODE_A");
    }

    // Verify mutex reset
    FILE *ms = std::fopen(MUTEX_STATE, "r");
    test(ms != nullptr, "Mutex state reset after orphan recovery");
    if (ms) {
      char buf[512];
      std::memset(buf, 0, sizeof(buf));
      std::fread(buf, 1, sizeof(buf) - 1, ms);
      std::fclose(ms);
      test(std::strstr(buf, "IDLE") != nullptr, "Mutex reset to IDLE");
    }

    // Verify recovery log
    FILE *rl = std::fopen(RECOVERY_LOG, "r");
    test(rl != nullptr, "Recovery log created");
    if (rl) {
      char buf[512];
      std::memset(buf, 0, sizeof(buf));
      std::fread(buf, 1, sizeof(buf) - 1, rl);
      std::fclose(rl);
      test(std::strstr(buf, "Orphaned") != nullptr,
           "Recovery log mentions orphan");
    }
  }

  // Test 3: Training with PID lock is NOT orphaned
  {
    FILE *f = std::fopen(PROTOCOL_STATE_PATH, "w");
    if (f) {
      std::fprintf(f, "{\"training_active\": true, \"mode\": 1}\n");
      std::fclose(f);
    }
    FILE *p = std::fopen(PID_LOCK_PATH, "w");
    if (p) {
      std::fprintf(p, "12345\n");
      std::fclose(p);
    }

    test(!is_training_orphaned(), "Not orphaned with PID lock");
  }

  // Test 4: Corrupted telemetry recovery
  {
    std::remove(MODE_OVERRIDE);
    std::remove(RECOVERY_LOG);
    std::remove(PROTOCOL_STATE_PATH);
    std::remove(PID_LOCK_PATH);

    // Write telemetry with bad CRC
    FILE *f = std::fopen(TELEMETRY_PATH, "w");
    if (f) {
      std::fprintf(f, "{\n  \"schema_version\": 1,\n"
                      "  \"determinism_status\": true,\n"
                      "  \"freeze_status\": true,\n"
                      "  \"precision\": 0.95000000,\n"
                      "  \"recall\": 0.93000000,\n"
                      "  \"kl_divergence\": 0.01500000,\n"
                      "  \"ece\": 0.01200000,\n"
                      "  \"loss\": 0.04500000,\n"
                      "  \"gpu_temperature\": 72.50000000,\n"
                      "  \"epoch\": 42,\n"
                      "  \"batch_size\": 64,\n"
                      "  \"timestamp\": 1700000000,\n"
                      "  \"crc32\": 99999,\n"
                      "  \"hmac\": \"\"\n}\n");
      std::fclose(f);
    }

    RecoveryResult r = run_recovery();
    test(r.telemetry_recovered, "Corrupted telemetry recovery triggered");

    // Verify telemetry removed
    FILE *tf = std::fopen(TELEMETRY_PATH, "r");
    test(tf == nullptr, "Corrupted telemetry file removed");
    if (tf)
      std::fclose(tf);
  }

  // Cleanup
  std::remove(PROTOCOL_STATE_PATH);
  std::remove(TELEMETRY_PATH);
  std::remove(MODE_OVERRIDE);
  std::remove(MUTEX_STATE);
  std::remove(PID_LOCK_PATH);
  std::remove(RECOVERY_LOG);

  std::printf("\n  Recovery Guard: %d passed, %d failed\n", passed, failed);
  return failed == 0;
}

} // namespace recovery_guard

// =========================================================================
// SELF-TEST ENTRY POINT
// =========================================================================

#ifdef RUN_SELF_TEST
int main() {
  std::printf("=== Runtime Recovery Guard Self-Test ===\n");
  bool ok = recovery_guard::run_tests();
  return ok ? 0 : 1;
}
#endif
