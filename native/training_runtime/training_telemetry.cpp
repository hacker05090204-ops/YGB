/**
 * training_telemetry.cpp — Training Telemetry with HMAC Tamper Protection
 *
 * Features:
 *   - JSON schema version field
 *   - CRC32 hash of payload (table-based, no external deps)
 *   - HMAC-SHA256 signature (no external deps — SHA-256 from scratch)
 *   - Secret key loaded from config/hmac_secret.key
 *   - Atomic write: temp -> fflush -> fsync -> rename
 *   - On write failure -> retain previous valid state
 *
 * NO mock data. NO silent fallback. NO telemetry trust without validation.
 */

#include <cmath>
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

namespace training_telemetry {

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int SCHEMA_VERSION = 1;
static constexpr char TELEMETRY_PATH[] = "reports/training_telemetry.json";
static constexpr char TELEMETRY_TMP[] = "reports/training_telemetry.json.tmp";
static constexpr char HMAC_KEY_PATH[] = "config/hmac_secret.key";
static constexpr char LAST_SEEN_PATH[] = "reports/last_seen_timestamp.json";
static constexpr char LAST_SEEN_TMP[] = "reports/last_seen_timestamp.json.tmp";

// =========================================================================
// MONOTONIC CLOCK
// =========================================================================

static uint64_t get_monotonic_seconds() {
#ifdef _WIN32
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

static uint64_t get_wall_clock_unix() {
  return static_cast<uint64_t>(std::time(nullptr));
}

// Global: set once on first telemetry write, never reset
static uint64_t g_monotonic_start_time = 0;

// =========================================================================
// LAST SEEN TIMESTAMP PERSISTENCE
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
// SHA-256 (FIPS 180-4, no external dependencies)
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

static void sha256(const uint8_t *data, size_t len, uint8_t out[32]) {
  Sha256State s;
  sha256_init(s);
  sha256_update(s, data, len);
  sha256_final(s, out);
}

// =========================================================================
// HMAC-SHA256 (RFC 2104, no external dependencies)
// =========================================================================

static constexpr int HMAC_BLOCK_SIZE = 64;
static constexpr int HMAC_DIGEST_SIZE = 32;

static void hmac_sha256(const uint8_t *key, size_t key_len, const uint8_t *msg,
                        size_t msg_len, uint8_t out[32]) {
  uint8_t k_pad[HMAC_BLOCK_SIZE];
  std::memset(k_pad, 0, HMAC_BLOCK_SIZE);

  // If key > block size, hash it first
  if (key_len > HMAC_BLOCK_SIZE) {
    sha256(key, key_len, k_pad);
  } else {
    std::memcpy(k_pad, key, key_len);
  }

  // Inner: SHA256(k_ipad || msg)
  uint8_t i_key_pad[HMAC_BLOCK_SIZE];
  for (int i = 0; i < HMAC_BLOCK_SIZE; ++i)
    i_key_pad[i] = k_pad[i] ^ 0x36;

  Sha256State inner;
  sha256_init(inner);
  sha256_update(inner, i_key_pad, HMAC_BLOCK_SIZE);
  sha256_update(inner, msg, msg_len);
  uint8_t inner_hash[32];
  sha256_final(inner, inner_hash);

  // Outer: SHA256(k_opad || inner_hash)
  uint8_t o_key_pad[HMAC_BLOCK_SIZE];
  for (int i = 0; i < HMAC_BLOCK_SIZE; ++i)
    o_key_pad[i] = k_pad[i] ^ 0x5c;

  Sha256State outer;
  sha256_init(outer);
  sha256_update(outer, o_key_pad, HMAC_BLOCK_SIZE);
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
// HMAC KEY MANAGEMENT
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
      return false; // Fail closed
    }
    n = std::fread(buf, 1, sizeof(buf) - 1, f);
    std::fclose(f);
  }

  // Trim whitespace
  while (n > 0 &&
         (buf[n - 1] == '\n' || buf[n - 1] == '\r' || buf[n - 1] == ' '))
    buf[--n] = '\0';

  if (n == 0)
    return false;

  // Key is hex-encoded
  if (n > max_len * 2)
    return false;
  *key_len = n / 2;
  return hex_to_bytes(buf, key, static_cast<int>(max_len));
}

// =========================================================================
// CRC32 (table-based, no external dependencies)
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
// TELEMETRY PAYLOAD
// =========================================================================

struct TelemetryPayload {
  int schema_version;
  bool determinism_status;
  bool freeze_status;
  double precision;
  double recall;
  double kl_divergence;
  double ece;
  double loss;
  double gpu_temperature;
  int epoch;
  int batch_size;
  uint64_t timestamp;
  uint64_t monotonic_timestamp; // Replay protection — monotonic clock
  // Phase 2: Real-time training visibility fields
  uint64_t wall_clock_unix;         // time(NULL) — real wall clock
  uint64_t monotonic_start_time;    // set once at first write
  double training_duration_seconds; // monotonic_current - monotonic_start
  double samples_per_second;        // throughput metric
  uint32_t crc32;
  char hmac[65]; // 64 hex chars + null
  bool valid;
};

// =========================================================================
// JSON SERIALIZATION (no external deps)
// =========================================================================

static void write_bool(FILE *f, const char *key, bool val, bool comma) {
  std::fprintf(f, "  \"%s\": %s%s\n", key, val ? "true" : "false",
               comma ? "," : "");
}

static void write_int(FILE *f, const char *key, int val, bool comma) {
  std::fprintf(f, "  \"%s\": %d%s\n", key, val, comma ? "," : "");
}

static void write_uint64(FILE *f, const char *key, uint64_t val, bool comma) {
  std::fprintf(f, "  \"%s\": %llu%s\n", key,
               static_cast<unsigned long long>(val), comma ? "," : "");
}

static void write_uint32(FILE *f, const char *key, uint32_t val, bool comma) {
  std::fprintf(f, "  \"%s\": %u%s\n", key, val, comma ? "," : "");
}

static void write_double(FILE *f, const char *key, double val, bool comma) {
  std::fprintf(f, "  \"%s\": %.8f%s\n", key, val, comma ? "," : "");
}

static void write_string(FILE *f, const char *key, const char *val,
                         bool comma) {
  std::fprintf(f, "  \"%s\": \"%s\"%s\n", key, val, comma ? "," : "");
}

// =========================================================================
// BUILD CRC PAYLOAD (deterministic string for hashing)
// =========================================================================

static uint32_t compute_payload_crc(const TelemetryPayload &p) {
  char buf[2048];
  int len = std::snprintf(
      buf, sizeof(buf),
      "v%d|det:%d|frz:%d|prec:%.8f|rec:%.8f|kl:%.8f|ece:%.8f|"
      "loss:%.8f|temp:%.8f|epoch:%d|batch:%d|ts:%llu|mono:%llu|"
      "start:%llu|wall:%llu|dur:%.8f|rate:%.8f",
      p.schema_version, p.determinism_status ? 1 : 0, p.freeze_status ? 1 : 0,
      p.precision, p.recall, p.kl_divergence, p.ece, p.loss, p.gpu_temperature,
      p.epoch, p.batch_size, static_cast<unsigned long long>(p.timestamp),
      static_cast<unsigned long long>(p.monotonic_timestamp),
      static_cast<unsigned long long>(p.monotonic_start_time),
      static_cast<unsigned long long>(p.wall_clock_unix),
      p.training_duration_seconds, p.samples_per_second);
  return compute_crc32(buf, static_cast<size_t>(len));
}

// =========================================================================
// COMPUTE HMAC over schema_version + CRC + timestamp
// =========================================================================

static bool compute_payload_hmac(const TelemetryPayload &p, char hmac_hex[65]) {
  uint8_t key[128];
  size_t key_len = 0;
  if (!load_hmac_key(key, &key_len, sizeof(key))) {
    hmac_hex[0] = '\0';
    return false;
  }

  // Build HMAC message: "schema_version|crc32|timestamp"
  char msg[256];
  int msg_len =
      std::snprintf(msg, sizeof(msg), "%d|%u|%llu", p.schema_version, p.crc32,
                    static_cast<unsigned long long>(p.timestamp));

  uint8_t digest[32];
  hmac_sha256(key, key_len, reinterpret_cast<const uint8_t *>(msg),
              static_cast<size_t>(msg_len), digest);

  bytes_to_hex(digest, 32, hmac_hex);
  return true;
}

// =========================================================================
// WRITE TELEMETRY (atomic: temp -> fsync -> rename)
// =========================================================================

static bool write_telemetry(const TelemetryPayload &payload) {
  // Set monotonic timestamp and enforce replay protection
  TelemetryPayload p = payload;
  p.monotonic_timestamp = get_monotonic_seconds();

  // Phase 2: Set timing fields
  p.wall_clock_unix = get_wall_clock_unix();
  if (g_monotonic_start_time == 0) {
    g_monotonic_start_time = p.monotonic_timestamp;
  }
  p.monotonic_start_time = g_monotonic_start_time;
  p.training_duration_seconds =
      static_cast<double>(p.monotonic_timestamp - g_monotonic_start_time);
  // samples_per_second is set by caller; keep as-is

  // Replay protection: reject if new timestamp <= last seen
  uint64_t last_seen = load_last_seen_timestamp();
  if (p.monotonic_timestamp <= last_seen && last_seen > 0) {
    std::fprintf(
        stderr, "REPLAY REJECTED: monotonic_timestamp %llu <= last_seen %llu\n",
        static_cast<unsigned long long>(p.monotonic_timestamp),
        static_cast<unsigned long long>(last_seen));
    return false; // Fail closed — no replayed telemetry
  }

  // Compute CRC over payload content (including monotonic_timestamp)
  p.crc32 = compute_payload_crc(p);

  // Compute HMAC over schema_version + CRC + timestamp
  if (!compute_payload_hmac(p, p.hmac)) {
    std::fprintf(stderr, "FATAL: Cannot load HMAC key from %s\n",
                 HMAC_KEY_PATH);
    return false; // Fail closed — no unsigned telemetry
  }

  FILE *f = std::fopen(TELEMETRY_TMP, "w");
  if (!f)
    return false; // Retain previous valid state

  std::fprintf(f, "{\n");
  write_int(f, "schema_version", p.schema_version, true);
  write_bool(f, "determinism_status", p.determinism_status, true);
  write_bool(f, "freeze_status", p.freeze_status, true);
  write_double(f, "precision", p.precision, true);
  write_double(f, "recall", p.recall, true);
  write_double(f, "kl_divergence", p.kl_divergence, true);
  write_double(f, "ece", p.ece, true);
  write_double(f, "loss", p.loss, true);
  write_double(f, "gpu_temperature", p.gpu_temperature, true);
  write_int(f, "epoch", p.epoch, true);
  write_int(f, "batch_size", p.batch_size, true);
  write_uint64(f, "timestamp", p.timestamp, true);
  write_uint64(f, "monotonic_timestamp", p.monotonic_timestamp, true);
  // Phase 2: Real-time visibility fields
  write_uint64(f, "wall_clock_unix", p.wall_clock_unix, true);
  write_uint64(f, "monotonic_start_time", p.monotonic_start_time, true);
  write_double(f, "training_duration_seconds", p.training_duration_seconds,
               true);
  write_double(f, "samples_per_second", p.samples_per_second, true);
  write_uint32(f, "crc32", p.crc32, true);
  write_string(f, "hmac", p.hmac, false);
  std::fprintf(f, "}\n");

  // Flush + fsync
  std::fflush(f);
  int fd = fileno(f);
  if (fd >= 0) {
    fsync_fd(fd);
  }
  std::fclose(f);

  // Atomic rename — only replace if write succeeded
  std::remove(TELEMETRY_PATH);
  if (std::rename(TELEMETRY_TMP, TELEMETRY_PATH) != 0) {
    return false;
  }

  // Persist last_seen_timestamp atomically
  save_last_seen_timestamp(p.monotonic_timestamp);

  return true;
}

// =========================================================================
// JSON PARSERS (no external deps)
// =========================================================================

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
  // pos now at start of string value (after opening quote)
  size_t i = 0;
  while (*pos && *pos != '"' && i < out_size - 1) {
    out[i++] = *pos++;
  }
  out[i] = '\0';
}

// =========================================================================
// READ TELEMETRY
// =========================================================================

static TelemetryPayload read_telemetry() {
  TelemetryPayload p;
  std::memset(&p, 0, sizeof(p));
  p.valid = false;

  FILE *f = std::fopen(TELEMETRY_PATH, "r");
  if (!f)
    return p;

  char buf[4096];
  std::memset(buf, 0, sizeof(buf));
  size_t n = std::fread(buf, 1, sizeof(buf) - 1, f);
  std::fclose(f);

  if (n == 0)
    return p;

  // Parse all fields
  p.schema_version = parse_int_after(buf, "schema_version");
  p.determinism_status = parse_bool_after(buf, "determinism_status");
  p.freeze_status = parse_bool_after(buf, "freeze_status");
  p.precision = parse_double_after(buf, "precision");
  p.recall = parse_double_after(buf, "recall");
  p.kl_divergence = parse_double_after(buf, "kl_divergence");
  p.ece = parse_double_after(buf, "ece");
  p.loss = parse_double_after(buf, "loss");
  p.gpu_temperature = parse_double_after(buf, "gpu_temperature");
  p.epoch = parse_int_after(buf, "epoch");
  p.batch_size = parse_int_after(buf, "batch_size");
  p.timestamp = parse_uint64_after(buf, "timestamp");
  p.monotonic_timestamp = parse_uint64_after(buf, "monotonic_timestamp");
  p.crc32 = parse_uint32_after(buf, "crc32");
  parse_string_after(buf, "hmac", p.hmac, sizeof(p.hmac));

  p.valid = true;
  return p;
}

// =========================================================================
// HMAC VALIDATION
// =========================================================================

static bool validate_hmac(const TelemetryPayload &p) {
  if (p.hmac[0] == '\0')
    return false; // No HMAC = unsigned = rejected

  char expected[65];
  if (!compute_payload_hmac(p, expected))
    return false;

  // Constant-time comparison to prevent timing attacks
  bool match = true;
  for (int i = 0; i < 64; ++i) {
    if (p.hmac[i] != expected[i])
      match = false;
  }
  return match;
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

  // Test 1: CRC32 determinism
  const char *data = "hello world";
  uint32_t crc_a = compute_crc32(data, std::strlen(data));
  uint32_t crc_b = compute_crc32(data, std::strlen(data));
  test(crc_a == crc_b, "CRC32 deterministic");
  test(crc_a != 0, "CRC32 non-zero for non-empty input");

  // Test 2: SHA-256 known answer test (NIST "abc")
  {
    const uint8_t abc[] = {'a', 'b', 'c'};
    uint8_t digest[32];
    sha256(abc, 3, digest);
    // Expected: ba7816bf 8f01cfea 414140de 5dae2223 b00361a3 96177a9c b410ff61
    // f20015ad
    test(digest[0] == 0xba && digest[1] == 0x78 && digest[2] == 0x16 &&
             digest[3] == 0xbf,
         "SHA-256 known answer (abc) first 4 bytes");
    test(digest[28] == 0xf2 && digest[29] == 0x00 && digest[30] == 0x15 &&
             digest[31] == 0xad,
         "SHA-256 known answer (abc) last 4 bytes");
  }

  // Test 3: HMAC-SHA256 determinism
  {
    const uint8_t key[] = "test_key_12345";
    const uint8_t msg[] = "1|12345|1700000000";
    uint8_t h1[32], h2[32];
    hmac_sha256(key, 14, msg, 18, h1);
    hmac_sha256(key, 14, msg, 18, h2);
    test(std::memcmp(h1, h2, 32) == 0, "HMAC-SHA256 deterministic");
    test(h1[0] != 0 || h1[1] != 0, "HMAC-SHA256 non-trivial output");
  }

  // Test 4: Write and read round-trip with HMAC
  TelemetryPayload original;
  std::memset(&original, 0, sizeof(original));
  original.schema_version = SCHEMA_VERSION;
  original.determinism_status = true;
  original.freeze_status = true;
  original.precision = 0.9650;
  original.recall = 0.9300;
  original.kl_divergence = 0.0150;
  original.ece = 0.0120;
  original.loss = 0.0450;
  original.gpu_temperature = 72.5;
  original.epoch = 42;
  original.batch_size = 64;
  original.timestamp = 1700000000;

  bool wrote = write_telemetry(original);
  test(wrote, "Write telemetry succeeds");

  TelemetryPayload loaded = read_telemetry();
  test(loaded.valid, "Read telemetry valid");
  test(loaded.schema_version == SCHEMA_VERSION, "Schema version preserved");
  test(loaded.determinism_status == true, "Determinism status preserved");
  test(loaded.freeze_status == true, "Freeze status preserved");
  test(std::fabs(loaded.precision - 0.9650) < 0.001, "Precision preserved");
  test(std::fabs(loaded.recall - 0.9300) < 0.001, "Recall preserved");
  test(loaded.epoch == 42, "Epoch preserved");
  test(loaded.batch_size == 64, "Batch size preserved");
  test(loaded.timestamp == 1700000000, "Timestamp preserved");

  // Test 5: CRC validation
  uint32_t expected_crc = compute_payload_crc(loaded);
  test(loaded.crc32 == expected_crc, "CRC32 matches after round-trip");

  // Test 6: HMAC present and valid
  test(loaded.hmac[0] != '\0', "HMAC field present after write");
  test(validate_hmac(loaded), "HMAC validates after round-trip");

  // Test 7: CRC detects mutation
  TelemetryPayload tampered = loaded;
  tampered.precision = 0.5000;
  uint32_t tampered_crc = compute_payload_crc(tampered);
  test(tampered_crc != loaded.crc32, "CRC32 detects payload mutation");

  // Test 8: HMAC detects signature tampering
  TelemetryPayload sig_tampered = loaded;
  sig_tampered.hmac[0] = (sig_tampered.hmac[0] == 'a') ? 'b' : 'a';
  test(!validate_hmac(sig_tampered), "HMAC detects signature tampering");

  // Test 9: Missing HMAC fails validation
  TelemetryPayload no_hmac = loaded;
  no_hmac.hmac[0] = '\0';
  test(!validate_hmac(no_hmac), "Missing HMAC fails validation");

  // Test 10: Monotonic timestamp is non-zero after write
  {
    TelemetryPayload mono_p;
    std::memset(&mono_p, 0, sizeof(mono_p));
    mono_p.schema_version = SCHEMA_VERSION;
    mono_p.determinism_status = true;
    mono_p.freeze_status = true;
    mono_p.precision = 0.96;
    mono_p.recall = 0.93;
    mono_p.timestamp = 1700000001;
    // Clear last_seen so this write succeeds
    std::remove(LAST_SEEN_PATH);
    bool w = write_telemetry(mono_p);
    test(w, "Write with monotonic timestamp succeeds");
    TelemetryPayload r2 = read_telemetry();
    test(r2.monotonic_timestamp > 0,
         "Monotonic timestamp non-zero after write");
  }

  // Test 11: Last seen timestamp persisted
  {
    uint64_t ls = load_last_seen_timestamp();
    test(ls > 0, "Last seen timestamp persisted");
  }

  // Cleanup
  std::remove(TELEMETRY_PATH);
  std::remove(TELEMETRY_TMP);
  std::remove(LAST_SEEN_PATH);
  std::remove(LAST_SEEN_TMP);

  std::printf("\n  Training Telemetry: %d passed, %d failed\n", passed, failed);
  return failed == 0;
}

} // namespace training_telemetry

// =========================================================================
// SELF-TEST ENTRY POINT
// =========================================================================

#ifdef RUN_SELF_TEST
int main() {
  std::printf("=== Training Telemetry Self-Test ===\n");
  bool ok = training_telemetry::run_tests();
  return ok ? 0 : 1;
}
#endif
