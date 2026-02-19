/**
 * role_escalation_detector.cpp — Privilege Escalation Detection
 *
 * Detects horizontal and vertical privilege escalation:
 *   - Role bypasses via parameter manipulation
 *   - JWT/token claims modification
 *   - Admin endpoint access without proper role
 *   - Self-service role assignment
 *   - Multi-tenant boundary violations
 *
 * Field 2: API / Business Logic Security
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace api_logic {

struct RoleEscalationResult {
  uint32_t endpoints_checked;
  uint32_t horizontal_escalation;
  uint32_t vertical_escalation;
  uint32_t token_manipulation;
  uint32_t admin_access_bypass;
  uint32_t self_role_assign;
  uint32_t tenant_boundary_break;
  double escalation_risk; // 0.0–1.0
  bool critical;
};

class RoleEscalationDetector {
public:
  RoleEscalationResult analyze(uint32_t endpoints, uint32_t horizontal,
                               uint32_t vertical, uint32_t token_manip,
                               uint32_t admin_bypass, uint32_t self_role,
                               uint32_t tenant_break) {
    RoleEscalationResult r;
    std::memset(&r, 0, sizeof(r));

    r.endpoints_checked = endpoints;
    r.horizontal_escalation = horizontal;
    r.vertical_escalation = vertical;
    r.token_manipulation = token_manip;
    r.admin_access_bypass = admin_bypass;
    r.self_role_assign = self_role;
    r.tenant_boundary_break = tenant_break;

    double weighted = vertical * 4.0 + admin_bypass * 4.0 + tenant_break * 3.5 +
                      token_manip * 3.0 + self_role * 2.5 + horizontal * 2.0;
    double max_w = (endpoints > 0) ? endpoints * 4.0 : 1.0;
    r.escalation_risk = std::fmin(weighted / max_w, 1.0);
    r.critical = (vertical > 0) || (admin_bypass > 0) || (tenant_break > 0);

    return r;
  }
};

} // namespace api_logic
