/**
 * rate_limit_analyzer.cpp — Rate Limiting Weakness Analysis
 *
 * Detects missing or weak rate limiting:
 *   - Authentication endpoints without limits
 *   - API enumeration without throttling
 *   - Batch endpoints without per-item limits
 *   - Inconsistent rate limiting across methods
 *   - Bypass via header manipulation
 *
 * Field 2: API / Business Logic Security
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace api_logic {

struct RateLimitResult {
  uint32_t endpoints_checked;
  uint32_t no_rate_limit;
  uint32_t auth_no_limit;
  uint32_t enum_no_throttle;
  uint32_t batch_no_limit;
  uint32_t inconsistent_methods;
  uint32_t header_bypass;
  double protection_score; // 0.0–1.0 (higher = better)
  bool critical;
};

class RateLimitAnalyzer {
public:
  RateLimitResult analyze(uint32_t endpoints, uint32_t no_limit,
                          uint32_t auth_no, uint32_t enum_no, uint32_t batch_no,
                          uint32_t inconsistent, uint32_t header_bypass) {
    RateLimitResult r;
    std::memset(&r, 0, sizeof(r));

    r.endpoints_checked = endpoints;
    r.no_rate_limit = no_limit;
    r.auth_no_limit = auth_no;
    r.enum_no_throttle = enum_no;
    r.batch_no_limit = batch_no;
    r.inconsistent_methods = inconsistent;
    r.header_bypass = header_bypass;

    uint32_t issues =
        no_limit + auth_no + enum_no + batch_no + inconsistent + header_bypass;
    r.protection_score =
        (endpoints > 0)
            ? std::fmax(0.0, 1.0 - (double)issues / (endpoints * 1.5))
            : 0.0;
    r.critical = (auth_no > 0) || (header_bypass > 0);

    return r;
  }
};

} // namespace api_logic
