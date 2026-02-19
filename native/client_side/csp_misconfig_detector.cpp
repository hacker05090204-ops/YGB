/**
 * csp_misconfig_detector.cpp — CSP Misconfiguration Detection
 *
 * Detects Content Security Policy weaknesses:
 *   - Missing CSP header
 *   - unsafe-inline / unsafe-eval directives
 *   - Wildcard sources (* or *.domain)
 *   - Missing frame-ancestors (clickjacking)
 *   - Overly permissive connect-src
 *   - Nonce/hash bypass opportunities
 *
 * Field 1: Client-Side Web Application Security
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace client_side {

// =========================================================================
// CSP ISSUE TYPE
// =========================================================================

enum class CspIssue : uint8_t {
  MISSING_CSP = 0,
  UNSAFE_INLINE = 1,
  UNSAFE_EVAL = 2,
  WILDCARD_SRC = 3,
  MISSING_FRAME_ANCESTORS = 4,
  PERMISSIVE_CONNECT = 5,
  NONCE_BYPASS = 6,
  BASE_URI_MISSING = 7
};

// =========================================================================
// CSP ANALYSIS RESULT
// =========================================================================

struct CspAnalysisResult {
  bool has_csp;
  uint32_t issues_found;
  bool unsafe_inline;
  bool unsafe_eval;
  bool wildcard_present;
  bool frame_ancestors_missing;
  bool permissive_connect;
  bool nonce_bypass_possible;
  bool base_uri_missing;
  double csp_strength; // 0.0–1.0
  bool critical;
};

// =========================================================================
// CSP MISCONFIG DETECTOR
// =========================================================================

class CspMisconfigDetector {
public:
  CspAnalysisResult analyze(bool has_csp, bool unsafe_inline, bool unsafe_eval,
                            bool wildcard, bool frame_missing,
                            bool perm_connect, bool nonce_bypass,
                            bool base_missing) {
    CspAnalysisResult r;
    std::memset(&r, 0, sizeof(r));

    r.has_csp = has_csp;
    r.unsafe_inline = unsafe_inline;
    r.unsafe_eval = unsafe_eval;
    r.wildcard_present = wildcard;
    r.frame_ancestors_missing = frame_missing;
    r.permissive_connect = perm_connect;
    r.nonce_bypass_possible = nonce_bypass;
    r.base_uri_missing = base_missing;

    if (!has_csp) {
      r.issues_found = 1;
      r.csp_strength = 0.0;
      r.critical = true;
      return r;
    }

    // Count issues
    r.issues_found = 0;
    if (unsafe_inline)
      ++r.issues_found;
    if (unsafe_eval)
      ++r.issues_found;
    if (wildcard)
      ++r.issues_found;
    if (frame_missing)
      ++r.issues_found;
    if (perm_connect)
      ++r.issues_found;
    if (nonce_bypass)
      ++r.issues_found;
    if (base_missing)
      ++r.issues_found;

    // Strength score
    r.csp_strength = std::fmax(0.0, 1.0 - r.issues_found * 0.15);
    r.critical =
        (unsafe_inline && unsafe_eval) || !has_csp || (r.issues_found >= 4);

    return r;
  }
};

} // namespace client_side
