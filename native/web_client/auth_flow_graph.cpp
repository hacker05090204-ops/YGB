/**
 * auth_flow_graph.cpp — Authentication Flow Graph Analysis
 *
 * Maps authentication flows and identifies weaknesses:
 *   - Session management flaws
 *   - Token lifecycle issues
 *   - OAuth/OIDC misconfigurations
 *   - Password reset chain vulnerabilities
 *
 * Field: Client-Side + Web/API (Field 1)
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace web_client {

struct AuthFlowResult {
  uint32_t flows_mapped;
  uint32_t session_flaws;
  uint32_t token_issues;
  uint32_t oauth_misconfig;
  uint32_t reset_chain_vulns;
  uint32_t mfa_bypass_risks;
  double auth_strength; // 0.0–1.0
};

class AuthFlowGraph {
public:
  AuthFlowResult analyze(uint32_t flows, uint32_t session_flaws,
                         uint32_t token_issues, uint32_t oauth_misconfig,
                         uint32_t reset_vulns, uint32_t mfa_bypass) {
    AuthFlowResult r;
    std::memset(&r, 0, sizeof(r));
    r.flows_mapped = flows;
    r.session_flaws = session_flaws;
    r.token_issues = token_issues;
    r.oauth_misconfig = oauth_misconfig;
    r.reset_chain_vulns = reset_vulns;
    r.mfa_bypass_risks = mfa_bypass;

    uint32_t issues = session_flaws + token_issues + oauth_misconfig +
                      reset_vulns + mfa_bypass;
    r.auth_strength = (flows > 0)
                          ? std::fmax(0.0, 1.0 - (double)issues / (flows * 1.5))
                          : 0.0;
    return r;
  }
};

} // namespace web_client
