/**
 * subdomain_surface_engine.cpp — Subdomain Attack Surface Mapping
 *
 * Maps subdomain enumeration data to identify:
 *   - Exposed services, dangling DNS, takeover candidates
 *   - Certificate mismatches, wildcard exposure
 *   - Development/staging environment leaks
 *
 * Field: Client-Side + Web/API (Field 1)
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace web_client {

struct SubdomainResult {
  uint32_t total_subdomains;
  uint32_t exposed_services;
  uint32_t dangling_dns;
  uint32_t takeover_candidates;
  uint32_t cert_mismatches;
  uint32_t wildcard_certs;
  uint32_t staging_leaks;
  double surface_risk; // 0.0–1.0
};

class SubdomainSurfaceEngine {
public:
  SubdomainResult analyze(uint32_t total, uint32_t exposed, uint32_t dangling,
                          uint32_t takeover, uint32_t cert_mismatch,
                          uint32_t wildcard, uint32_t staging) {
    SubdomainResult r;
    std::memset(&r, 0, sizeof(r));
    r.total_subdomains = total;
    r.exposed_services = exposed;
    r.dangling_dns = dangling;
    r.takeover_candidates = takeover;
    r.cert_mismatches = cert_mismatch;
    r.wildcard_certs = wildcard;
    r.staging_leaks = staging;

    double risk = (takeover * 4.0 + dangling * 3.0 + staging * 2.5 +
                   cert_mismatch * 2.0 + wildcard * 1.5 + exposed * 1.0);
    r.surface_risk = (total > 0) ? std::fmin(risk / (total * 4.0), 1.0) : 0.0;
    return r;
  }
};

} // namespace web_client
