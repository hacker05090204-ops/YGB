/**
 * device_identity.cpp — Per-Device Cryptographic Identity
 *
 * Generates and persists a unique 256-bit device private key using
 * platform CSPRNG (/dev/urandom on Linux, BCryptGenRandom on Windows).
 *
 * Derives device_id (SHA-256 fingerprint of private key).
 * Persists to config/device_identity.json on first run.
 * Loads from file on subsequent runs.
 *
 * NO external crypto libraries. SHA-256 from scratch (FIPS 180-4).
 * NO cloud dependency. NO key sharing between devices.
 */

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>

#ifdef _WIN32
#include <bcrypt.h>
#include <windows.h>

#pragma comment(lib, "bcrypt.lib")
#else
#include <unistd.h>
#endif

namespace device_identity {

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int KEY_SIZE = 32; // 256-bit
static constexpr char IDENTITY_PATH[] = "config/device_identity.json";

// =========================================================================
// SHA-256 (standalone, FIPS 180-4)
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

static inline uint32_t rotr(uint32_t x, int n) {
  return (x >> n) | (x << (32 - n));
}

static void sha256(const uint8_t *data, size_t len, uint8_t out[32]) {
  uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                   0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};

  // Pad message
  size_t new_len = ((len + 8) / 64 + 1) * 64;
  uint8_t *msg = new uint8_t[new_len];
  std::memset(msg, 0, new_len);
  std::memcpy(msg, data, len);
  msg[len] = 0x80;
  uint64_t bits = len * 8;
  for (int i = 0; i < 8; ++i)
    msg[new_len - 1 - i] = static_cast<uint8_t>(bits >> (i * 8));

  // Process blocks
  for (size_t off = 0; off < new_len; off += 64) {
    uint32_t w[64];
    for (int i = 0; i < 16; ++i)
      w[i] = (uint32_t(msg[off + i * 4]) << 24) |
             (uint32_t(msg[off + i * 4 + 1]) << 16) |
             (uint32_t(msg[off + i * 4 + 2]) << 8) |
             uint32_t(msg[off + i * 4 + 3]);
    for (int i = 16; i < 64; ++i) {
      uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
      uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }

    uint32_t a = h[0], b = h[1], c = h[2], d = h[3];
    uint32_t e = h[4], f = h[5], g = h[6], hh = h[7];
    for (int i = 0; i < 64; ++i) {
      uint32_t S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      uint32_t ch = (e & f) ^ (~e & g);
      uint32_t t1 = hh + S1 + ch + sha256_k[i] + w[i];
      uint32_t S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
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
    h[0] += a;
    h[1] += b;
    h[2] += c;
    h[3] += d;
    h[4] += e;
    h[5] += f;
    h[6] += g;
    h[7] += hh;
  }
  delete[] msg;

  for (int i = 0; i < 8; ++i) {
    out[i * 4] = static_cast<uint8_t>(h[i] >> 24);
    out[i * 4 + 1] = static_cast<uint8_t>(h[i] >> 16);
    out[i * 4 + 2] = static_cast<uint8_t>(h[i] >> 8);
    out[i * 4 + 3] = static_cast<uint8_t>(h[i]);
  }
}

// =========================================================================
// HEX ENCODING
// =========================================================================

static void bytes_to_hex(const uint8_t *data, int len, char *out) {
  static const char hex[] = "0123456789abcdef";
  for (int i = 0; i < len; ++i) {
    out[i * 2] = hex[(data[i] >> 4) & 0xF];
    out[i * 2 + 1] = hex[data[i] & 0xF];
  }
  out[len * 2] = '\0';
}

// =========================================================================
// CSPRNG — Platform Secure Random
// =========================================================================

static bool secure_random(uint8_t *buf, size_t len) {
#ifdef _WIN32
  NTSTATUS status = BCryptGenRandom(NULL, buf, static_cast<ULONG>(len),
                                    BCRYPT_USE_SYSTEM_PREFERRED_RNG);
  return status >= 0;
#else
  FILE *f = std::fopen("/dev/urandom", "rb");
  if (!f)
    return false;
  size_t n = std::fread(buf, 1, len, f);
  std::fclose(f);
  return n == len;
#endif
}

// =========================================================================
// DEVICE IDENTITY
// =========================================================================

struct DeviceIdentity {
  uint8_t private_key[KEY_SIZE]; // 256-bit secret
  char device_id[65];            // SHA-256 hex of private key
  char created_at[32];           // ISO timestamp
  bool loaded;
};

static DeviceIdentity g_identity = {};

// =========================================================================
// PERSISTENCE
// =========================================================================

static bool save_identity(const DeviceIdentity &id) {
  FILE *f = std::fopen(IDENTITY_PATH, "w");
  if (!f)
    return false;

  char key_hex[KEY_SIZE * 2 + 1];
  bytes_to_hex(id.private_key, KEY_SIZE, key_hex);

  std::fprintf(f,
               "{\n"
               "  \"device_id\": \"%s\",\n"
               "  \"private_key\": \"%s\",\n"
               "  \"created_at\": \"%s\"\n"
               "}\n",
               id.device_id, key_hex, id.created_at);

  std::fclose(f);
  return true;
}

static bool hex_to_bytes(const char *hex, uint8_t *out, int max_bytes) {
  for (int i = 0; i < max_bytes; ++i) {
    unsigned int byte;
    if (std::sscanf(hex + i * 2, "%2x", &byte) != 1)
      return false;
    out[i] = static_cast<uint8_t>(byte);
  }
  return true;
}

static bool load_identity(DeviceIdentity &id) {
  FILE *f = std::fopen(IDENTITY_PATH, "r");
  if (!f)
    return false;

  char buf[2048];
  std::memset(buf, 0, sizeof(buf));
  std::fread(buf, 1, sizeof(buf) - 1, f);
  std::fclose(f);

  // Parse device_id
  const char *did = std::strstr(buf, "\"device_id\"");
  if (!did)
    return false;
  const char *q1 = std::strchr(did + 11, '"');
  if (!q1)
    return false;
  q1++;
  const char *q2 = std::strchr(q1, '"');
  if (!q2 || (q2 - q1) != 64)
    return false;
  std::memcpy(id.device_id, q1, 64);
  id.device_id[64] = '\0';

  // Parse private_key
  const char *pk = std::strstr(buf, "\"private_key\"");
  if (!pk)
    return false;
  q1 = std::strchr(pk + 13, '"');
  if (!q1)
    return false;
  q1++;
  q2 = std::strchr(q1, '"');
  if (!q2 || (q2 - q1) != KEY_SIZE * 2)
    return false;

  char key_hex[KEY_SIZE * 2 + 1];
  std::memcpy(key_hex, q1, KEY_SIZE * 2);
  key_hex[KEY_SIZE * 2] = '\0';
  if (!hex_to_bytes(key_hex, id.private_key, KEY_SIZE))
    return false;

  id.loaded = true;
  return true;
}

// =========================================================================
// GENERATE OR LOAD
// =========================================================================

static bool ensure_identity() {
  if (g_identity.loaded)
    return true;

  // Try loading existing
  if (load_identity(g_identity)) {
    g_identity.loaded = true;
    return true;
  }

  // Generate new identity
  if (!secure_random(g_identity.private_key, KEY_SIZE)) {
    std::fprintf(stderr, "FATAL: CSPRNG failed — cannot generate device key\n");
    return false;
  }

  // Derive device_id = SHA-256(private_key)
  uint8_t hash[32];
  sha256(g_identity.private_key, KEY_SIZE, hash);
  bytes_to_hex(hash, 32, g_identity.device_id);

  // Timestamp
  std::time_t now = std::time(nullptr);
  struct std::tm *t = std::gmtime(&now);
  std::strftime(g_identity.created_at, sizeof(g_identity.created_at),
                "%Y-%m-%dT%H:%M:%SZ", t);

  g_identity.loaded = true;

  if (!save_identity(g_identity)) {
    std::fprintf(stderr, "WARNING: Could not persist device identity to %s\n",
                 IDENTITY_PATH);
    // Continue — identity is valid in memory
  }

  return true;
}

static const char *get_device_id() {
  if (!ensure_identity())
    return nullptr;
  return g_identity.device_id;
}

// =========================================================================
// SELF-TEST
// =========================================================================

#ifdef RUN_SELF_TEST
static int self_test() {
  int pass = 0, fail = 0;

  // Test CSPRNG
  uint8_t rng_out[32];
  bool rng_ok = secure_random(rng_out, 32);
  if (rng_ok) {
    ++pass;
  } else {
    ++fail;
  }

  // Test SHA-256: hash of empty string = known value
  uint8_t sha_out[32];
  sha256(nullptr, 0, sha_out);
  // SHA-256("") =
  // e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
  char sha_hex[65];
  bytes_to_hex(sha_out, 32, sha_hex);
  bool sha_ok =
      std::strcmp(
          sha_hex,
          "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855") ==
      0;
  if (sha_ok) {
    ++pass;
  } else {
    ++fail;
  }

  // Test identity generation
  DeviceIdentity test_id = {};
  secure_random(test_id.private_key, KEY_SIZE);
  sha256(test_id.private_key, KEY_SIZE, sha_out);
  bytes_to_hex(sha_out, 32, test_id.device_id);
  bool id_ok = std::strlen(test_id.device_id) == 64;
  if (id_ok) {
    ++pass;
  } else {
    ++fail;
  }

  // Test hex round-trip
  char hex_buf[KEY_SIZE * 2 + 1];
  bytes_to_hex(test_id.private_key, KEY_SIZE, hex_buf);
  uint8_t rt_key[KEY_SIZE];
  bool rt_ok = hex_to_bytes(hex_buf, rt_key, KEY_SIZE);
  rt_ok = rt_ok && (std::memcmp(test_id.private_key, rt_key, KEY_SIZE) == 0);
  if (rt_ok) {
    ++pass;
  } else {
    ++fail;
  }

  std::printf("device_identity self-test: %d passed, %d failed\n", pass, fail);
  return fail == 0 ? 0 : 1;
}
#endif

} // namespace device_identity
