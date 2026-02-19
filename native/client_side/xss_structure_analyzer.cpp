/**
 * xss_structure_analyzer.cpp — XSS Structural Analysis Engine
 *
 * Deep structural analysis for XSS vulnerability patterns:
 *   - Reflected XSS (user input → response body without encoding)
 *   - Stored XSS (persisted input → rendered without sanitization)
 *   - DOM-based XSS (client-side sink/source pairs)
 *   - Mutation XSS (browser parser differential exploitation)
 *   - Context-aware encoding gap detection (HTML/JS/URL/CSS)
 *
 * Field 1: Client-Side Web Application Security
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace client_side {

// =========================================================================
// ENCODING CONTEXT
// =========================================================================

enum class EncodingContext : uint8_t {
  HTML_BODY = 0,
  HTML_ATTRIBUTE = 1,
  JAVASCRIPT = 2,
  URL_PARAM = 3,
  CSS_VALUE = 4
};

// =========================================================================
// XSS ANALYSIS RESULT
// =========================================================================

struct XssStructureResult {
  uint32_t sinks_total;
  uint32_t sources_total;
  uint32_t unencoded_paths;
  uint32_t reflected_patterns;
  uint32_t stored_patterns;
  uint32_t dom_patterns;
  uint32_t mutation_patterns;
  uint32_t context_gaps[5]; // per encoding context
  double coverage_score;    // encoding coverage 0.0–1.0
  double vulnerability_density;
  bool critical;
};

// =========================================================================
// XSS STRUCTURE ANALYZER
// =========================================================================

class XssStructureAnalyzer {
public:
  XssStructureResult analyze(uint32_t sinks, uint32_t sources,
                             uint32_t unencoded, uint32_t reflected,
                             uint32_t stored, uint32_t dom, uint32_t mutation,
                             const uint32_t ctx_gaps[5]) {
    XssStructureResult r;
    std::memset(&r, 0, sizeof(r));

    r.sinks_total = sinks;
    r.sources_total = sources;
    r.unencoded_paths = unencoded;
    r.reflected_patterns = reflected;
    r.stored_patterns = stored;
    r.dom_patterns = dom;
    r.mutation_patterns = mutation;

    uint32_t total_gaps = 0;
    for (int i = 0; i < 5; ++i) {
      r.context_gaps[i] = ctx_gaps[i];
      total_gaps += ctx_gaps[i];
    }

    uint32_t total_patterns = reflected + stored + dom + mutation;
    r.vulnerability_density =
        (sinks > 0) ? (double)total_patterns / sinks : 0.0;

    // Coverage: what fraction of sink/source pairs are properly encoded
    uint32_t total_paths = sinks * sources;
    if (total_paths > 0) {
      r.coverage_score = 1.0 - (double)unencoded / total_paths;
      if (r.coverage_score < 0.0)
        r.coverage_score = 0.0;
    }

    r.critical = (stored > 0) || (unencoded > sinks / 2) ||
                 (r.vulnerability_density > 0.5);

    return r;
  }
};

} // namespace client_side
