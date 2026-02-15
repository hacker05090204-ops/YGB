/**
 * HTTP Variance Engine for MODE-A Representation Expansion.
 *
 * Generates diverse HTTP request/response representation patterns
 * for representation-only learning. Target: 30% protocol diversity increase.
 *
 * GOVERNANCE:
 *   - NO decision labels
 *   - NO severity fields
 *   - NO exploit content
 *   - Deterministic seeded generation
 *   - Append-only sanitized JSONL
 *   - FNV-1a deduplication
 *
 * Compile: cl /O2 /EHsc /std:c++17 http_variance_engine.cpp
 */
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <random>
#include <string>
#include <unordered_set>
#include <vector>


namespace g38 {
namespace repr {

// ============================================================================
// FNV-1a 64-bit hash
// ============================================================================

static constexpr uint64_t FNV_OFFSET = 14695981039346656037ULL;
static constexpr uint64_t FNV_PRIME = 1099511628211ULL;

inline uint64_t fnv1a_hash(const float *data, int n) {
  uint64_t h = FNV_OFFSET;
  const auto *bytes = reinterpret_cast<const uint8_t *>(data);
  int nbytes = n * sizeof(float);
  for (int i = 0; i < nbytes; ++i) {
    h ^= bytes[i];
    h *= FNV_PRIME;
  }
  return h;
}

// ============================================================================
// FORBIDDEN FIELDS — stripped during sanitization
// ============================================================================

static const std::array<std::string, 6> FORBIDDEN_FIELDS = {
    "valid", "accepted", "rejected", "severity", "impact", "cve_score"};

// ============================================================================
// HTTP Method / Status / Content-Type templates
// ============================================================================

static const std::array<std::string, 15> HTTP_METHODS = {
    "GET",   "POST",    "PUT",   "DELETE",  "PATCH",
    "HEAD",  "OPTIONS", "TRACE", "CONNECT", "PROPFIND",
    "MKCOL", "COPY",    "MOVE",  "LOCK",    "UNLOCK"};

static const std::array<int, 20> HTTP_STATUS_CODES = {
    200, 201, 204, 301, 302, 304, 400, 401, 403, 404,
    405, 408, 409, 413, 415, 422, 429, 500, 502, 503};

static const std::array<std::string, 12> CONTENT_TYPES = {
    "application/json",
    "application/xml",
    "text/html",
    "text/plain",
    "multipart/form-data",
    "application/x-www-form-urlencoded",
    "application/octet-stream",
    "application/graphql",
    "application/jwt",
    "text/csv",
    "application/yaml",
    "application/cbor"};

static const std::array<std::string, 8> AUTH_HEADERS = {
    "Bearer", "Basic",       "Digest", "OAuth",
    "ApiKey", "HMAC-SHA256", "JWT",    "SAML"};

static const std::array<std::string, 6> ENCODINGS = {
    "gzip", "deflate", "br", "identity", "compress", "zstd"};

// ============================================================================
// HTTP Representation Vector (32 dims — maps to signal[0:32])
// ============================================================================

struct HttpRepresentation {
  float method_id;         // [0] Method index normalized
  float status_family;     // [1] Status family (1xx=0.1, 2xx=0.2, ...)
  float status_specific;   // [2] Specific status normalized
  float content_type_id;   // [3] Content-Type index normalized
  float auth_scheme_id;    // [4] Auth scheme index normalized
  float encoding_id;       // [5] Encoding index normalized
  float has_body;          // [6] Request has body
  float body_size_log;     // [7] log(body_size) normalized
  float header_count;      // [8] Number of headers normalized
  float cookie_count;      // [9] Number of cookies normalized
  float query_param_count; // [10] Query param count normalized
  float path_depth;        // [11] URL path depth normalized
  float has_auth;          // [12] Has authorization header
  float has_csrf;          // [13] Has CSRF token
  float has_cors;          // [14] Has CORS headers
  float is_websocket;      // [15] WebSocket upgrade
  float response_time;     // [16] Response time normalized
  float redirect_count;    // [17] Number of redirects
  float has_cache;         // [18] Has cache headers
  float has_etag;          // [19] Has ETag
  float tls_version;       // [20] TLS version normalized
  float http_version; // [21] HTTP version (1.0=0.1, 1.1=0.5, 2.0=0.8, 3.0=1.0)
  float content_length;      // [22] Content-Length normalized
  float vary_header_count;   // [23] Vary header count
  float accept_types;        // [24] Number of Accept types
  float is_preflight;        // [25] Is CORS preflight
  float has_rate_limit;      // [26] Has rate limit headers
  float retry_after;         // [27] Retry-After value normalized
  float connection_type;     // [28] Connection: keep-alive=1, close=0
  float has_www_auth;        // [29] Has WWW-Authenticate
  float security_headers;    // [30] Count of security headers normalized
  float custom_header_count; // [31] Count of custom headers
};

// ============================================================================
// HTTP Variance Engine
// ============================================================================

class HttpVarianceEngine {
public:
  explicit HttpVarianceEngine(uint64_t seed = 42) : rng_(seed), seed_(seed) {}

  /**
   * Generate a batch of diverse HTTP representation vectors.
   * Output: batch_size x 32 floats
   * All output is sanitized — no forbidden fields.
   */
  void generate_batch(float *output, int batch_size, int dim = 32) {
    std::uniform_real_distribution<float> uniform(0.0f, 1.0f);
    std::uniform_int_distribution<int> method_dist(0, HTTP_METHODS.size() - 1);
    std::uniform_int_distribution<int> status_dist(0, HTTP_STATUS_CODES.size() -
                                                          1);
    std::uniform_int_distribution<int> ctype_dist(0, CONTENT_TYPES.size() - 1);
    std::uniform_int_distribution<int> auth_dist(0, AUTH_HEADERS.size() - 1);
    std::uniform_int_distribution<int> enc_dist(0, ENCODINGS.size() - 1);

    for (int b = 0; b < batch_size; ++b) {
      float *row = output + b * dim;

      int method = method_dist(rng_);
      int status_idx = status_dist(rng_);
      int status = HTTP_STATUS_CODES[status_idx];
      int ctype = ctype_dist(rng_);
      int auth = auth_dist(rng_);
      int enc = enc_dist(rng_);

      row[0] = static_cast<float>(method) / 14.0f;
      row[1] = static_cast<float>(status / 100) / 5.0f;
      row[2] = static_cast<float>(status_idx) / 19.0f;
      row[3] = static_cast<float>(ctype) / 11.0f;
      row[4] = static_cast<float>(auth) / 7.0f;
      row[5] = static_cast<float>(enc) / 5.0f;
      row[6] = (method >= 1 && method <= 3) ? 1.0f : uniform(rng_);
      row[7] =
          std::min(1.0f, std::log2(1.0f + uniform(rng_) * 10000.0f) / 14.0f);
      row[8] = std::min(1.0f, (3.0f + uniform(rng_) * 20.0f) / 25.0f);
      row[9] = std::min(1.0f, uniform(rng_) * 5.0f / 5.0f);
      row[10] = std::min(1.0f, uniform(rng_) * 8.0f / 10.0f);
      row[11] = std::min(1.0f, (1.0f + uniform(rng_) * 7.0f) / 8.0f);
      row[12] = (uniform(rng_) > 0.3f) ? 1.0f : 0.0f;
      row[13] = (uniform(rng_) > 0.6f) ? 1.0f : 0.0f;
      row[14] = (uniform(rng_) > 0.5f) ? 1.0f : 0.0f;
      row[15] = (uniform(rng_) > 0.95f) ? 1.0f : 0.0f;
      row[16] = std::min(1.0f, uniform(rng_) * 2.0f);
      row[17] = std::min(1.0f, uniform(rng_) * 3.0f / 5.0f);
      row[18] = (uniform(rng_) > 0.4f) ? 1.0f : 0.0f;
      row[19] = (uniform(rng_) > 0.5f) ? 1.0f : 0.0f;
      row[20] =
          uniform(rng_) > 0.8f ? 1.0f : (uniform(rng_) > 0.3f ? 0.75f : 0.5f);
      row[21] =
          uniform(rng_) > 0.7f ? 0.8f : (uniform(rng_) > 0.4f ? 0.5f : 0.1f);
      row[22] =
          std::min(1.0f, std::log2(1.0f + uniform(rng_) * 50000.0f) / 16.0f);
      row[23] = std::min(1.0f, uniform(rng_) * 4.0f / 5.0f);
      row[24] = std::min(1.0f, (1.0f + uniform(rng_) * 5.0f) / 6.0f);
      row[25] = (uniform(rng_) > 0.9f) ? 1.0f : 0.0f;
      row[26] = (uniform(rng_) > 0.6f) ? 1.0f : 0.0f;
      row[27] = uniform(rng_) * 0.5f;
      row[28] = (uniform(rng_) > 0.3f) ? 1.0f : 0.0f;
      row[29] = (status == 401) ? 1.0f : 0.0f;
      row[30] = std::min(1.0f, uniform(rng_) * 6.0f / 8.0f);
      row[31] = std::min(1.0f, uniform(rng_) * 10.0f / 15.0f);
    }
  }

  /**
   * Deduplicate batch using FNV-1a hashing.
   * Returns number of unique samples.
   */
  int deduplicate(float *data, int batch_size, int dim,
                  std::unordered_set<uint64_t> &seen) {
    int write = 0;
    for (int r = 0; r < batch_size; ++r) {
      uint64_t h = fnv1a_hash(data + r * dim, dim);
      if (seen.find(h) == seen.end()) {
        seen.insert(h);
        if (write != r) {
          std::copy(data + r * dim, data + r * dim + dim, data + write * dim);
        }
        write++;
      }
    }
    return write;
  }

  /**
   * Get protocol diversity metric: unique method/status combinations.
   */
  float compute_diversity(const float *data, int batch_size, int dim) {
    std::unordered_set<uint64_t> combos;
    for (int b = 0; b < batch_size; ++b) {
      const float *row = data + b * dim;
      // Hash method + status + content_type + auth
      uint64_t key = static_cast<uint64_t>(row[0] * 100) * 1000000 +
                     static_cast<uint64_t>(row[2] * 100) * 10000 +
                     static_cast<uint64_t>(row[3] * 100) * 100 +
                     static_cast<uint64_t>(row[4] * 100);
      combos.insert(key);
    }
    // Max possible: 15 methods * 20 statuses * 12 ctypes * 8 auth = 28800
    return static_cast<float>(combos.size()) /
           std::min(static_cast<float>(batch_size), 28800.0f);
  }

private:
  std::mt19937_64 rng_;
  uint64_t seed_;
};

} // namespace repr
} // namespace g38
