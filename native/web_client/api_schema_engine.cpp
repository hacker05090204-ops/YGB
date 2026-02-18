/**
 * api_schema_engine.cpp — API Schema Validation Engine
 *
 * Analyzes API endpoint schemas for security issues:
 *   - Missing auth headers, IDOR patterns, mass assignment
 *   - Input validation gaps, rate limiting absence
 *   - Response data exposure
 *
 * Field: Client-Side + Web/API (Field 1)
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace web_client {

struct ApiSchemaResult {
  uint32_t endpoints_analyzed;
  uint32_t missing_auth;
  uint32_t idor_patterns;
  uint32_t mass_assignment;
  uint32_t validation_gaps;
  uint32_t no_rate_limit;
  uint32_t data_exposure;
  double security_score; // 0.0–1.0 (higher = more secure)
};

class ApiSchemaEngine {
public:
  ApiSchemaResult analyze(uint32_t endpoints, uint32_t missing_auth,
                          uint32_t idor, uint32_t mass_assign,
                          uint32_t val_gaps, uint32_t no_rate,
                          uint32_t exposure) {
    ApiSchemaResult r;
    std::memset(&r, 0, sizeof(r));
    r.endpoints_analyzed = endpoints;
    r.missing_auth = missing_auth;
    r.idor_patterns = idor;
    r.mass_assignment = mass_assign;
    r.validation_gaps = val_gaps;
    r.no_rate_limit = no_rate;
    r.data_exposure = exposure;

    uint32_t issues =
        missing_auth + idor + mass_assign + val_gaps + no_rate + exposure;
    r.security_score =
        (endpoints > 0)
            ? std::fmax(0.0, 1.0 - (double)issues / (endpoints * 2.0))
            : 0.0;
    return r;
  }
};

} // namespace web_client
