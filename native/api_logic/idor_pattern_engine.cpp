/**
 * idor_pattern_engine.cpp — IDOR Pattern Detection
 *
 * Detects Insecure Direct Object Reference patterns:
 *   - Sequential/predictable IDs in URLs and parameters
 *   - Missing authorization checks on object access
 *   - User-controlled references to other users' objects
 *   - Horizontal privilege escalation via object ID manipulation
 *
 * Field 2: API / Business Logic Security
 * NO company-specific targeting.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace api_logic {

struct IdorResult {
  uint32_t endpoints_checked;
  uint32_t sequential_ids;
  uint32_t predictable_patterns;
  uint32_t missing_authz;
  uint32_t user_ref_exposure;
  uint32_t horizontal_escalation;
  double idor_risk; // 0.0–1.0
  bool critical;
};

class IdorPatternEngine {
public:
  static constexpr bool ALLOW_COMPANY_TARGETING = false;

  IdorResult analyze(uint32_t endpoints, uint32_t sequential,
                     uint32_t predictable, uint32_t no_authz, uint32_t user_ref,
                     uint32_t horizontal) {
    IdorResult r;
    std::memset(&r, 0, sizeof(r));

    r.endpoints_checked = endpoints;
    r.sequential_ids = sequential;
    r.predictable_patterns = predictable;
    r.missing_authz = no_authz;
    r.user_ref_exposure = user_ref;
    r.horizontal_escalation = horizontal;

    double weighted = no_authz * 4.0 + horizontal * 3.5 + user_ref * 3.0 +
                      sequential * 2.5 + predictable * 2.0;
    double max_w = (endpoints > 0) ? endpoints * 4.0 : 1.0;
    r.idor_risk = std::fmin(weighted / max_w, 1.0);
    r.critical = (no_authz > 0 && horizontal > 0);

    return r;
  }
};

} // namespace api_logic
