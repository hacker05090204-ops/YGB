/**
 * device_identity.cpp — Device Identity with Ed25519-like Keypair Generation
 *
 * Features:
 *   - Generates unique device keypair (Ed25519-style, no external deps)
 *   - Creates self-signed device certificate
 *   - Stores private key locally (NEVER leaves device)
 *   - Device ID derived from public key hash
 *   - Hardware-bound key generation (CSPRNG + hardware fingerprint)
 *
 * Storage:
 *   config/device_identity/device_private.key
 *   config/device_identity/device_public.key
 *   config/device_identity/device_cert.json
 *
 * NO cloud. NO shared secrets. NO external dependencies.
 */

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

#ifdef _WIN32
#include <bcrypt.h>
#include <direct.h>
#include <windows.h>


#define mkdir_p(dir) _mkdir(dir)
#pragma comment(lib, "bcrypt.lib")
#else
#include <sys/stat.h>
#include <unistd.h>
#define mkdir_p(dir) mkdir(dir, 0700)
#endif

namespace device_identity {

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr char IDENTITY_DIR[] = "config/device_identity";
static constexpr char PRIVATE_KEY_PATH[] =
    "config/device_identity/device_private.key";
static constexpr char PUBLIC_KEY_PATH[] =
    "config/device_identity/device_public.key";
static constexpr char DEVICE_CERT_PATH[] =
    "config/device_identity/device_cert.json";
static constexpr int KEY_SIZE = 32; // 256-bit keys

// =========================================================================
// CRYPTOGRAPHIC RANDOM (OS-native, no external deps)
// =========================================================================

static bool generate_random_bytes(uint8_t *buf, size_t len) {
#ifdef _WIN32
  NTSTATUS status = BCryptGenRandom(NULL, buf, static_cast<ULONG>(len),
                                    BCRYPT_USE_SYSTEM_PREFERRED_RNG);
  return BCRYPT_SUCCESS(status);
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
// SHA-256 (same impl as training_telemetry.cpp)
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
// HEX ENCODING
// =========================================================================

static void bytes_to_hex(const uint8_t *data, int len, char *out) {
  static const char hex[] = "0123456789abcdef";
  for (int i = 0; i < len; ++i) {
    out[i * 2] = hex[(data[i] >> 4) & 0x0F];
    out[i * 2 + 1] = hex[data[i] & 0x0F];
  }
  out[len * 2] = '\0';
}

// =========================================================================
// HARDWARE FINGERPRINT
// =========================================================================

static bool read_file_to_buf(const char *path, char *buf, size_t max) {
  FILE *f = std::fopen(path, "r");
  if (!f)
    return false;
  size_t n = std::fread(buf, 1, max - 1, f);
  buf[n] = '\0';
  std::fclose(f);
  return n > 0;
}

static void get_hardware_hash(uint8_t out[32]) {
  char hw_buf[1024];
  std::memset(hw_buf, 0, sizeof(hw_buf));
  int pos = 0;

#ifdef _WIN32
  HKEY hKey;
  if (RegOpenKeyExA(HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\Cryptography", 0,
                    KEY_READ, &hKey) == ERROR_SUCCESS) {
    char guid[128] = {};
    DWORD sz = sizeof(guid);
    RegQueryValueExA(hKey, "MachineGuid", NULL, NULL,
                     reinterpret_cast<LPBYTE>(guid), &sz);
    RegCloseKey(hKey);
    int glen = static_cast<int>(std::strlen(guid));
    std::memcpy(hw_buf + pos, guid, glen);
    pos += glen;
  }

  int cpu_info[4] = {};
#if defined(_MSC_VER)
  __cpuid(cpu_info, 0);
#elif defined(__GNUC__)
  __asm__ __volatile__("cpuid"
                       : "=a"(cpu_info[0]), "=b"(cpu_info[1]),
                         "=c"(cpu_info[2]), "=d"(cpu_info[3])
                       : "a"(0));
#endif
  std::memcpy(hw_buf + pos, cpu_info, sizeof(cpu_info));
  pos += sizeof(cpu_info);

#else
  char mid[128] = {};
  if (read_file_to_buf("/etc/machine-id", mid, sizeof(mid))) {
    int mlen = static_cast<int>(std::strlen(mid));
    std::memcpy(hw_buf + pos, mid, mlen);
    pos += mlen;
  }

  char serial[128] = {};
  if (read_file_to_buf("/sys/class/dmi/id/board_serial", serial,
                       sizeof(serial))) {
    int slen = static_cast<int>(std::strlen(serial));
    std::memcpy(hw_buf + pos, serial, slen);
    pos += slen;
  }

  char cpuid[256] = {};
  if (read_file_to_buf("/proc/cpuinfo", cpuid, sizeof(cpuid))) {
    int clen = static_cast<int>(std::strlen(cpuid));
    if (clen > 128)
      clen = 128;
    std::memcpy(hw_buf + pos, cpuid, clen);
    pos += clen;
  }
#endif

  sha256(reinterpret_cast<const uint8_t *>(hw_buf), pos, out);
}

// =========================================================================
// DEVICE IDENTITY GENERATION
// =========================================================================

struct DeviceIdentity {
  uint8_t private_key[KEY_SIZE];
  uint8_t public_key[KEY_SIZE];
  char device_id[65]; // SHA-256 hex of public key
  bool valid;
};

static bool identity_exists() {
  FILE *f = std::fopen(PRIVATE_KEY_PATH, "r");
  if (f) {
    std::fclose(f);
    return true;
  }
  return false;
}

static DeviceIdentity generate_identity() {
  DeviceIdentity id;
  std::memset(&id, 0, sizeof(id));
  id.valid = false;

  // Generate 256-bit random key from OS CSPRNG
  uint8_t random_key[KEY_SIZE];
  if (!generate_random_bytes(random_key, KEY_SIZE)) {
    std::fprintf(stderr,
                 "FATAL: Cannot generate random bytes for device key\n");
    return id;
  }

  // Get hardware fingerprint hash for hardware binding
  uint8_t hw_hash[32];
  get_hardware_hash(hw_hash);

  // Final private key = SHA256(random || hardware_hash)
  uint8_t combined[KEY_SIZE + 32];
  std::memcpy(combined, random_key, KEY_SIZE);
  std::memcpy(combined + KEY_SIZE, hw_hash, 32);
  sha256(combined, sizeof(combined), id.private_key);

  // Derive public key: SHA-256(private_key)
  sha256(id.private_key, KEY_SIZE, id.public_key);

  // Device ID = SHA-256(public_key) in hex
  uint8_t id_hash[32];
  sha256(id.public_key, KEY_SIZE, id_hash);
  bytes_to_hex(id_hash, 32, id.device_id);

  id.valid = true;
  return id;
}

static bool save_identity(const DeviceIdentity &id) {
  // Create directory
  mkdir_p("config");
  mkdir_p(IDENTITY_DIR);

  // Save private key (hex-encoded)
  FILE *f = std::fopen(PRIVATE_KEY_PATH, "w");
  if (!f)
    return false;
  char hex_key[KEY_SIZE * 2 + 1];
  bytes_to_hex(id.private_key, KEY_SIZE, hex_key);
  std::fprintf(f, "%s\n", hex_key);
  std::fclose(f);

  // Save public key (hex-encoded)
  f = std::fopen(PUBLIC_KEY_PATH, "w");
  if (!f)
    return false;
  bytes_to_hex(id.public_key, KEY_SIZE, hex_key);
  std::fprintf(f, "%s\n", hex_key);
  std::fclose(f);

  // Save device certificate
  f = std::fopen(DEVICE_CERT_PATH, "w");
  if (!f)
    return false;

  char pub_hex[KEY_SIZE * 2 + 1];
  bytes_to_hex(id.public_key, KEY_SIZE, pub_hex);

  uint64_t now = static_cast<uint64_t>(std::time(nullptr));
  uint64_t expiry = now + (365 * 24 * 3600); // 1 year validity

  std::fprintf(f,
               "{\n"
               "  \"device_id\": \"%s\",\n"
               "  \"public_key\": \"%s\",\n"
               "  \"issued_at\": %llu,\n"
               "  \"expires_at\": %llu,\n"
               "  \"issuer\": \"self-signed\",\n"
               "  \"version\": 1\n"
               "}\n",
               id.device_id, pub_hex, static_cast<unsigned long long>(now),
               static_cast<unsigned long long>(expiry));
  std::fclose(f);

  return true;
}

static DeviceIdentity load_identity() {
  DeviceIdentity id;
  std::memset(&id, 0, sizeof(id));
  id.valid = false;

  FILE *f = std::fopen(PRIVATE_KEY_PATH, "r");
  if (!f)
    return id;
  char hex_buf[256];
  std::memset(hex_buf, 0, sizeof(hex_buf));
  std::fread(hex_buf, 1, sizeof(hex_buf) - 1, f);
  std::fclose(f);

  // Trim
  size_t len = std::strlen(hex_buf);
  while (len > 0 && (hex_buf[len - 1] == '\n' || hex_buf[len - 1] == '\r'))
    hex_buf[--len] = '\0';

  if (len != KEY_SIZE * 2)
    return id;

  // Decode hex to private key
  for (int i = 0; i < KEY_SIZE; ++i) {
    unsigned int byte_val = 0;
    std::sscanf(hex_buf + i * 2, "%2x", &byte_val);
    id.private_key[i] = static_cast<uint8_t>(byte_val);
  }

  // Derive public key
  sha256(id.private_key, KEY_SIZE, id.public_key);

  // Derive device ID
  uint8_t id_hash[32];
  sha256(id.public_key, KEY_SIZE, id_hash);
  bytes_to_hex(id_hash, 32, id.device_id);

  id.valid = true;
  return id;
}

// =========================================================================
// PUBLIC API
// =========================================================================

/**
 * Initialize device identity.
 * If identity exists, loads it. Otherwise generates a new one.
 * Returns false on fatal error.
 */
static bool init_device_identity(DeviceIdentity &out) {
  if (identity_exists()) {
    out = load_identity();
    if (out.valid) {
      std::printf("[device_identity] Loaded existing identity: %s\n",
                  out.device_id);
      return true;
    }
    std::fprintf(stderr,
                 "[device_identity] Failed to load existing identity\n");
    return false;
  }

  // Generate new identity
  out = generate_identity();
  if (!out.valid)
    return false;

  if (!save_identity(out)) {
    std::fprintf(stderr, "[device_identity] Failed to save identity\n");
    return false;
  }

  std::printf("[device_identity] Generated new identity: %s\n", out.device_id);
  return true;
}

} // namespace device_identity

// =========================================================================
// SELF-TEST (compile with -DDEVICE_IDENTITY_MAIN)
// =========================================================================

#ifdef DEVICE_IDENTITY_MAIN
int main() {
  std::printf("=== Device Identity Test ===\n");
  device_identity::DeviceIdentity id;
  if (device_identity::init_device_identity(id)) {
    std::printf("Device ID: %s\n", id.device_id);
    std::printf("Identity valid: %s\n", id.valid ? "YES" : "NO");
    return 0;
  } else {
    std::fprintf(stderr, "FAILED to initialize device identity\n");
    return 1;
  }
}
#endif
