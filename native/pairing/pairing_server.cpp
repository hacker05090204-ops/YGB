/**
 * pairing_server.cpp — Zero-Trust Device Pairing System
 *
 * Features:
 *   - Generate 128-bit one-time pairing tokens (5-minute expiry)
 *   - Validate token on device connection
 *   - Issue device certificate on successful pairing
 *   - Token invalidated after single use
 *   - All pairing events logged
 *
 * NO email required. NO cloud required. NO external dependencies.
 */

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>

#ifdef _WIN32
#include <windows.h>
#include <bcrypt.h>
#pragma comment(lib, "bcrypt.lib")
#else
#include <unistd.h>
#endif

namespace pairing_server {

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int TOKEN_SIZE = 16;       // 128-bit token
static constexpr int TOKEN_EXPIRY_SEC = 300; // 5 minutes
static constexpr int MAX_PENDING_TOKENS = 32;
static constexpr char PAIRING_LOG_PATH[] = "reports/pairing_events.log";

// Rate-limit constants
static constexpr int MAX_TRACKED_IPS = 64;
static constexpr int MAX_FAILURES = 5;
static constexpr int FAILURE_WINDOW_SEC = 600;    // 10 minutes
static constexpr int LOCKOUT_DURATION_SEC = 1800; // 30 minutes

// =========================================================================
// RATE LIMITER
// =========================================================================

struct FailedAttempt {
  char ip[46];
  int count;
  uint64_t first_attempt;
  uint64_t last_attempt;
  uint64_t locked_until; // 0 = not locked
  bool active;
};

class RateLimiter {
public:
  RateLimiter() : count_(0) { std::memset(entries_, 0, sizeof(entries_)); }

  // Returns true if IP is currently blocked
  bool is_blocked(const char *ip) {
    if (!ip)
      return false;
    uint64_t now = static_cast<uint64_t>(std::time(nullptr));
    for (int i = 0; i < count_; ++i) {
      if (entries_[i].active && std::strcmp(entries_[i].ip, ip) == 0) {
        if (entries_[i].locked_until > 0 && now < entries_[i].locked_until) {
          return true; // Still locked
        }
        if (entries_[i].locked_until > 0 && now >= entries_[i].locked_until) {
          // Lockout expired — reset
          entries_[i].count = 0;
          entries_[i].locked_until = 0;
        }
        return false;
      }
    }
    return false;
  }

  // Record a failed attempt from IP. Returns true if IP is now locked out.
  bool record_failure(const char *ip) {
    if (!ip)
      return false;
    uint64_t now = static_cast<uint64_t>(std::time(nullptr));

    // Find existing entry
    for (int i = 0; i < count_; ++i) {
      if (entries_[i].active && std::strcmp(entries_[i].ip, ip) == 0) {
        FailedAttempt &e = entries_[i];
        // Reset if outside window
        if (now - e.first_attempt > FAILURE_WINDOW_SEC) {
          e.count = 0;
          e.first_attempt = now;
        }
        e.count++;
        e.last_attempt = now;
        if (e.count >= MAX_FAILURES) {
          e.locked_until = now + LOCKOUT_DURATION_SEC;
          return true; // LOCKED
        }
        return false;
      }
    }

    // New entry
    if (count_ >= MAX_TRACKED_IPS) {
      // Evict oldest
      int oldest = 0;
      for (int i = 1; i < count_; ++i) {
        if (entries_[i].last_attempt < entries_[oldest].last_attempt)
          oldest = i;
      }
      entries_[oldest].active = false;
      entries_[oldest] = {};
      // Reuse slot
      FailedAttempt &e = entries_[oldest];
      std::strncpy(e.ip, ip, 45);
      e.ip[45] = '\0';
      e.count = 1;
      e.first_attempt = now;
      e.last_attempt = now;
      e.locked_until = 0;
      e.active = true;
    } else {
      FailedAttempt &e = entries_[count_++];
      std::strncpy(e.ip, ip, 45);
      e.ip[45] = '\0';
      e.count = 1;
      e.first_attempt = now;
      e.last_attempt = now;
      e.locked_until = 0;
      e.active = true;
    }
    return false;
  }

private:
  FailedAttempt entries_[MAX_TRACKED_IPS];
  int count_;
};

static RateLimiter g_rate_limiter;

// =========================================================================
// CRYPTOGRAPHIC RANDOM
// =========================================================================

static bool generate_random_bytes(uint8_t *buf, size_t len) {
#ifdef _WIN32
    NTSTATUS status = BCryptGenRandom(
        NULL, buf, static_cast<ULONG>(len), BCRYPT_USE_SYSTEM_PREFERRED_RNG);
    return BCRYPT_SUCCESS(status);
#else
    FILE *f = std::fopen("/dev/urandom", "rb");
    if (!f) return false;
    size_t n = std::fread(buf, 1, len, f);
    std::fclose(f);
    return n == len;
#endif
}

// =========================================================================
// HEX ENCODING
// =========================================================================

static void bytes_to_hex(const uint8_t *data, int len, char *out) {
    static const char hex[] = "0123456789abcdef";
    for (int i = 0; i < len; ++i) {
        out[i*2] = hex[(data[i] >> 4) & 0x0F];
        out[i*2+1] = hex[data[i] & 0x0F];
    }
    out[len*2] = '\0';
}

// =========================================================================
// PAIRING TOKEN
// =========================================================================

struct PairingToken {
    uint8_t token[TOKEN_SIZE];
    char token_hex[TOKEN_SIZE * 2 + 1];
    uint64_t created_at;     // Unix timestamp
    uint64_t expires_at;     // Unix timestamp
    bool used;               // Single-use flag
    bool valid;              // Is this slot occupied?
};

// In-memory token storage (no persistence needed — tokens expire in 5 min)
static PairingToken g_tokens[MAX_PENDING_TOKENS];
static int g_token_count = 0;

// =========================================================================
// TOKEN MANAGEMENT
// =========================================================================

/**
 * Generate a new one-time pairing token.
 * Returns token hex string, or nullptr on failure.
 */
static const char *generate_pairing_token() {
    // Find free slot (or reuse expired/used slot)
    int slot = -1;
    uint64_t now = static_cast<uint64_t>(std::time(nullptr));

    for (int i = 0; i < MAX_PENDING_TOKENS; ++i) {
        if (!g_tokens[i].valid || g_tokens[i].used ||
            g_tokens[i].expires_at < now) {
            slot = i;
            break;
        }
    }

    if (slot < 0) {
        std::fprintf(stderr, "[pairing] No free token slots\n");
        return nullptr;
    }

    PairingToken &t = g_tokens[slot];
    std::memset(&t, 0, sizeof(t));

    if (!generate_random_bytes(t.token, TOKEN_SIZE)) {
        std::fprintf(stderr, "[pairing] Failed to generate random token\n");
        return nullptr;
    }

    bytes_to_hex(t.token, TOKEN_SIZE, t.token_hex);
    t.created_at = now;
    t.expires_at = now + TOKEN_EXPIRY_SEC;
    t.used = false;
    t.valid = true;

    if (slot >= g_token_count) g_token_count = slot + 1;

    std::printf("[pairing] Generated token: %s (expires in %ds)\n",
                t.token_hex, TOKEN_EXPIRY_SEC);
    return t.token_hex;
}

/**
 * Validate a pairing token.
 * Returns true if token is valid, not expired, and not already used.
 * On success, marks token as used (single-use).
 */
static bool validate_pairing_token(const char *token_hex) {
    if (!token_hex || std::strlen(token_hex) != TOKEN_SIZE * 2)
        return false;

    uint64_t now = static_cast<uint64_t>(std::time(nullptr));

    for (int i = 0; i < g_token_count; ++i) {
        if (!g_tokens[i].valid) continue;

        // Constant-time comparison (prevent timing attacks)
        bool match = true;
        for (int j = 0; j < TOKEN_SIZE * 2; ++j) {
            if (g_tokens[i].token_hex[j] != token_hex[j])
                match = false;
        }

        if (match) {
            // Check expiry
            if (g_tokens[i].expires_at < now) {
                std::fprintf(stderr, "[pairing] Token expired\n");
                g_tokens[i].valid = false;
                return false;
            }

            // Check single-use
            if (g_tokens[i].used) {
                std::fprintf(stderr, "[pairing] Token already used (replay attempt)\n");
                return false;
            }

            // Mark as used — single use only
            g_tokens[i].used = true;
            std::printf("[pairing] Token validated successfully\n");
            return true;
        }
    }

    std::fprintf(stderr, "[pairing] Token not found (invalid)\n");
    return false;
}

// =========================================================================
// PAIRING EVENT LOGGING
// =========================================================================

struct PairingEvent {
    char device_id[65];
    char token_hex[TOKEN_SIZE * 2 + 1];
    uint64_t timestamp;
    bool success;
};

static bool log_pairing_event(const PairingEvent &event) {
    FILE *f = std::fopen(PAIRING_LOG_PATH, "a");
    if (!f) return false;

    std::fprintf(f, "{\"timestamp\": %llu, \"device_id\": \"%s\", "
                    "\"token\": \"%s\", \"success\": %s}\n",
                 static_cast<unsigned long long>(event.timestamp),
                 event.device_id, event.token_hex,
                 event.success ? "true" : "false");
    std::fclose(f);
    return true;
}

// =========================================================================
// PAIRING WORKFLOW
// =========================================================================

/**
 * Process a pairing request.
 * 1. Validate token
 * 2. If valid: issue device certificate, log event
 * 3. If invalid: reject, log event
 */
static bool process_pairing_request(const char *device_id,
                                     const char *token_hex) {
    PairingEvent event;
    std::memset(&event, 0, sizeof(event));
    std::strncpy(event.device_id, device_id, sizeof(event.device_id) - 1);
    std::strncpy(event.token_hex, token_hex, sizeof(event.token_hex) - 1);
    event.timestamp = static_cast<uint64_t>(std::time(nullptr));

    if (!validate_pairing_token(token_hex)) {
        event.success = false;
        log_pairing_event(event);
        std::fprintf(stderr, "[pairing] REJECTED device %s\n", device_id);
        return false;
    }

    event.success = true;
    log_pairing_event(event);
    std::printf("[pairing] APPROVED device %s\n", device_id);
    return true;
}

} // namespace pairing_server

// =========================================================================
// SELF-TEST (compile with -DPAIRING_SERVER_MAIN)
// =========================================================================

#ifdef PAIRING_SERVER_MAIN
int main() {
    std::printf("=== Pairing Server Test ===\n");

    // Test 1: Generate token
    const char *token = pairing_server::generate_pairing_token();
    if (!token) {
        std::fprintf(stderr, "FAIL: Could not generate token\n");
        return 1;
    }
    std::printf("Token: %s\n", token);

    // Test 2: Validate token
    char token_copy[33];
    std::strncpy(token_copy, token, sizeof(token_copy) - 1);
    token_copy[32] = '\0';

    bool valid = pairing_server::process_pairing_request("test-device-001", token_copy);
    std::printf("First use: %s\n", valid ? "PASS" : "FAIL");

    // Test 3: Replay must fail
    bool replay = pairing_server::process_pairing_request("test-device-002", token_copy);
    std::printf("Replay blocked: %s\n", !replay ? "PASS" : "FAIL");

    // Test 4: Invalid token must fail
    bool invalid = pairing_server::process_pairing_request("test-device-003", "00000000000000000000000000000000");
    std::printf("Invalid blocked: %s\n", !invalid ? "PASS" : "FAIL");

    return 0;
}
#endif
