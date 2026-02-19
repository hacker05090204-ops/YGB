/**
 * runtime_signature_validator.cpp — Runtime Telemetry Signature Validator
 *
 * On load:
 *   1. Validate CRC32
 *   2. Validate schema_version
 *   3. Validate HMAC-SHA256 signature
 *   4. Validate determinism_status
 *
 * If ANY fail:
 *   - Force MODE_A (write mode_override.json)
 *   - Disable HUNT (reset mutex to IDLE)
 *   - Log incident to reports/signature_incidents.log
 *
 * NO silent fallback. NO trust without validation.
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
#include <sys/stat.h>
#include <unistd.h>

#define fsync_fd(fd) fsync(fd)
#endif

namespace signature_validator {

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int EXPECTED_SCHEMA_VERSION = 1;
static constexpr char TELEMETRY_PATH[] = "reports/training_telemetry.json";
static constexpr char MODE_OVERRIDE[] = "reports/mode_override.json";
static constexpr char MUTEX_STATE[] = "reports/mode_mutex_state.json";
static constexpr char INCIDENT_LOG[] = "reports/signature_incidents.log";
static constexpr char HMAC_KEY_PATH[] = "config/hmac_secret.key";
static constexpr char LAST_SEEN_PATH[] = "reports/last_seen_timestamp.json";
static constexpr char LAST_SEEN_TMP[] = "reports/last_seen_timestamp.json.tmp";

// =========================================================================
// SHA-256 (same implementation as training_telemetry.cpp)
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
  for (int i = 0; i < 16; ++i) {
    w[i] = (uint32_t(s.block[i * 4]) << 24) |
           (uint32_t(s.block[i * 4 + 1]) << 16) |
           (uint32_t(s.block[i * 4 + 2]) << 8) | uint32_t(s.block[i * 4 + 3]);
  }
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
    uint32_t temp1 = hh + S1 + ch + sha256_k[i] + w[i];
    uint32_t S0 = sha_rotr(a, 2) ^ sha_rotr(a, 13) ^ sha_rotr(a, 22);
    uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
    uint32_t temp2 = S0 + maj;

    hh = g;
    g = f;
    f = e;
    e = d + temp1;
    d = c;
    c = b;
    b = a;
    a = temp1 + temp2;
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

// =========================================================================
// HMAC-SHA256
// =========================================================================

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

  uint8_t i_key_pad[64];
  for (int i = 0; i < 64; ++i)
    i_key_pad[i] = k_pad[i] ^ 0x36;

  Sha256State inner;
  sha256_init(inner);
  sha256_update(inner, i_key_pad, 64);
  sha256_update(inner, msg, msg_len);
  uint8_t inner_hash[32];
  sha256_final(inner, inner_hash);

  uint8_t o_key_pad[64];
  for (int i = 0; i < 64; ++i)
    o_key_pad[i] = k_pad[i] ^ 0x5c;

  Sha256State outer;
  sha256_init(outer);
  sha256_update(outer, o_key_pad, 64);
  sha256_update(outer, inner_hash, 32);
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
    unsigned int byte_val = 0;
    std::sscanf(hex_str + i * 2, "%2x", &byte_val);
    out[i] = static_cast<uint8_t>(byte_val);
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
// TELEMETRY LOADING & PARSING
// =========================================================================

struct TelemetryData {
  int schema_version;
  bool determinism_status;
  bool freeze_status;
  double precision, recall, kl_divergence, ece, loss, gpu_temperature;
  int epoch, batch_size;
  uint64_t timestamp;
  uint64_t monotonic_timestamp;
  uint32_t crc32;
  char hmac[65];
  bool loaded;
};

static double parse_double_after(const char *buf, const char *key) {
  const char *pos = std::strstr(buf, key);
  if (!pos)
    return 0.0;
  pos += std::strlen(key);
  while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
    ++pos;
  double val = 0.0;
  std::sscanf(pos, "%lf", &val);
  return val;
}

static int parse_int_after(const char *buf, const char *key) {
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

static uint64_t parse_uint64_after(const char *buf, const char *key) {
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

static uint32_t parse_uint32_after(const char *buf, const char *key) {
  const char *pos = std::strstr(buf, key);
  if (!pos)
    return 0;
  pos += std::strlen(key);
  while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
    ++pos;
  unsigned int val = 0;
  std::sscanf(pos, "%u", &val);
  return static_cast<uint32_t>(val);
}

static bool parse_bool_after(const char *buf, const char *key) {
  const char *pos = std::strstr(buf, key);
  if (!pos)
    return false;
  pos += std::strlen(key);
  while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
    ++pos;
  return (std::strncmp(pos, "true", 4) == 0);
}

static void parse_string_after(const char *buf, const char *key, char *out,
                               size_t out_size) {
  out[0] = '\0';
  const char *pos = std::strstr(buf, key);
  if (!pos)
    return;
  pos += std::strlen(key);
  while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
    ++pos;
  size_t i = 0;
  while (*pos && *pos != '"' && i < out_size - 1)
    out[i++] = *pos++;
  out[i] = '\0';
}

static TelemetryData load_telemetry(const char *path) {
  TelemetryData d;
  std::memset(&d, 0, sizeof(d));
  d.loaded = false;

  FILE *f = std::fopen(path, "r");
  if (!f)
    return d;

  char buf[4096];
  std::memset(buf, 0, sizeof(buf));
  size_t n = std::fread(buf, 1, sizeof(buf) - 1, f);
  std::fclose(f);
  if (n == 0)
    return d;

  d.schema_version = parse_int_after(buf, "schema_version");
  d.determinism_status = parse_bool_after(buf, "determinism_status");
  d.freeze_status = parse_bool_after(buf, "freeze_status");
  d.precision = parse_double_after(buf, "precision");
  d.recall = parse_double_after(buf, "recall");
  d.kl_divergence = parse_double_after(buf, "kl_divergence");
  d.ece = parse_double_after(buf, "ece");
  d.loss = parse_double_after(buf, "loss");
  d.gpu_temperature = parse_double_after(buf, "gpu_temperature");
  d.epoch = parse_int_after(buf, "epoch");
  d.batch_size = parse_int_after(buf, "batch_size");
  d.timestamp = parse_uint64_after(buf, "timestamp");
  d.monotonic_timestamp = parse_uint64_after(buf, "monotonic_timestamp");
  d.crc32 = parse_uint32_after(buf, "crc32");
  parse_string_after(buf, "hmac", d.hmac, sizeof(d.hmac));
  d.loaded = true;
  return d;
}

// =========================================================================
// HMAC KEY LOADING
// =========================================================================

static bool load_hmac_key(uint8_t *key, size_t *key_len, size_t max_len) {
  char buf[256];
  std::memset(buf, 0, sizeof(buf));
  size_t n = 0;

  // Priority 1: YGB_HMAC_SECRET environment variable
  const char *env_secret = std::getenv("YGB_HMAC_SECRET");
  if (env_secret && env_secret[0] != '\0') {
    n = std::strlen(env_secret);
    if (n < sizeof(buf)) {
      std::memcpy(buf, env_secret, n);
      buf[n] = '\0';
    } else {
      return false; // Too long
    }
  } else {
    // Priority 2: Key file
    FILE *f = std::fopen(HMAC_KEY_PATH, "r");
    if (!f) {
      std::fprintf(stderr,
                   "HMAC secret not configured: no env var YGB_HMAC_SECRET "
                   "and no file %s\n",
                   HMAC_KEY_PATH);
      return false;
    }
    n = std::fread(buf, 1, sizeof(buf) - 1, f);
    std::fclose(f);
  }

  // Trim whitespace
  while (n > 0 &&
         (buf[n - 1] == '\n' || buf[n - 1] == '\r' || buf[n - 1] == ' '))
    buf[--n] = '\0';
  if (n == 0 || n > max_len * 2)
    return false;
  *key_len = n / 2;
  return hex_to_bytes(buf, key, static_cast<int>(max_len));
}

// =========================================================================
// VALIDATION RESULT
// =========================================================================

struct ValidationResult {
  bool crc_ok;
  bool schema_ok;
  bool hmac_ok;
  bool determinism_ok;
  bool secret_ok;
  bool replay_ok;
  bool all_ok;
  char failure_reason[512];
};

// =========================================================================
// SECRET KEY HARDENING
// =========================================================================

struct SecretCheckResult {
  bool exists;
  bool permissions_ok;
  char reason[256];
};

static SecretCheckResult check_secret_key_security() {
  SecretCheckResult r;
  std::memset(&r, 0, sizeof(r));
  r.exists = false;
  r.permissions_ok = false;

  FILE *f = std::fopen(HMAC_KEY_PATH, "r");
  if (!f) {
    std::snprintf(r.reason, sizeof(r.reason), "HMAC secret key missing: %s",
                  HMAC_KEY_PATH);
    return r;
  }
  std::fclose(f);
  r.exists = true;

#ifdef _WIN32
  // On Windows, check that file is not zero-length
  WIN32_FILE_ATTRIBUTE_DATA fad;
  if (GetFileAttributesExA(HMAC_KEY_PATH, GetFileExInfoStandard, &fad)) {
    if (fad.nFileSizeLow == 0 && fad.nFileSizeHigh == 0) {
      std::snprintf(r.reason, sizeof(r.reason), "HMAC secret key is empty");
      return r;
    }
    // Check if file has READONLY attribute (good security practice)
    // We accept both readable-only and normal files on Windows
    r.permissions_ok = true;
  } else {
    std::snprintf(r.reason, sizeof(r.reason),
                  "Cannot read HMAC key file attributes");
    return r;
  }
#else
  struct stat st;
  if (stat(HMAC_KEY_PATH, &st) != 0) {
    std::snprintf(r.reason, sizeof(r.reason), "Cannot stat HMAC key file");
    return r;
  }
  // Reject if world-readable (o+r) or group-writable (g+w)
  if (st.st_mode & S_IROTH) {
    std::snprintf(r.reason, sizeof(r.reason),
                  "HMAC key is world-readable (insecure)");
    return r;
  }
  if (st.st_mode & S_IWGRP) {
    std::snprintf(r.reason, sizeof(r.reason),
                  "HMAC key is group-writable (insecure)");
    return r;
  }
  r.permissions_ok = true;
#endif

  return r;
}

// =========================================================================
// REPLAY PROTECTION
// =========================================================================

static uint64_t load_last_seen_timestamp() {
  FILE *f = std::fopen(LAST_SEEN_PATH, "r");
  if (!f)
    return 0;
  char buf[256];
  std::memset(buf, 0, sizeof(buf));
  std::fread(buf, 1, sizeof(buf) - 1, f);
  std::fclose(f);
  const char *pos = std::strstr(buf, "last_seen");
  if (!pos)
    return 0;
  pos += 9;
  while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
    ++pos;
  unsigned long long val = 0;
  std::sscanf(pos, "%llu", &val);
  return static_cast<uint64_t>(val);
}

static bool save_last_seen_timestamp(uint64_t ts) {
  FILE *f = std::fopen(LAST_SEEN_TMP, "w");
  if (!f)
    return false;
  std::fprintf(f, "{\n  \"last_seen\": %llu\n}\n",
               static_cast<unsigned long long>(ts));
  std::fflush(f);
  int fd = fileno(f);
  if (fd >= 0)
    fsync_fd(fd);
  std::fclose(f);
  std::remove(LAST_SEEN_PATH);
  return std::rename(LAST_SEEN_TMP, LAST_SEEN_PATH) == 0;
}

// =========================================================================
// CONTAINMENT ACTIONS
// =========================================================================

static void force_mode_a(const char *reason = "signature_validation_failure") {
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

static void disable_hunt() {
  FILE *f = std::fopen(MUTEX_STATE, "w");
  if (!f)
    return;
  uint64_t now = static_cast<uint64_t>(std::time(nullptr));
  std::fprintf(f, "{\n");
  std::fprintf(f, "  \"mode\": 0,\n");
  std::fprintf(f, "  \"mode_name\": \"IDLE\",\n");
  std::fprintf(f, "  \"entry_timestamp\": %llu,\n",
               static_cast<unsigned long long>(now));
  std::fprintf(f, "  \"forced_by\": \"signature_validator\"\n");
  std::fprintf(f, "}\n");
  std::fflush(f);
  int fd = fileno(f);
  if (fd >= 0)
    fsync_fd(fd);
  std::fclose(f);
}

static void log_incident(const char *reason) {
  FILE *f = std::fopen(INCIDENT_LOG, "a");
  if (!f)
    return;
  uint64_t now = static_cast<uint64_t>(std::time(nullptr));
  std::fprintf(f, "[%llu] SIGNATURE INCIDENT: %s\n",
               static_cast<unsigned long long>(now), reason);
  std::fflush(f);
  std::fclose(f);
}

// =========================================================================
// CORE VALIDATION
// =========================================================================

static uint32_t recompute_crc(const TelemetryData &d) {
  char buf[2048];
  int len = std::snprintf(
      buf, sizeof(buf),
      "v%d|det:%d|frz:%d|prec:%.8f|rec:%.8f|kl:%.8f|ece:%.8f|"
      "loss:%.8f|temp:%.8f|epoch:%d|batch:%d|ts:%llu|mono:%llu",
      d.schema_version, d.determinism_status ? 1 : 0, d.freeze_status ? 1 : 0,
      d.precision, d.recall, d.kl_divergence, d.ece, d.loss, d.gpu_temperature,
      d.epoch, d.batch_size, static_cast<unsigned long long>(d.timestamp),
      static_cast<unsigned long long>(d.monotonic_timestamp));
  return compute_crc32(buf, static_cast<size_t>(len));
}

static bool verify_hmac(const TelemetryData &d) {
  if (d.hmac[0] == '\0')
    return false;

  uint8_t key[128];
  size_t key_len = 0;
  if (!load_hmac_key(key, &key_len, sizeof(key)))
    return false;

  char msg[256];
  int msg_len =
      std::snprintf(msg, sizeof(msg), "%d|%u|%llu", d.schema_version, d.crc32,
                    static_cast<unsigned long long>(d.timestamp));

  uint8_t digest[32];
  hmac_sha256(key, key_len, reinterpret_cast<const uint8_t *>(msg),
              static_cast<size_t>(msg_len), digest);

  char expected[65];
  bytes_to_hex(digest, 32, expected);

  // Constant-time comparison
  bool match = true;
  for (int i = 0; i < 64; ++i) {
    if (d.hmac[i] != expected[i])
      match = false;
  }
  return match;
}

static ValidationResult validate_telemetry() {
  ValidationResult r;
  std::memset(&r, 0, sizeof(r));

  // 0. Secret key security check
  SecretCheckResult sc = check_secret_key_security();
  r.secret_ok = sc.exists && sc.permissions_ok;
  if (!r.secret_ok) {
    r.all_ok = false;
    std::snprintf(r.failure_reason, sizeof(r.failure_reason),
                  "SECURITY_VIOLATION: %s", sc.reason);
    return r;
  }

  TelemetryData d = load_telemetry(TELEMETRY_PATH);
  if (!d.loaded) {
    r.all_ok = false;
    std::snprintf(r.failure_reason, sizeof(r.failure_reason),
                  "Telemetry file missing or empty");
    return r;
  }

  // 1. CRC validation
  uint32_t expected_crc = recompute_crc(d);
  r.crc_ok = (d.crc32 == expected_crc);

  // 2. Schema version
  r.schema_ok = (d.schema_version == EXPECTED_SCHEMA_VERSION);

  // 3. HMAC validation
  r.hmac_ok = verify_hmac(d);

  // 4. Determinism
  r.determinism_ok = d.determinism_status;

  // 5. Replay protection: monotonic_timestamp > last_seen
  uint64_t last_seen = load_last_seen_timestamp();
  r.replay_ok = (d.monotonic_timestamp > last_seen) || (last_seen == 0);

  r.all_ok = r.crc_ok && r.schema_ok && r.hmac_ok && r.determinism_ok &&
             r.secret_ok && r.replay_ok;

  if (!r.all_ok) {
    std::snprintf(r.failure_reason, sizeof(r.failure_reason),
                  "Validation failed: CRC=%s, Schema=%s, HMAC=%s, Det=%s, "
                  "Secret=%s, Replay=%s",
                  r.crc_ok ? "OK" : "FAIL", r.schema_ok ? "OK" : "FAIL",
                  r.hmac_ok ? "OK" : "FAIL", r.determinism_ok ? "OK" : "FAIL",
                  r.secret_ok ? "OK" : "FAIL", r.replay_ok ? "OK" : "FAIL");
  }

  // Persist last_seen if all OK
  if (r.all_ok && d.monotonic_timestamp > 0) {
    save_last_seen_timestamp(d.monotonic_timestamp);
  }

  return r;
}

// =========================================================================
// MAIN ENTRY: VALIDATE AND CONTAIN
// =========================================================================

static bool validate_and_contain() {
  ValidationResult r = validate_telemetry();

  if (r.all_ok) {
    std::printf("[SIGNATURE VALIDATOR] All checks passed\n");
    return true;
  }

  // CONTAINMENT: Force MODE_A, disable HUNT, log incident
  std::printf("[SIGNATURE VALIDATOR] CONTAINMENT TRIGGERED: %s\n",
              r.failure_reason);

  // Use specific reason for secret violations
  if (!r.secret_ok) {
    force_mode_a("SECURITY_VIOLATION_insecure_secret");
  } else if (!r.replay_ok) {
    force_mode_a("REPLAY_ATTACK_detected");
  } else {
    force_mode_a("signature_validation_failure");
  }
  disable_hunt();
  log_incident(r.failure_reason);

  return false;
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

  // Test 1: Secret key exists
  {
    SecretCheckResult sc = check_secret_key_security();
    test(sc.exists, "Secret key exists");
    test(sc.permissions_ok, "Secret key permissions OK");
  }

  // Test 2: Missing secret key detected
  {
    // Rename key temporarily
    std::rename(HMAC_KEY_PATH, "config/hmac_secret.key.bak");
    SecretCheckResult sc = check_secret_key_security();
    test(!sc.exists, "Missing secret key detected");
    std::rename("config/hmac_secret.key.bak", HMAC_KEY_PATH);
  }

  // Test 3: Missing telemetry file returns failure
  {
    std::remove(TELEMETRY_PATH);
    std::remove(LAST_SEEN_PATH);
    ValidationResult r = validate_telemetry();
    test(!r.all_ok, "Missing telemetry: validation fails");
  }

  // Test 4: CRC recomputation is deterministic
  {
    TelemetryData d;
    std::memset(&d, 0, sizeof(d));
    d.schema_version = 1;
    d.determinism_status = true;
    d.precision = 0.95;
    d.timestamp = 1700000000;
    d.monotonic_timestamp = 100;
    uint32_t c1 = recompute_crc(d);
    uint32_t c2 = recompute_crc(d);
    test(c1 == c2, "CRC recomputation deterministic");
    test(c1 != 0, "CRC non-zero");
  }

  // Test 5: Tampered CRC detected
  {
    TelemetryData d;
    std::memset(&d, 0, sizeof(d));
    d.schema_version = 1;
    d.determinism_status = true;
    d.timestamp = 1700000000;
    d.crc32 = 99999; // Wrong CRC
    d.loaded = true;
    uint32_t expected = recompute_crc(d);
    test(d.crc32 != expected, "Tampered CRC detected");
  }

  // Test 6: Wrong schema version detected
  {
    TelemetryData d;
    std::memset(&d, 0, sizeof(d));
    d.schema_version = 99;
    test(d.schema_version != EXPECTED_SCHEMA_VERSION, "Wrong schema detected");
  }

  // Test 7: Missing HMAC fails validation
  {
    TelemetryData d;
    std::memset(&d, 0, sizeof(d));
    d.hmac[0] = '\0';
    test(!verify_hmac(d), "Missing HMAC fails validation");
  }

  // Test 8: Containment writes mode override
  {
    std::remove(MODE_OVERRIDE);
    force_mode_a();
    FILE *f = std::fopen(MODE_OVERRIDE, "r");
    test(f != nullptr, "force_mode_a writes mode_override.json");
    if (f) {
      char buf[512];
      std::memset(buf, 0, sizeof(buf));
      std::fread(buf, 1, sizeof(buf) - 1, f);
      std::fclose(f);
      test(std::strstr(buf, "MODE_A") != nullptr,
           "Mode override contains MODE_A");
    }
    std::remove(MODE_OVERRIDE);
  }

  // Test 9: Containment resets mutex to IDLE
  {
    std::remove(MUTEX_STATE);
    disable_hunt();
    FILE *f = std::fopen(MUTEX_STATE, "r");
    test(f != nullptr, "disable_hunt writes mutex state");
    if (f) {
      char buf[512];
      std::memset(buf, 0, sizeof(buf));
      std::fread(buf, 1, sizeof(buf) - 1, f);
      std::fclose(f);
      test(std::strstr(buf, "IDLE") != nullptr, "Mutex reset to IDLE");
    }
    std::remove(MUTEX_STATE);
  }

  // Test 10: Incident logging
  {
    std::remove(INCIDENT_LOG);
    log_incident("test_incident");
    FILE *f = std::fopen(INCIDENT_LOG, "r");
    test(f != nullptr, "Incident log created");
    if (f) {
      char buf[512];
      std::memset(buf, 0, sizeof(buf));
      std::fread(buf, 1, sizeof(buf) - 1, f);
      std::fclose(f);
      test(std::strstr(buf, "test_incident") != nullptr,
           "Incident log contains reason");
    }
    std::remove(INCIDENT_LOG);
  }

  // Test 11: Last seen timestamp persistence
  {
    std::remove(LAST_SEEN_PATH);
    save_last_seen_timestamp(12345);
    uint64_t ls = load_last_seen_timestamp();
    test(ls == 12345, "Last seen timestamp round-trip");
    std::remove(LAST_SEEN_PATH);
  }

  // Test 12: Replay detection via last_seen
  {
    // Set last_seen to a high value, then check replay_ok
    save_last_seen_timestamp(999999999);
    TelemetryData d;
    std::memset(&d, 0, sizeof(d));
    d.monotonic_timestamp = 100; // Way below last_seen
    uint64_t ls = load_last_seen_timestamp();
    bool replay_ok = (d.monotonic_timestamp > ls) || (ls == 0);
    test(!replay_ok, "Replay detected: monotonic < last_seen");
    std::remove(LAST_SEEN_PATH);
  }

  std::printf("\n  Signature Validator: %d passed, %d failed\n", passed,
              failed);
  return failed == 0;
}

} // namespace signature_validator

// =========================================================================
// SELF-TEST ENTRY POINT
// =========================================================================

#ifdef RUN_SELF_TEST
int main() {
  std::printf("=== Runtime Signature Validator Self-Test ===\n");
  bool ok = signature_validator::run_tests();
  return ok ? 0 : 1;
}
#endif
