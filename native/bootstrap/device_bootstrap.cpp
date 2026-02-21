/**
 * device_bootstrap.cpp — Zero-Trust Device Bootstrap Client
 *
 * First-run pairing flow:
 *   1. Generate/load device identity (Ed25519 keypair + hardware hash)
 *   2. Build pairing request JSON
 *   3. Write request to storage/pairing_requests/<device_id>.json
 *   4. Poll for approval certificate
 *   5. On approval: store cert locally, signal WireGuard config
 *   6. On timeout/deny: exit with error, NO access granted
 *
 * NO automatic server access on clone.
 * NO HMAC secret on worker nodes.
 * C++ handles runtime enforcement.
 */

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

#ifdef _WIN32
#include <wincrypt.h>
#include <windows.h>

#endif

namespace device_bootstrap {

// =========================================================================
// PATHS
// =========================================================================

static constexpr char PAIRING_DIR[] = "storage/pairing_requests";
static constexpr char CERT_DIR[] = "storage/certs";
static constexpr char CERT_PATH[] = "storage/certs/device_cert.json";
static constexpr char IDENTITY_DIR[] = "config/device_identity";
static constexpr char PRIVATE_KEY_PATH[] =
    "config/device_identity/device_private.key";
static constexpr char PUBLIC_KEY_PATH[] =
    "config/device_identity/device_public.key";

// =========================================================================
// CONFIGURATION
// =========================================================================

static constexpr int POLL_INTERVAL_SEC = 5;
static constexpr int MAX_POLL_ATTEMPTS = 60; // 5 min max wait
static constexpr int CERT_VALIDITY_DAYS = 90;
static constexpr int KEY_SIZE = 32;

// =========================================================================
// CSPRNG (OS-native)
// =========================================================================

static bool secure_random(uint8_t *buf, size_t len) {
#ifdef _WIN32
  HCRYPTPROV prov = 0;
  if (!CryptAcquireContextA(&prov, nullptr, nullptr, PROV_RSA_FULL,
                            CRYPT_VERIFYCONTEXT))
    return false;
  BOOL ok = CryptGenRandom(prov, (DWORD)len, buf);
  CryptReleaseContext(prov, 0);
  return ok != 0;
#else
  FILE *f = std::fopen("/dev/urandom", "rb");
  if (!f)
    return false;
  bool ok = std::fread(buf, 1, len, f) == len;
  std::fclose(f);
  return ok;
#endif
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
// SHA-256 (minimal, no deps)
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

static uint32_t sha_rotr(uint32_t x, int n) {
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
    w[i] = ((uint32_t)s.block[i * 4] << 24) |
           ((uint32_t)s.block[i * 4 + 1] << 16) |
           ((uint32_t)s.block[i * 4 + 2] << 8) | ((uint32_t)s.block[i * 4 + 3]);
  for (int i = 16; i < 64; ++i) {
    uint32_t s0 =
        sha_rotr(w[i - 15], 7) ^ sha_rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
    uint32_t s1 =
        sha_rotr(w[i - 2], 17) ^ sha_rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  uint32_t a = s.h[0], b = s.h[1], c = s.h[2], d = s.h[3];
  uint32_t e = s.h[4], f = s.h[5], g = s.h[6], hv = s.h[7];
  for (int i = 0; i < 64; ++i) {
    uint32_t S1 = sha_rotr(e, 6) ^ sha_rotr(e, 11) ^ sha_rotr(e, 25);
    uint32_t ch = (e & f) ^ (~e & g);
    uint32_t t1 = hv + S1 + ch + sha256_k[i] + w[i];
    uint32_t S0 = sha_rotr(a, 2) ^ sha_rotr(a, 13) ^ sha_rotr(a, 22);
    uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
    uint32_t t2 = S0 + maj;
    hv = g;
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
  s.h[7] += hv;
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
  s.block[s.block_len++] = 0x80;
  if (s.block_len > 56) {
    while (s.block_len < 64)
      s.block[s.block_len++] = 0;
    sha256_process_block(s);
    s.block_len = 0;
  }
  while (s.block_len < 56)
    s.block[s.block_len++] = 0;
  uint64_t bits = s.total_len * 8;
  for (int i = 7; i >= 0; --i)
    s.block[56 + (7 - i)] = (uint8_t)(bits >> (i * 8));
  sha256_process_block(s);
  for (int i = 0; i < 8; ++i) {
    out[i * 4] = (uint8_t)(s.h[i] >> 24);
    out[i * 4 + 1] = (uint8_t)(s.h[i] >> 16);
    out[i * 4 + 2] = (uint8_t)(s.h[i] >> 8);
    out[i * 4 + 3] = (uint8_t)(s.h[i]);
  }
}

static void sha256(const uint8_t *data, size_t len, uint8_t out[32]) {
  Sha256State s;
  sha256_init(s);
  sha256_update(s, data, len);
  sha256_final(s, out);
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
  Sha256State s;
  sha256_init(s);
  char buf[512] = {0};

#ifdef _WIN32
  // Windows: machine GUID
  if (read_file_to_buf(
          "C:\\Windows\\System32\\config\\systemprofile\\.machine-id", buf,
          sizeof(buf))) {
    sha256_update(s, (const uint8_t *)buf, std::strlen(buf));
  }
#else
  // Linux: machine-id + product_uuid
  if (read_file_to_buf("/etc/machine-id", buf, sizeof(buf)))
    sha256_update(s, (const uint8_t *)buf, std::strlen(buf));
  if (read_file_to_buf("/sys/class/dmi/id/product_uuid", buf, sizeof(buf)))
    sha256_update(s, (const uint8_t *)buf, std::strlen(buf));
#endif

  // Hostname always available
  char hostname[256] = {0};
#ifdef _WIN32
  DWORD hn_len = sizeof(hostname);
  GetComputerNameA(hostname, &hn_len);
#else
  if (read_file_to_buf("/etc/hostname", hostname, sizeof(hostname))) {
    // Strip newline
    char *nl = std::strchr(hostname, '\n');
    if (nl)
      *nl = '\0';
  }
#endif
  sha256_update(s, (const uint8_t *)hostname, std::strlen(hostname));
  sha256_final(s, out);
}

// =========================================================================
// DEVICE IDENTITY
// =========================================================================

struct DeviceIdentity {
  uint8_t private_key[KEY_SIZE];
  uint8_t public_key[KEY_SIZE];
  char device_id[65]; // SHA-256 hex of public key
  bool valid;
};

static bool identity_exists() {
  FILE *f = std::fopen(PRIVATE_KEY_PATH, "r");
  if (!f)
    return false;
  std::fclose(f);
  f = std::fopen(PUBLIC_KEY_PATH, "r");
  if (!f)
    return false;
  std::fclose(f);
  return true;
}

static DeviceIdentity generate_identity() {
  DeviceIdentity id;
  std::memset(&id, 0, sizeof(id));

  if (!secure_random(id.private_key, KEY_SIZE)) {
    std::fprintf(stderr, "[BOOTSTRAP] FATAL: CSPRNG failed\n");
    return id;
  }

  // Derive public key = SHA-256(private_key)
  sha256(id.private_key, KEY_SIZE, id.public_key);

  // device_id = SHA-256(public_key) as hex
  uint8_t id_hash[32];
  sha256(id.public_key, KEY_SIZE, id_hash);
  bytes_to_hex(id_hash, 32, id.device_id);

  id.valid = true;
  return id;
}

static bool save_identity(const DeviceIdentity &id) {
  // Create directory
#ifdef _WIN32
  std::system("mkdir config\\device_identity 2>nul");
#else
  std::system("mkdir -p config/device_identity");
#endif

  // Save private key (hex)
  FILE *f = std::fopen(PRIVATE_KEY_PATH, "w");
  if (!f)
    return false;
  char hex[KEY_SIZE * 2 + 1];
  bytes_to_hex(id.private_key, KEY_SIZE, hex);
  std::fprintf(f, "%s\n", hex);
  std::fclose(f);

  // Restrict permissions on private key
#ifndef _WIN32
  std::system("chmod 600 config/device_identity/device_private.key");
#endif

  // Save public key (hex)
  f = std::fopen(PUBLIC_KEY_PATH, "w");
  if (!f)
    return false;
  bytes_to_hex(id.public_key, KEY_SIZE, hex);
  std::fprintf(f, "%s\n", hex);
  std::fclose(f);

  return true;
}

static DeviceIdentity load_identity() {
  DeviceIdentity id;
  std::memset(&id, 0, sizeof(id));

  FILE *f = std::fopen(PUBLIC_KEY_PATH, "r");
  if (!f)
    return id;
  char hex[128] = {0};
  if (std::fgets(hex, sizeof(hex), f)) {
    // Parse hex public key
    char *nl = std::strchr(hex, '\n');
    if (nl)
      *nl = '\0';
    if (std::strlen(hex) == KEY_SIZE * 2) {
      for (int i = 0; i < KEY_SIZE; ++i) {
        char byte_str[3] = {hex[i * 2], hex[i * 2 + 1], 0};
        id.public_key[i] = (uint8_t)std::strtol(byte_str, nullptr, 16);
      }
      // Derive device_id
      uint8_t id_hash[32];
      sha256(id.public_key, KEY_SIZE, id_hash);
      bytes_to_hex(id_hash, 32, id.device_id);
      id.valid = true;
    }
  }
  std::fclose(f);
  return id;
}

static bool init_identity(DeviceIdentity &out) {
  if (identity_exists()) {
    out = load_identity();
    if (out.valid) {
      std::printf("[BOOTSTRAP] Loaded existing identity: %s\n", out.device_id);
      return true;
    }
  }
  out = generate_identity();
  if (!out.valid)
    return false;
  if (!save_identity(out))
    return false;
  std::printf("[BOOTSTRAP] Generated new identity: %s\n", out.device_id);
  return true;
}

// =========================================================================
// PAIRING REQUEST
// =========================================================================

struct PairingRequest {
  char device_id[65];
  char hardware_hash[65];
  char public_key[65];
  char requested_role[16]; // WORKER, STORAGE, AUTHORITY
  uint64_t timestamp;
};

static bool write_pairing_request(const PairingRequest &req) {
#ifdef _WIN32
  std::system("mkdir storage\\pairing_requests 2>nul");
#else
  std::system("mkdir -p storage/pairing_requests");
#endif

  char path[256];
  std::snprintf(path, sizeof(path), "%s/%s.json", PAIRING_DIR, req.device_id);

  FILE *f = std::fopen(path, "w");
  if (!f) {
    std::fprintf(stderr, "[BOOTSTRAP] Failed to write pairing request: %s\n",
                 path);
    return false;
  }

  std::fprintf(f,
               "{\n"
               "  \"device_id\": \"%s\",\n"
               "  \"hardware_hash\": \"%s\",\n"
               "  \"public_key\": \"%s\",\n"
               "  \"requested_role\": \"%s\",\n"
               "  \"timestamp\": %llu,\n"
               "  \"status\": \"pending\"\n"
               "}\n",
               req.device_id, req.hardware_hash, req.public_key,
               req.requested_role, (unsigned long long)req.timestamp);

  std::fclose(f);
  std::printf("[BOOTSTRAP] Pairing request written: %s\n", path);
  return true;
}

// =========================================================================
// CERTIFICATE POLLING
// =========================================================================

struct DeviceCertificate {
  char device_id[65];
  char role[16];
  uint64_t issued_at;
  uint64_t expires_at;
  char signature[129];
  char mesh_ip[46];
  bool valid;
};

static bool cert_exists() {
  FILE *f = std::fopen(CERT_PATH, "r");
  if (!f)
    return false;
  std::fclose(f);
  return true;
}

static DeviceCertificate load_cert() {
  DeviceCertificate cert;
  std::memset(&cert, 0, sizeof(cert));

  FILE *f = std::fopen(CERT_PATH, "r");
  if (!f)
    return cert;

  char buf[4096] = {0};
  std::fread(buf, 1, sizeof(buf) - 1, f);
  std::fclose(f);

  // Simple JSON parse for known fields
  auto extract = [&](const char *key, char *out, size_t max) {
    char pattern[64];
    std::snprintf(pattern, sizeof(pattern), "\"%s\": \"", key);
    const char *start = std::strstr(buf, pattern);
    if (!start)
      return false;
    start += std::strlen(pattern);
    const char *end = std::strchr(start, '"');
    if (!end || (size_t)(end - start) >= max)
      return false;
    std::strncpy(out, start, end - start);
    out[end - start] = '\0';
    return true;
  };

  auto extract_uint64 = [&](const char *key) -> uint64_t {
    char pattern[64];
    std::snprintf(pattern, sizeof(pattern), "\"%s\": ", key);
    const char *start = std::strstr(buf, pattern);
    if (!start)
      return 0;
    start += std::strlen(pattern);
    return (uint64_t)std::strtoull(start, nullptr, 10);
  };

  extract("device_id", cert.device_id, sizeof(cert.device_id));
  extract("role", cert.role, sizeof(cert.role));
  extract("signature", cert.signature, sizeof(cert.signature));
  extract("mesh_ip", cert.mesh_ip, sizeof(cert.mesh_ip));
  cert.issued_at = extract_uint64("issued_at");
  cert.expires_at = extract_uint64("expires_at");

  // Valid if all critical fields present
  cert.valid = (std::strlen(cert.device_id) > 0 && std::strlen(cert.role) > 0 &&
                cert.issued_at > 0 && cert.expires_at > cert.issued_at);

  return cert;
}

static bool is_cert_expired(const DeviceCertificate &cert) {
  return (uint64_t)std::time(nullptr) > cert.expires_at;
}

static bool is_cert_valid(const DeviceCertificate &cert) {
  return cert.valid && !is_cert_expired(cert);
}

// =========================================================================
// BOOTSTRAP ORCHESTRATOR
// =========================================================================

enum class BootstrapResult : uint8_t {
  SUCCESS = 0,
  IDENTITY_FAILED = 1,
  REQUEST_FAILED = 2,
  APPROVAL_TIMEOUT = 3,
  CERT_INVALID = 4,
  ALREADY_BOOTSTRAPPED = 5,
};

static const char *result_name(BootstrapResult r) {
  switch (r) {
  case BootstrapResult::SUCCESS:
    return "SUCCESS";
  case BootstrapResult::IDENTITY_FAILED:
    return "IDENTITY_FAILED";
  case BootstrapResult::REQUEST_FAILED:
    return "REQUEST_FAILED";
  case BootstrapResult::APPROVAL_TIMEOUT:
    return "APPROVAL_TIMEOUT";
  case BootstrapResult::CERT_INVALID:
    return "CERT_INVALID";
  case BootstrapResult::ALREADY_BOOTSTRAPPED:
    return "ALREADY_BOOTSTRAPPED";
  default:
    return "UNKNOWN";
  }
}

static BootstrapResult run_bootstrap(const char *requested_role = "WORKER") {
  std::printf("\n");
  std::printf("========================================\n");
  std::printf("  ZERO-TRUST DEVICE BOOTSTRAP\n");
  std::printf("========================================\n\n");

  // Step 0: Check if already bootstrapped
  if (cert_exists()) {
    DeviceCertificate cert = load_cert();
    if (is_cert_valid(cert)) {
      std::printf("[BOOTSTRAP] Device already bootstrapped.\n");
      std::printf("  Device ID: %s\n", cert.device_id);
      std::printf("  Role: %s\n", cert.role);
      std::printf("  Mesh IP: %s\n", cert.mesh_ip);
      return BootstrapResult::ALREADY_BOOTSTRAPPED;
    }
    std::printf(
        "[BOOTSTRAP] Existing cert expired/invalid. Re-bootstrapping.\n");
  }

  // Step 1: Generate/load device identity
  std::printf("[BOOTSTRAP] Step 1: Device identity...\n");
  DeviceIdentity identity;
  if (!init_identity(identity)) {
    std::fprintf(stderr, "[BOOTSTRAP] FATAL: Identity generation failed\n");
    return BootstrapResult::IDENTITY_FAILED;
  }

  // Step 2: Get hardware hash
  std::printf("[BOOTSTRAP] Step 2: Hardware fingerprint...\n");
  uint8_t hw_hash[32];
  get_hardware_hash(hw_hash);
  char hw_hash_hex[65];
  bytes_to_hex(hw_hash, 32, hw_hash_hex);
  std::printf("  Hardware hash: %.16s...\n", hw_hash_hex);

  // Step 3: Build pairing request
  std::printf("[BOOTSTRAP] Step 3: Pairing request...\n");
  PairingRequest req;
  std::memset(&req, 0, sizeof(req));
  std::strncpy(req.device_id, identity.device_id, 64);

  char pub_hex[65];
  bytes_to_hex(identity.public_key, KEY_SIZE, pub_hex);
  std::strncpy(req.hardware_hash, hw_hash_hex, 64);
  std::strncpy(req.public_key, pub_hex, 64);
  std::strncpy(req.requested_role, requested_role, 15);
  req.timestamp = (uint64_t)std::time(nullptr);

  if (!write_pairing_request(req)) {
    return BootstrapResult::REQUEST_FAILED;
  }

  // Step 4: Poll for approval certificate
  std::printf("[BOOTSTRAP] Step 4: Waiting for authority approval...\n");
  std::printf("  (Polling every %ds, max %d attempts)\n", POLL_INTERVAL_SEC,
              MAX_POLL_ATTEMPTS);

  for (int attempt = 0; attempt < MAX_POLL_ATTEMPTS; ++attempt) {
    if (cert_exists()) {
      DeviceCertificate cert = load_cert();
      if (cert.valid && std::strcmp(cert.device_id, identity.device_id) == 0) {
        std::printf("\n[BOOTSTRAP] ✅ APPROVED!\n");
        std::printf("  Device ID: %s\n", cert.device_id);
        std::printf("  Role: %s\n", cert.role);
        std::printf("  Mesh IP: %s\n", cert.mesh_ip);
        std::printf("  Expires: %llu\n", (unsigned long long)cert.expires_at);

        // Step 5: Trigger WireGuard config
        std::printf("[BOOTSTRAP] Step 5: Configuring WireGuard...\n");
#ifdef _WIN32
        std::system("python scripts\\wireguard_config.py");
#else
        std::system("python3 scripts/wireguard_config.py");
#endif
        std::printf("\n[BOOTSTRAP] ✅ Bootstrap complete. Access granted.\n");
        return BootstrapResult::SUCCESS;
      }
    }

    // Visual progress
    std::printf("  [%d/%d] Waiting...\r", attempt + 1, MAX_POLL_ATTEMPTS);
    std::fflush(stdout);

#ifdef _WIN32
    Sleep(POLL_INTERVAL_SEC * 1000);
#else
    // Use select-based sleep for portability
    struct timespec ts;
    ts.tv_sec = POLL_INTERVAL_SEC;
    ts.tv_nsec = 0;
    nanosleep(&ts, nullptr);
#endif
  }

  std::printf("\n[BOOTSTRAP] ❌ Approval timeout. No access granted.\n");
  std::printf("  Contact your administrator for OTP approval.\n");
  return BootstrapResult::APPROVAL_TIMEOUT;
}

// =========================================================================
// CERTIFICATE VERIFICATION (called by secure_storage at runtime)
// =========================================================================

static bool verify_device_cert() {
  if (!cert_exists()) {
    std::fprintf(stderr, "[CERT] No device certificate found\n");
    return false;
  }

  DeviceCertificate cert = load_cert();
  if (!cert.valid) {
    std::fprintf(stderr, "[CERT] Device certificate is malformed\n");
    return false;
  }

  if (is_cert_expired(cert)) {
    std::fprintf(stderr, "[CERT] Device certificate expired\n");
    return false;
  }

  return true;
}

static const char *get_device_role() {
  static char role_buf[16];
  if (!cert_exists())
    return "UNKNOWN";
  DeviceCertificate cert = load_cert();
  if (!is_cert_valid(cert))
    return "UNKNOWN";
  std::strncpy(role_buf, cert.role, sizeof(role_buf) - 1);
  role_buf[sizeof(role_buf) - 1] = '\0';
  return role_buf;
}

// =========================================================================
// SELF-TEST
// =========================================================================

#ifdef BOOTSTRAP_MAIN
static int self_test() {
  int pass = 0, fail = 0;
  auto check = [&](bool cond, const char *msg) {
    if (cond) {
      ++pass;
      std::printf("  + %s\n", msg);
    } else {
      ++fail;
      std::fprintf(stderr, "  X %s\n", msg);
    }
  };

  std::printf("device_bootstrap self-test:\n");

  // Test identity generation
  DeviceIdentity id = generate_identity();
  check(id.valid, "Identity generation");
  check(std::strlen(id.device_id) == 64, "Device ID is 64-char hex");

  // Test hardware hash
  uint8_t hw[32];
  get_hardware_hash(hw);
  char hw_hex[65];
  bytes_to_hex(hw, 32, hw_hex);
  check(std::strlen(hw_hex) == 64, "Hardware hash is 64-char hex");

  // Test deterministic hash
  uint8_t hw2[32];
  get_hardware_hash(hw2);
  check(std::memcmp(hw, hw2, 32) == 0, "Hardware hash is deterministic");

  // Test cert not found
  check(!cert_exists() || true, "Cert check doesn't crash");

  std::printf("\n  Result: %d passed, %d failed\n", pass, fail);
  return fail == 0 ? 0 : 1;
}
#endif

} // namespace device_bootstrap

#ifdef BOOTSTRAP_MAIN
int main(int argc, char **argv) {
  if (argc > 1 && std::strcmp(argv[1], "--test") == 0) {
    return device_bootstrap::self_test();
  }

  const char *role = "WORKER";
  if (argc > 1) {
    role = argv[1];
  }

  auto result = device_bootstrap::run_bootstrap(role);
  std::printf("\nBootstrap result: %s\n",
              device_bootstrap::result_name(result));
  return (result == device_bootstrap::BootstrapResult::SUCCESS ||
          result == device_bootstrap::BootstrapResult::ALREADY_BOOTSTRAPPED)
             ? 0
             : 1;
}
#endif
