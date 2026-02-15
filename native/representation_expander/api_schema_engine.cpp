/**
 * API Schema Engine for MODE-A Representation Expansion.
 *
 * Generates diverse API schema representation patterns
 * for representation-only learning. Target: 20% nesting depth variance
 * increase.
 *
 * GOVERNANCE:
 *   - NO decision labels
 *   - NO severity/exploit fields
 *   - Deterministic seeded generation
 *   - FNV-1a deduplication
 *
 * Compile: cl /O2 /EHsc /std:c++17 api_schema_engine.cpp
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
// API Schema Templates
// ============================================================================

static const std::array<std::string, 8> ENDPOINT_PATTERNS = {
    "/api/v{n}/{resource}",
    "/api/{resource}/{id}",
    "/api/v{n}/{resource}/{id}/{sub}",
    "/graphql",
    "/api/{resource}/{id}/{sub}/{action}",
    "/rest/{namespace}/{resource}",
    "/api/v{n}/{resource}/{id}/relationships/{rel}",
    "/api/{resource}/{id}/{sub}/{subid}/{action}"};

static const std::array<std::string, 8> PARAM_TYPES = {
    "query", "path", "body", "header", "cookie", "form", "matrix", "fragment"};

static const std::array<std::string, 10> RESPONSE_TYPES = {
    "object",   "array", "paginated",        "envelope",     "hal+json",
    "json-api", "odata", "graphql-response", "error-object", "polymorphic"};

static const std::array<std::string, 6> AUTH_PATTERNS = {
    "none",        "api-key",         "bearer",
    "oauth2-code", "oauth2-implicit", "mutual-tls"};

// ============================================================================
// API Representation Vector (32 dims — maps to response[0:32])
// ============================================================================

struct ApiRepresentation {
  float path_depth;            // [0] URL path segment count (1-8)
  float path_segment_count;    // [1] Total path segments
  float query_param_count;     // [2] Number of query parameters
  float body_param_count;      // [3] Number of body parameters
  float header_param_count;    // [4] Number of header parameters
  float param_type_diversity;  // [5] Unique param types / total
  float response_nesting;      // [6] Response JSON nesting depth (1-10)
  float response_field_count;  // [7] Fields in response schema
  float response_array_depth;  // [8] Array nesting depth in response
  float response_type;         // [9] Response envelope type
  float has_pagination;        // [10] Supports pagination
  float pagination_style;      // [11] offset vs cursor vs page
  float has_filtering;         // [12] Supports query filtering
  float filter_complexity;     // [13] Filter expression complexity
  float has_sorting;           // [14] Supports sorting
  float has_projection;        // [15] Supports field projection
  float is_graphql;            // [16] GraphQL endpoint
  float graphql_depth;         // [17] GraphQL query nesting
  float graphql_fragments;     // [18] Uses fragments
  float mutation_count;        // [19] Number of mutations
  float subscription_support;  // [20] Supports subscriptions
  float versioning_style;      // [21] URL vs header vs media-type
  float rate_limit_type;       // [22] fixed vs sliding vs token-bucket
  float auth_complexity;       // [23] Auth pattern complexity
  float has_webhooks;          // [24] Supports webhooks
  float webhook_event_count;   // [25] Number of webhook events
  float error_schema_depth;    // [26] Error response nesting
  float has_batch_endpoint;    // [27] Supports batch operations
  float idempotency_support;   // [28] Supports idempotency keys
  float has_hateoas;           // [29] HATEOAS links present
  float polymorphic_responses; // [30] Uses discriminator patterns
  float schema_complexity;     // [31] Overall schema complexity score
};

// ============================================================================
// API Schema Engine
// ============================================================================

class ApiSchemaEngine {
public:
  explicit ApiSchemaEngine(uint64_t seed = 42) : rng_(seed), seed_(seed) {}

  /**
   * Generate a batch of diverse API schema representation vectors.
   * Output: batch_size x 32 floats
   */
  void generate_batch(float *output, int batch_size, int dim = 32) {
    std::uniform_real_distribution<float> uniform(0.0f, 1.0f);
    std::uniform_int_distribution<int> depth_dist(1, 8);
    std::uniform_int_distribution<int> nesting_dist(1, 10);
    std::uniform_int_distribution<int> rtype_dist(0, RESPONSE_TYPES.size() - 1);
    std::uniform_int_distribution<int> auth_dist(0, AUTH_PATTERNS.size() - 1);

    for (int b = 0; b < batch_size; ++b) {
      float *row = output + b * dim;

      int depth = depth_dist(rng_);
      int nesting = nesting_dist(rng_);
      bool is_gql = uniform(rng_) > 0.75f;

      row[0] = static_cast<float>(depth) / 8.0f;
      row[1] = std::min(1.0f, (depth + uniform(rng_) * 3.0f) / 12.0f);
      row[2] = std::min(1.0f, uniform(rng_) * 8.0f / 10.0f);
      row[3] = std::min(1.0f, uniform(rng_) * 15.0f / 20.0f);
      row[4] = std::min(1.0f, uniform(rng_) * 5.0f / 8.0f);
      row[5] = std::min(1.0f, (1.0f + uniform(rng_) * 5.0f) /
                                  static_cast<float>(PARAM_TYPES.size()));
      row[6] = static_cast<float>(nesting) / 10.0f;
      row[7] = std::min(1.0f, std::log2(1.0f + uniform(rng_) * 100.0f) / 7.0f);
      row[8] = std::min(1.0f, uniform(rng_) * 4.0f / 5.0f);
      row[9] = static_cast<float>(rtype_dist(rng_)) /
               static_cast<float>(RESPONSE_TYPES.size() - 1);
      row[10] = (uniform(rng_) > 0.4f) ? 1.0f : 0.0f;
      row[11] = uniform(rng_); // pagination style
      row[12] = (uniform(rng_) > 0.3f) ? 1.0f : 0.0f;
      row[13] = uniform(rng_) * 0.8f;
      row[14] = (uniform(rng_) > 0.4f) ? 1.0f : 0.0f;
      row[15] = (uniform(rng_) > 0.5f) ? 1.0f : 0.0f;
      row[16] = is_gql ? 1.0f : 0.0f;
      row[17] = is_gql ? std::min(1.0f, uniform(rng_) * 6.0f / 8.0f) : 0.0f;
      row[18] = is_gql ? (uniform(rng_) > 0.5f ? 1.0f : 0.0f) : 0.0f;
      row[19] = is_gql ? std::min(1.0f, uniform(rng_) * 10.0f / 12.0f) : 0.0f;
      row[20] = is_gql ? (uniform(rng_) > 0.6f ? 1.0f : 0.0f) : 0.0f;
      row[21] = uniform(rng_); // versioning style
      row[22] = uniform(rng_); // rate limit type
      row[23] = static_cast<float>(auth_dist(rng_)) /
                static_cast<float>(AUTH_PATTERNS.size() - 1);
      row[24] = (uniform(rng_) > 0.7f) ? 1.0f : 0.0f;
      row[25] = std::min(1.0f, uniform(rng_) * 8.0f / 10.0f);
      row[26] = std::min(1.0f, uniform(rng_) * 4.0f / 5.0f);
      row[27] = (uniform(rng_) > 0.8f) ? 1.0f : 0.0f;
      row[28] = (uniform(rng_) > 0.6f) ? 1.0f : 0.0f;
      row[29] = (uniform(rng_) > 0.7f) ? 1.0f : 0.0f;
      row[30] = (uniform(rng_) > 0.75f) ? 1.0f : 0.0f;
      // Complexity score
      row[31] =
          std::min(1.0f, (row[0] * 0.2f + row[6] * 0.25f + row[8] * 0.15f +
                          row[13] * 0.1f + row[17] * 0.15f + row[26] * 0.15f));
    }
  }

  /**
   * Compute API schema diversity metric.
   */
  float compute_nesting_variance(const float *data, int batch_size, int dim) {
    float mean = 0.0f;
    for (int b = 0; b < batch_size; ++b) {
      mean += data[b * dim + 6]; // response_nesting
    }
    mean /= batch_size;

    float var = 0.0f;
    for (int b = 0; b < batch_size; ++b) {
      float diff = data[b * dim + 6] - mean;
      var += diff * diff;
    }
    return var / batch_size;
  }

private:
  std::mt19937_64 rng_;
  uint64_t seed_;
};

} // namespace repr
} // namespace g38
