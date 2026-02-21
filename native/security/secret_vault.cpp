/**
 * secret_vault.cpp — AES-256-GCM Secret Vault (Phase 2 + 3 + 6)
 *
 * Features:
 *   - AES-256-GCM encryption (no external deps, portable impl)
 *   - Master key injected via vault_set_master_key() API (PBKDF2-derived)
 *   - Encrypted storage in ./secure_data/
 *   - Per-user data isolation (user_id scoping)
 *   - Startup permission check (abort if world-readable)
 *
 * Security comes from ENCRYPTION, not name obfuscation.
 * No special folder names. No security theater.
 *
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


#else
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace secret_vault {

// =========================================================================
// PATHS & CONSTANTS
// =========================================================================

static constexpr char VAULT_DIR[] = "secure_data";
static constexpr int AES_KEY_SIZE = 32; // 256 bits
static constexpr int AES_IV_SIZE = 12;  // 96 bits for GCM
static constexpr int AES_TAG_SIZE = 16; // 128-bit auth tag
static constexpr int AES_BLOCK_SIZE = 16;
static constexpr int MAX_PLAINTEXT_SIZE = 1024 * 1024; // 1 MB max

// =========================================================================
// CSPRNG
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
  static const char h[] = "0123456789abcdef";
  for (int i = 0; i < len; ++i) {
    out[i * 2] = h[(data[i] >> 4) & 0x0F];
    out[i * 2 + 1] = h[data[i] & 0x0F];
  }
  out[len * 2] = '\0';
}

static bool hex_to_bytes(const char *hex, uint8_t *out, int max_bytes) {
  int len = (int)std::strlen(hex);
  if (len % 2 != 0 || len / 2 > max_bytes)
    return false;
  for (int i = 0; i < len / 2; ++i) {
    char byte_str[3] = {hex[i * 2], hex[i * 2 + 1], 0};
    out[i] = (uint8_t)std::strtol(byte_str, nullptr, 16);
  }
  return true;
}

// =========================================================================
// SHA-256 (for key derivation)
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

static uint32_t rotr(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }

static void sha256(const uint8_t *data, size_t len, uint8_t out[32]) {
  uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                   0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  uint8_t block[64];
  uint64_t total_len = 0;
  int block_len = 0;

  auto process_block = [&]() {
    uint32_t w[64];
    for (int i = 0; i < 16; ++i)
      w[i] = ((uint32_t)block[i * 4] << 24) |
             ((uint32_t)block[i * 4 + 1] << 16) |
             ((uint32_t)block[i * 4 + 2] << 8) | block[i * 4 + 3];
    for (int i = 16; i < 64; ++i) {
      uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
      uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5],
             g = h[6], hv = h[7];
    for (int i = 0; i < 64; ++i) {
      uint32_t S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      uint32_t ch = (e & f) ^ (~e & g);
      uint32_t t1 = hv + S1 + ch + sha256_k[i] + w[i];
      uint32_t S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
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
    h[0] += a;
    h[1] += b;
    h[2] += c;
    h[3] += d;
    h[4] += e;
    h[5] += f;
    h[6] += g;
    h[7] += hv;
  };

  for (size_t i = 0; i < len; ++i) {
    block[block_len++] = data[i];
    if (block_len == 64) {
      process_block();
      block_len = 0;
    }
  }
  total_len = len;

  block[block_len++] = 0x80;
  if (block_len > 56) {
    while (block_len < 64)
      block[block_len++] = 0;
    process_block();
    block_len = 0;
  }
  while (block_len < 56)
    block[block_len++] = 0;
  uint64_t bits = total_len * 8;
  for (int i = 7; i >= 0; --i)
    block[56 + (7 - i)] = (uint8_t)(bits >> (i * 8));
  process_block();

  for (int i = 0; i < 8; ++i) {
    out[i * 4] = (uint8_t)(h[i] >> 24);
    out[i * 4 + 1] = (uint8_t)(h[i] >> 16);
    out[i * 4 + 2] = (uint8_t)(h[i] >> 8);
    out[i * 4 + 3] = (uint8_t)h[i];
  }
}

// =========================================================================
// AES-256 CORE (Rijndael, portable C implementation)
// =========================================================================

static const uint8_t AES_SBOX[256] = {
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b,
    0xfe, 0xd7, 0xab, 0x76, 0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0,
    0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0, 0xb7, 0xfd, 0x93, 0x26,
    0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2,
    0xeb, 0x27, 0xb2, 0x75, 0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0,
    0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84, 0x53, 0xd1, 0x00, 0xed,
    0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f,
    0x50, 0x3c, 0x9f, 0xa8, 0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5,
    0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2, 0xcd, 0x0c, 0x13, 0xec,
    0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14,
    0xde, 0x5e, 0x0b, 0xdb, 0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c,
    0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79, 0xe7, 0xc8, 0x37, 0x6d,
    0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f,
    0x4b, 0xbd, 0x8b, 0x8a, 0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e,
    0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e, 0xe1, 0xf8, 0x98, 0x11,
    0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f,
    0xb0, 0x54, 0xbb, 0x16};

static const uint8_t AES_RCON[11] = {0x00, 0x01, 0x02, 0x04, 0x08, 0x10,
                                     0x20, 0x40, 0x80, 0x1B, 0x36};

// GF multiply
static uint8_t gf_mul(uint8_t a, uint8_t b) {
  uint8_t p = 0;
  for (int i = 0; i < 8; ++i) {
    if (b & 1)
      p ^= a;
    bool hi = a & 0x80;
    a <<= 1;
    if (hi)
      a ^= 0x1B;
    b >>= 1;
  }
  return p;
}

struct AesKey {
  uint8_t round_keys[15][16]; // Up to 14 rounds for AES-256
  int rounds;
};

static void aes_key_expand(const uint8_t key[32], AesKey &ek) {
  ek.rounds = 14; // AES-256
  uint8_t w[240];
  std::memcpy(w, key, 32);

  int i = 8; // 8 words for 256-bit key
  while (i < 4 * (ek.rounds + 1)) {
    uint8_t temp[4];
    std::memcpy(temp, &w[(i - 1) * 4], 4);

    if (i % 8 == 0) {
      // RotWord + SubWord + Rcon
      uint8_t t = temp[0];
      temp[0] = AES_SBOX[temp[1]] ^ AES_RCON[i / 8];
      temp[1] = AES_SBOX[temp[2]];
      temp[2] = AES_SBOX[temp[3]];
      temp[3] = AES_SBOX[t];
    } else if (i % 8 == 4) {
      // SubWord only
      for (int j = 0; j < 4; ++j)
        temp[j] = AES_SBOX[temp[j]];
    }

    for (int j = 0; j < 4; ++j)
      w[i * 4 + j] = w[(i - 8) * 4 + j] ^ temp[j];
    ++i;
  }

  for (int r = 0; r <= ek.rounds; ++r)
    std::memcpy(ek.round_keys[r], &w[r * 16], 16);
}

static void aes_encrypt_block(const uint8_t in[16], uint8_t out[16],
                              const AesKey &ek) {
  uint8_t state[16];
  std::memcpy(state, in, 16);

  // AddRoundKey
  for (int i = 0; i < 16; ++i)
    state[i] ^= ek.round_keys[0][i];

  for (int r = 1; r <= ek.rounds; ++r) {
    // SubBytes
    for (int i = 0; i < 16; ++i)
      state[i] = AES_SBOX[state[i]];

    // ShiftRows
    uint8_t tmp;
    tmp = state[1];
    state[1] = state[5];
    state[5] = state[9];
    state[9] = state[13];
    state[13] = tmp;
    tmp = state[2];
    state[2] = state[10];
    state[10] = tmp;
    tmp = state[6];
    state[6] = state[14];
    state[14] = tmp;
    tmp = state[15];
    state[15] = state[11];
    state[11] = state[7];
    state[7] = state[3];
    state[3] = tmp;

    // MixColumns (skip in last round)
    if (r < ek.rounds) {
      for (int c = 0; c < 4; ++c) {
        int ci = c * 4;
        uint8_t a0 = state[ci], a1 = state[ci + 1], a2 = state[ci + 2],
                a3 = state[ci + 3];
        state[ci] = gf_mul(a0, 2) ^ gf_mul(a1, 3) ^ a2 ^ a3;
        state[ci + 1] = a0 ^ gf_mul(a1, 2) ^ gf_mul(a2, 3) ^ a3;
        state[ci + 2] = a0 ^ a1 ^ gf_mul(a2, 2) ^ gf_mul(a3, 3);
        state[ci + 3] = gf_mul(a0, 3) ^ a1 ^ a2 ^ gf_mul(a3, 2);
      }
    }

    // AddRoundKey
    for (int i = 0; i < 16; ++i)
      state[i] ^= ek.round_keys[r][i];
  }

  std::memcpy(out, state, 16);
}

// =========================================================================
// GCM MODE (Counter + GHASH)
// =========================================================================

// GCM: multiply in GF(2^128)
static void ghash_mul(uint8_t x[16], const uint8_t h[16]) {
  uint8_t z[16] = {0};
  uint8_t v[16];
  std::memcpy(v, h, 16);

  for (int i = 0; i < 128; ++i) {
    if ((x[i / 8] >> (7 - (i % 8))) & 1) {
      for (int j = 0; j < 16; ++j)
        z[j] ^= v[j];
    }
    bool lsb = v[15] & 1;
    for (int j = 15; j > 0; --j)
      v[j] = (v[j] >> 1) | ((v[j - 1] & 1) << 7);
    v[0] >>= 1;
    if (lsb)
      v[0] ^= 0xE1; // R polynomial
  }
  std::memcpy(x, z, 16);
}

struct VaultResult {
  bool success;
  size_t output_len;
  char error[128];
};

// =========================================================================
// MASTER KEY — API-injected (from PBKDF2 derivation in Python layer)
// =========================================================================

static uint8_t g_master_key[32] = {0};
static bool g_master_key_set = false;

// Set the master key from an external source (Python PBKDF2 derivation).
// Key must be exactly 32 bytes (AES-256).
void vault_set_master_key(const uint8_t key[32]) {
  std::memcpy(g_master_key, key, 32);
  g_master_key_set = true;
  std::fprintf(stderr, "[VAULT] Master key set via API\n");
}

// Securely clear the master key from memory.
void vault_clear_master_key() {
  volatile uint8_t *p = g_master_key;
  for (int i = 0; i < 32; ++i)
    p[i] = 0;
  g_master_key_set = false;
  std::fprintf(stderr, "[VAULT] Master key cleared\n");
}

// Check if vault is unlocked (master key set).
bool vault_is_unlocked() { return g_master_key_set; }

static bool load_master_key(uint8_t key[32]) {
  // Primary: use API-injected key (from PBKDF2 derivation)
  if (g_master_key_set) {
    std::memcpy(key, g_master_key, 32);
    return true;
  }

  // Fallback: legacy env var (for backward compatibility during migration)
  const char *env = std::getenv("YGB_VAULT_KEY");
  if (env && std::strlen(env) > 0) {
    std::fprintf(stderr, "[VAULT] WARNING: Using legacy YGB_VAULT_KEY env var. "
                         "Migrate to password-derived key.\n");
    if (std::strlen(env) == 64) {
      return hex_to_bytes(env, key, 32);
    }
    sha256((const uint8_t *)env, std::strlen(env), key);
    return true;
  }

  std::fprintf(stderr,
               "[VAULT] FATAL: No master key. Call vault_set_master_key() "
               "or set YGB_VAULT_KEY.\n");
  return false;
}

// =========================================================================
// PHASE 3 — FOLDER PROTECTION
// =========================================================================

static bool check_permissions() {
#ifdef _WIN32
  // On Windows, check that secure_data exists
  // NTFS ACLs handled by Windows — we just ensure directory exists
  return true;
#else
  struct stat st;
  if (stat(VAULT_DIR, &st) != 0) {
    // Directory doesn't exist yet, will create with correct perms
    return true;
  }

  // Check that directory is NOT world-readable
  if (st.st_mode & S_IROTH) {
    std::fprintf(stderr,
                 "[VAULT] FATAL: %s is world-readable! Run: chmod 700 %s\n",
                 VAULT_DIR, VAULT_DIR);
    return false;
  }
  if (st.st_mode & S_IWOTH) {
    std::fprintf(stderr,
                 "[VAULT] FATAL: %s is world-writable! Run: chmod 700 %s\n",
                 VAULT_DIR, VAULT_DIR);
    return false;
  }
  return true;
#endif
}

static bool init_vault_dir() {
  // Check permissions first
  if (!check_permissions()) {
    return false;
  }

#ifdef _WIN32
  std::system("mkdir secure_data 2>nul");
#else
  // Create with 700 permissions
  mkdir(VAULT_DIR, 0700);
#endif
  return true;
}

// =========================================================================
// PHASE 6 — PER-USER DATA ISOLATION
// =========================================================================

static bool validate_user_path(const char *user_id, const char *filename) {
  // user_id must be alphanumeric + underscore
  for (const char *p = user_id; *p; ++p) {
    if (!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
          (*p >= '0' && *p <= '9') || *p == '_'))
      return false;
  }
  // filename must not contain path traversal
  if (std::strstr(filename, "..") || std::strchr(filename, '/') ||
      std::strchr(filename, '\\'))
    return false;
  return true;
}

static bool ensure_user_dir(const char *user_id) {
  char path[512];
  std::snprintf(path, sizeof(path), "%s/%s", VAULT_DIR, user_id);
#ifdef _WIN32
  char cmd[600];
  std::snprintf(cmd, sizeof(cmd), "mkdir \"%s\" 2>nul", path);
  std::system(cmd);
#else
  mkdir(path, 0700);
#endif
  return true;
}

// =========================================================================
// ENCRYPT / DECRYPT (AES-256-GCM)
// =========================================================================

// Encrypt data and write to file: [12 IV][16 TAG][ciphertext]
static VaultResult vault_encrypt_file(const char *user_id, const char *filename,
                                      const uint8_t *plaintext,
                                      size_t plain_len) {
  VaultResult res = {false, 0, ""};

  if (!validate_user_path(user_id, filename)) {
    std::snprintf(res.error, sizeof(res.error), "Invalid user/filename");
    return res;
  }
  if (plain_len > MAX_PLAINTEXT_SIZE) {
    std::snprintf(res.error, sizeof(res.error), "Data too large");
    return res;
  }

  // Load master key
  uint8_t master_key[32];
  if (!load_master_key(master_key)) {
    std::snprintf(res.error, sizeof(res.error), "Master key not available");
    return res;
  }

  // Derive per-user key = SHA256(master_key + user_id)
  uint8_t user_key_input[128];
  std::memcpy(user_key_input, master_key, 32);
  size_t uid_len = std::strlen(user_id);
  std::memcpy(user_key_input + 32, user_id, uid_len);
  uint8_t user_key[32];
  sha256(user_key_input, 32 + uid_len, user_key);

  // Generate random IV
  uint8_t iv[AES_IV_SIZE];
  if (!secure_random(iv, AES_IV_SIZE)) {
    std::snprintf(res.error, sizeof(res.error), "CSPRNG failed");
    return res;
  }

  // Expand key
  AesKey ek;
  aes_key_expand(user_key, ek);

  // Generate H = AES(K, 0^128) for GHASH
  uint8_t h_block[16] = {0};
  aes_encrypt_block(h_block, h_block, ek);

  // Initial counter block J0
  uint8_t j0[16] = {0};
  std::memcpy(j0, iv, AES_IV_SIZE);
  j0[15] = 1;

  // CTR encryption
  uint8_t *ciphertext = new uint8_t[plain_len];
  uint8_t counter[16];
  std::memcpy(counter, j0, 16);

  for (size_t i = 0; i < plain_len; i += 16) {
    // Increment counter
    for (int k = 15; k >= 12; --k) {
      if (++counter[k] != 0)
        break;
    }

    uint8_t keystream[16];
    aes_encrypt_block(counter, keystream, ek);

    size_t block_len = (plain_len - i < 16) ? plain_len - i : 16;
    for (size_t j = 0; j < block_len; ++j)
      ciphertext[i + j] = plaintext[i + j] ^ keystream[j];
  }

  // Compute GHASH for authentication tag
  uint8_t ghash_acc[16] = {0};
  // Process ciphertext blocks
  for (size_t i = 0; i < plain_len; i += 16) {
    uint8_t block[16] = {0};
    size_t bl = (plain_len - i < 16) ? plain_len - i : 16;
    std::memcpy(block, ciphertext + i, bl);
    for (int j = 0; j < 16; ++j)
      ghash_acc[j] ^= block[j];
    ghash_mul(ghash_acc, h_block);
  }
  // Length block
  uint8_t len_block[16] = {0};
  uint64_t ct_bits = (uint64_t)plain_len * 8;
  for (int i = 0; i < 8; ++i)
    len_block[8 + i] = (uint8_t)(ct_bits >> (56 - i * 8));
  for (int j = 0; j < 16; ++j)
    ghash_acc[j] ^= len_block[j];
  ghash_mul(ghash_acc, h_block);

  // Tag = GHASH ^ AES(K, J0)
  uint8_t tag[16];
  aes_encrypt_block(j0, tag, ek);
  for (int i = 0; i < 16; ++i)
    tag[i] ^= ghash_acc[i];

  // Ensure directory exists
  init_vault_dir();
  ensure_user_dir(user_id);

  // Write: [IV 12][TAG 16][ciphertext]
  char path[512];
  std::snprintf(path, sizeof(path), "%s/%s/%s.vault", VAULT_DIR, user_id,
                filename);
  FILE *f = std::fopen(path, "wb");
  if (!f) {
    std::snprintf(res.error, sizeof(res.error), "Cannot write vault file");
    delete[] ciphertext;
    return res;
  }

  std::fwrite(iv, 1, AES_IV_SIZE, f);
  std::fwrite(tag, 1, AES_TAG_SIZE, f);
  std::fwrite(ciphertext, 1, plain_len, f);
  std::fclose(f);

  delete[] ciphertext;
  res.success = true;
  res.output_len = AES_IV_SIZE + AES_TAG_SIZE + plain_len;
  return res;
}

// Decrypt file: read [12 IV][16 TAG][ciphertext], verify tag, return plaintext
static VaultResult vault_decrypt_file(const char *user_id, const char *filename,
                                      uint8_t *output, size_t output_max,
                                      size_t *output_len) {
  VaultResult res = {false, 0, ""};

  if (!validate_user_path(user_id, filename)) {
    std::snprintf(res.error, sizeof(res.error), "Invalid user/filename");
    return res;
  }

  char path[512];
  std::snprintf(path, sizeof(path), "%s/%s/%s.vault", VAULT_DIR, user_id,
                filename);

  FILE *f = std::fopen(path, "rb");
  if (!f) {
    std::snprintf(res.error, sizeof(res.error), "Vault file not found");
    return res;
  }

  // Get file size
  std::fseek(f, 0, SEEK_END);
  long file_size = std::ftell(f);
  std::fseek(f, 0, SEEK_SET);

  if (file_size < AES_IV_SIZE + AES_TAG_SIZE) {
    std::fclose(f);
    std::snprintf(res.error, sizeof(res.error), "Vault file too small");
    return res;
  }

  size_t ct_len = file_size - AES_IV_SIZE - AES_TAG_SIZE;
  if (ct_len > output_max) {
    std::fclose(f);
    std::snprintf(res.error, sizeof(res.error), "Output buffer too small");
    return res;
  }

  uint8_t iv[AES_IV_SIZE], tag[AES_TAG_SIZE];
  std::fread(iv, 1, AES_IV_SIZE, f);
  std::fread(tag, 1, AES_TAG_SIZE, f);
  uint8_t *ciphertext = new uint8_t[ct_len];
  std::fread(ciphertext, 1, ct_len, f);
  std::fclose(f);

  // Load and derive key
  uint8_t master_key[32];
  if (!load_master_key(master_key)) {
    delete[] ciphertext;
    std::snprintf(res.error, sizeof(res.error), "Master key not available");
    return res;
  }

  uint8_t user_key_input[128];
  std::memcpy(user_key_input, master_key, 32);
  size_t uid_len = std::strlen(user_id);
  std::memcpy(user_key_input + 32, user_id, uid_len);
  uint8_t user_key[32];
  sha256(user_key_input, 32 + uid_len, user_key);

  AesKey ek;
  aes_key_expand(user_key, ek);

  // Recompute tag to verify
  uint8_t h_block[16] = {0};
  aes_encrypt_block(h_block, h_block, ek);

  uint8_t j0[16] = {0};
  std::memcpy(j0, iv, AES_IV_SIZE);
  j0[15] = 1;

  uint8_t ghash_acc[16] = {0};
  for (size_t i = 0; i < ct_len; i += 16) {
    uint8_t blk[16] = {0};
    size_t bl = (ct_len - i < 16) ? ct_len - i : 16;
    std::memcpy(blk, ciphertext + i, bl);
    for (int j = 0; j < 16; ++j)
      ghash_acc[j] ^= blk[j];
    ghash_mul(ghash_acc, h_block);
  }
  uint8_t len_block[16] = {0};
  uint64_t ct_bits = (uint64_t)ct_len * 8;
  for (int i = 0; i < 8; ++i)
    len_block[8 + i] = (uint8_t)(ct_bits >> (56 - i * 8));
  for (int j = 0; j < 16; ++j)
    ghash_acc[j] ^= len_block[j];
  ghash_mul(ghash_acc, h_block);

  uint8_t expected_tag[16];
  aes_encrypt_block(j0, expected_tag, ek);
  for (int i = 0; i < 16; ++i)
    expected_tag[i] ^= ghash_acc[i];

  // Constant-time tag comparison
  uint8_t diff = 0;
  for (int i = 0; i < AES_TAG_SIZE; ++i)
    diff |= tag[i] ^ expected_tag[i];
  if (diff != 0) {
    delete[] ciphertext;
    std::snprintf(res.error, sizeof(res.error),
                  "Authentication failed — data tampered");
    return res;
  }

  // Decrypt
  uint8_t counter[16];
  std::memcpy(counter, j0, 16);
  for (size_t i = 0; i < ct_len; i += 16) {
    for (int k = 15; k >= 12; --k) {
      if (++counter[k] != 0)
        break;
    }
    uint8_t keystream[16];
    aes_encrypt_block(counter, keystream, ek);
    size_t bl = (ct_len - i < 16) ? ct_len - i : 16;
    for (size_t j = 0; j < bl; ++j)
      output[i + j] = ciphertext[i + j] ^ keystream[j];
  }

  delete[] ciphertext;
  *output_len = ct_len;
  res.success = true;
  res.output_len = ct_len;
  return res;
}

// =========================================================================
// PUBLIC API
// =========================================================================

static bool vault_init() {
  if (!check_permissions()) {
    std::fprintf(stderr, "[VAULT] Aborting: insecure permissions\n");
    return false;
  }
  return init_vault_dir();
}

// =========================================================================
// SELF-TEST
// =========================================================================

#ifdef VAULT_MAIN
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

  std::printf("secret_vault self-test:\n");

  // Check permission validation
  check(check_permissions(), "Permission check passes");

  // Check directory creation
  check(init_vault_dir(), "Vault dir creation");

  // Check user path validation
  check(validate_user_path("user123", "secrets"), "Valid user path");
  check(!validate_user_path("../evil", "secrets"), "Rejects traversal user");
  check(!validate_user_path("user", "../etc/passwd"), "Rejects traversal file");
  check(validate_user_path("admin_01", "api_keys"), "Underscore OK");

  // SHA-256 test vector
  uint8_t test_hash[32];
  sha256((const uint8_t *)"abc", 3, test_hash);
  char hex[65];
  bytes_to_hex(test_hash, 32, hex);
  check(
      std::strcmp(
          hex,
          "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad") ==
          0,
      "SHA-256 test vector");

  std::printf("\n  Result: %d passed, %d failed\n", pass, fail);
  return fail == 0 ? 0 : 1;
}
#endif

} // namespace secret_vault

#ifdef VAULT_MAIN
int main() { return secret_vault::self_test(); }
#endif
