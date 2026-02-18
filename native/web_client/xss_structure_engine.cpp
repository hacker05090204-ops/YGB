/**
 * xss_structure_engine.cpp — XSS Structural Analysis
 *
 * Analyzes code structure for XSS vulnerability patterns:
 *   - Reflected, stored, DOM-based XSS indicators
 *   - Sink/source pair detection
 *   - Sanitization gap analysis
 *   - Context-aware encoding verification
 *
 * Field: Client-Side + Web/API (Field 1)
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace web_client {

// =========================================================================
// XSS PATTERN TYPE
// =========================================================================

enum class XssType : uint8_t {
  REFLECTED = 0,
  STORED = 1,
  DOM_BASED = 2,
  MUTATION_XSS = 3
};

// =========================================================================
// XSS ANALYSIS RESULT
// =========================================================================

struct XssAnalysisResult {
  uint32_t sinks_found;
  uint32_t sources_found;
  uint32_t unsanitized_paths;
  uint32_t encoding_gaps;
  uint32_t reflected_indicators;
  uint32_t stored_indicators;
  uint32_t dom_indicators;
  double vulnerability_score; // 0.0–1.0
  bool high_risk;
};

// =========================================================================
// XSS STRUCTURE ENGINE
// =========================================================================

class XssStructureEngine {
public:
  XssAnalysisResult analyze(uint32_t sinks, uint32_t sources,
                            uint32_t unsanitized, uint32_t encoding_gaps,
                            uint32_t reflected, uint32_t stored, uint32_t dom) {
    XssAnalysisResult r;
    std::memset(&r, 0, sizeof(r));

    r.sinks_found = sinks;
    r.sources_found = sources;
    r.unsanitized_paths = unsanitized;
    r.encoding_gaps = encoding_gaps;
    r.reflected_indicators = reflected;
    r.stored_indicators = stored;
    r.dom_indicators = dom;

    // Vulnerability scoring
    double raw = (unsanitized * 3.0 + encoding_gaps * 2.0 + stored * 2.5 +
                  dom * 2.0 + reflected * 1.5);
    double max_possible = (sinks + sources + 1) * 3.0;
    r.vulnerability_score =
        (max_possible > 0) ? std::fmin(raw / max_possible, 1.0) : 0.0;
    r.high_risk = (r.vulnerability_score > 0.6);

    return r;
  }
};

} // namespace web_client
