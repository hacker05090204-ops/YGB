/**
 * secure_secret_loader.cpp — Hardened Secret Loader (Phase 1)
 *
 * Security-critical JWT secret management in C++:
 *   - Loads JWT_SECRET exclusively from environment variables
 *   - Rejects placeholders and short secrets (< 32 bytes)
 *   - Zeroes memory on destruction (SecureMemory)
 *   - Exposes only sign/verify via C bindings
 *   - Python NEVER accesses the raw secret
 *
 * Build:
 *   g++ -std=c++17 -shared -o secure_secret_loader.dll secure_secret_loader.cpp
 *
 * STRICT RULES:
 *   - No .env file loading
 *   - No fallback secrets
 *   - No mock mode
 *   - Fail-closed on any invalid state
 */

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* ================================================================== */
/*  CONSTANTS                                                         */
/* ================================================================== */

static constexpr int MIN_SECRET_LEN = 32;
static constexpr int MAX_SECRET_LEN = 512;
static constexpr int HMAC_SHA256_LEN = 32;
static constexpr int SHA256_BLOCK_SIZE = 64;

/* Known placeholder secrets that MUST be rejected */
static const char *PLACEHOLDER_SECRETS[] = {
    "changeme",
    "secret",
    "password",
    "jwt_secret",
    "your-secret-here",
    "your_secret_here",
    "replace-me",
    "replace_me",
    "test",
    "dev",
    "development",
    "default",
    "mysecret",
    "my_secret",
    "super_secret",
    "supersecret",
    "",
    nullptr /* sentinel */
};

/* ================================================================== */
/*  SECURE MEMORY                                                     */
/* ================================================================== */

static uint8_t g_secret[MAX_SECRET_LEN];
static int g_secret_len = 0;
static int g_initialized = 0;

static void secure_zero(void *ptr, size_t len) {
  volatile uint8_t *p = (volatile uint8_t *)ptr;
  for (size_t i = 0; i < len; i++) {
    p[i] = 0;
  }
}

/* ================================================================== */
/*  SHA-256 (portable, no dependencies)                               */
/* ================================================================== */

static const uint32_t SHA256_K[64] = {
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
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
};

static inline uint32_t rotr32(uint32_t x, int n) {
  return (x >> n) | (x << (32 - n));
}

typedef struct {
  uint32_t state[8];
  uint8_t buf[64];
  uint64_t total;
} Sha256Ctx;

static void sha256_init(Sha256Ctx *ctx) {
  ctx->state[0] = 0x6a09e667;
  ctx->state[1] = 0xbb67ae85;
  ctx->state[2] = 0x3c6ef372;
  ctx->state[3] = 0xa54ff53a;
  ctx->state[4] = 0x510e527f;
  ctx->state[5] = 0x9b05688c;
  ctx->state[6] = 0x1f83d9ab;
  ctx->state[7] = 0x5be0cd19;
  ctx->total = 0;
  std::memset(ctx->buf, 0, 64);
}

static void sha256_transform(Sha256Ctx *ctx, const uint8_t blk[64]) {
  uint32_t w[64];
  for (int i = 0; i < 16; i++) {
    w[i] = ((uint32_t)blk[i * 4] << 24) | ((uint32_t)blk[i * 4 + 1] << 16) |
           ((uint32_t)blk[i * 4 + 2] << 8) | (uint32_t)blk[i * 4 + 3];
  }
  for (int i = 16; i < 64; i++) {
    uint32_t s0 =
        rotr32(w[i - 15], 7) ^ rotr32(w[i - 15], 18) ^ (w[i - 15] >> 3);
    uint32_t s1 =
        rotr32(w[i - 2], 17) ^ rotr32(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  uint32_t a = ctx->state[0], b = ctx->state[1], c = ctx->state[2],
           d = ctx->state[3];
  uint32_t e = ctx->state[4], f = ctx->state[5], g = ctx->state[6],
           h = ctx->state[7];
  for (int i = 0; i < 64; i++) {
    uint32_t S1 = rotr32(e, 6) ^ rotr32(e, 11) ^ rotr32(e, 25);
    uint32_t ch = (e & f) ^ (~e & g);
    uint32_t t1 = h + S1 + ch + SHA256_K[i] + w[i];
    uint32_t S0 = rotr32(a, 2) ^ rotr32(a, 13) ^ rotr32(a, 22);
    uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
    uint32_t t2 = S0 + maj;
    h = g;
    g = f;
    f = e;
    e = d + t1;
    d = c;
    c = b;
    b = a;
    a = t1 + t2;
  }
  ctx->state[0] += a;
  ctx->state[1] += b;
  ctx->state[2] += c;
  ctx->state[3] += d;
  ctx->state[4] += e;
  ctx->state[5] += f;
  ctx->state[6] += g;
  ctx->state[7] += h;
}

static void sha256_update(Sha256Ctx *ctx, const uint8_t *data, size_t len) {
  for (size_t i = 0; i < len; i++) {
    ctx->buf[ctx->total % 64] = data[i];
    ctx->total++;
    if (ctx->total % 64 == 0)
      sha256_transform(ctx, ctx->buf);
  }
}

static void sha256_final(Sha256Ctx *ctx, uint8_t out[32]) {
  uint64_t bits = ctx->total * 8;
  uint8_t pad = 0x80;
  sha256_update(ctx, &pad, 1);
  pad = 0;
  while (ctx->total % 64 != 56)
    sha256_update(ctx, &pad, 1);
  for (int i = 7; i >= 0; i--) {
    uint8_t b = (uint8_t)(bits >> (i * 8));
    sha256_update(ctx, &b, 1);
  }
  for (int i = 0; i < 8; i++) {
    out[i * 4 + 0] = (uint8_t)(ctx->state[i] >> 24);
    out[i * 4 + 1] = (uint8_t)(ctx->state[i] >> 16);
    out[i * 4 + 2] = (uint8_t)(ctx->state[i] >> 8);
    out[i * 4 + 3] = (uint8_t)(ctx->state[i]);
  }
}

static void sha256(const uint8_t *data, size_t len, uint8_t out[32]) {
  Sha256Ctx ctx;
  sha256_init(&ctx);
  sha256_update(&ctx, data, len);
  sha256_final(&ctx, out);
}

/* ================================================================== */
/*  HMAC-SHA256                                                       */
/* ================================================================== */

static void hmac_sha256(const uint8_t *key, int key_len, const uint8_t *msg,
                        int msg_len, uint8_t out[32]) {
  uint8_t k_pad[SHA256_BLOCK_SIZE];
  uint8_t ipad[SHA256_BLOCK_SIZE];
  uint8_t opad[SHA256_BLOCK_SIZE];

  /* If key longer than block size, hash it first */
  uint8_t key_hash[32];
  if (key_len > SHA256_BLOCK_SIZE) {
    sha256(key, key_len, key_hash);
    key = key_hash;
    key_len = 32;
  }

  std::memset(k_pad, 0, SHA256_BLOCK_SIZE);
  std::memcpy(k_pad, key, key_len);

  for (int i = 0; i < SHA256_BLOCK_SIZE; i++) {
    ipad[i] = k_pad[i] ^ 0x36;
    opad[i] = k_pad[i] ^ 0x5c;
  }

  /* inner hash: SHA256(ipad || msg) */
  Sha256Ctx ctx;
  sha256_init(&ctx);
  sha256_update(&ctx, ipad, SHA256_BLOCK_SIZE);
  sha256_update(&ctx, msg, msg_len);
  uint8_t inner[32];
  sha256_final(&ctx, inner);

  /* outer hash: SHA256(opad || inner) */
  sha256_init(&ctx);
  sha256_update(&ctx, opad, SHA256_BLOCK_SIZE);
  sha256_update(&ctx, inner, 32);
  sha256_final(&ctx, out);

  /* Zero sensitive intermediates */
  secure_zero(k_pad, sizeof(k_pad));
  secure_zero(ipad, sizeof(ipad));
  secure_zero(opad, sizeof(opad));
  secure_zero(inner, sizeof(inner));
  secure_zero(key_hash, sizeof(key_hash));
}

/* ================================================================== */
/*  HEX ENCODING                                                      */
/* ================================================================== */

static void bytes_to_hex(const uint8_t *data, int len, char *out) {
  static const char hex[] = "0123456789abcdef";
  for (int i = 0; i < len; i++) {
    out[i * 2] = hex[data[i] >> 4];
    out[i * 2 + 1] = hex[data[i] & 0x0f];
  }
  out[len * 2] = '\0';
}

/* ================================================================== */
/*  PLACEHOLDER DETECTION                                             */
/* ================================================================== */

static int is_placeholder(const char *secret, int len) {
  /* Empty */
  if (len == 0)
    return 1;

  /* Too short */
  if (len < MIN_SECRET_LEN)
    return 1;

  /* Check against known placeholders */
  for (int i = 0; PLACEHOLDER_SECRETS[i] != nullptr; i++) {
    if (std::strcmp(secret, PLACEHOLDER_SECRETS[i]) == 0)
      return 1;
  }

  /* Check for low entropy: all same char */
  int all_same = 1;
  for (int i = 1; i < len; i++) {
    if (secret[i] != secret[0]) {
      all_same = 0;
      break;
    }
  }
  if (all_same)
    return 1;

  /* Check for sequential ASCII */
  int sequential = 1;
  for (int i = 1; i < len && i < 32; i++) {
    if (secret[i] != secret[i - 1] + 1) {
      sequential = 0;
      break;
    }
  }
  if (sequential && len >= 8)
    return 1;

  return 0;
}

/* ================================================================== */
/*  CONSTANT-TIME COMPARISON                                          */
/* ================================================================== */

static int constant_time_compare(const uint8_t *a, const uint8_t *b, int len) {
  volatile uint8_t diff = 0;
  for (int i = 0; i < len; i++) {
    diff |= a[i] ^ b[i];
  }
  return diff == 0;
}

/* ================================================================== */
/*  PUBLIC API                                                        */
/* ================================================================== */

/**
 * Initialize the secret loader.
 * Loads JWT_SECRET from environment variable ONLY.
 * Returns: 1 on success, 0 on failure (fail-closed).
 */
EXPORT int secret_init(void) {
  if (g_initialized)
    return 1;

  const char *env_secret = std::getenv("JWT_SECRET");
  if (!env_secret) {
    std::fprintf(stderr, "[SECURE_SECRET_LOADER] FATAL: JWT_SECRET environment "
                         "variable not set.\n"
                         "[SECURE_SECRET_LOADER] Set it via: export "
                         "JWT_SECRET=<your-32+byte-secret>\n"
                         "[SECURE_SECRET_LOADER] .env files are NOT supported "
                         "for security reasons.\n");
    return 0;
  }

  int len = (int)std::strlen(env_secret);

  if (is_placeholder(env_secret, len)) {
    std::fprintf(stderr,
                 "[SECURE_SECRET_LOADER] FATAL: JWT_SECRET is a placeholder or "
                 "too short.\n"
                 "[SECURE_SECRET_LOADER] Minimum length: %d bytes.\n"
                 "[SECURE_SECRET_LOADER] Do NOT use: 'changeme', 'secret', "
                 "'password', etc.\n",
                 MIN_SECRET_LEN);
    return 0;
  }

  if (len > MAX_SECRET_LEN) {
    std::fprintf(
        stderr,
        "[SECURE_SECRET_LOADER] FATAL: JWT_SECRET too long (%d > %d).\n", len,
        MAX_SECRET_LEN);
    return 0;
  }

  std::memcpy(g_secret, env_secret, len);
  g_secret_len = len;
  g_initialized = 1;

  std::fprintf(
      stderr,
      "[SECURE_SECRET_LOADER] Secret loaded from environment (%d bytes).\n",
      len);
  return 1;
}

/**
 * Sign a message with HMAC-SHA256 using the loaded secret.
 * Returns: 1 on success, 0 on failure.
 * out_hex must be at least 65 bytes (64 hex chars + null).
 */
EXPORT int secret_sign_hmac(const char *message, int msg_len, char *out_hex,
                            int out_hex_len) {
  if (!g_initialized) {
    std::fprintf(stderr, "[SECURE_SECRET_LOADER] FATAL: secret_sign_hmac "
                         "called before secret_init.\n");
    return 0;
  }
  if (!message || msg_len <= 0)
    return 0;
  if (!out_hex || out_hex_len < 65)
    return 0;

  uint8_t mac[32];
  hmac_sha256(g_secret, g_secret_len, (const uint8_t *)message, msg_len, mac);
  bytes_to_hex(mac, 32, out_hex);
  secure_zero(mac, sizeof(mac));
  return 1;
}

/**
 * Verify an HMAC-SHA256 signature.
 * Returns: 1 if valid, 0 if invalid.
 * Uses constant-time comparison.
 */
EXPORT int secret_verify_hmac(const char *message, int msg_len,
                              const char *expected_hex) {
  if (!g_initialized) {
    std::fprintf(stderr, "[SECURE_SECRET_LOADER] FATAL: secret_verify_hmac "
                         "called before secret_init.\n");
    return 0;
  }
  if (!message || msg_len <= 0)
    return 0;
  if (!expected_hex || std::strlen(expected_hex) != 64)
    return 0;

  char computed_hex[65];
  uint8_t mac[32];
  hmac_sha256(g_secret, g_secret_len, (const uint8_t *)message, msg_len, mac);
  bytes_to_hex(mac, 32, computed_hex);
  secure_zero(mac, sizeof(mac));

  int result = constant_time_compare((const uint8_t *)computed_hex,
                                     (const uint8_t *)expected_hex, 64);
  secure_zero(computed_hex, sizeof(computed_hex));
  return result;
}

/**
 * Destroy the loaded secret — zeroes all memory.
 */
EXPORT void secret_destroy(void) {
  secure_zero(g_secret, sizeof(g_secret));
  g_secret_len = 0;
  g_initialized = 0;
}

/**
 * Check if secret loader is initialized.
 */
EXPORT int secret_is_initialized(void) { return g_initialized; }

/**
 * Get the minimum required secret length.
 */
EXPORT int secret_min_length(void) { return MIN_SECRET_LEN; }

#ifdef __cplusplus
}
#endif
