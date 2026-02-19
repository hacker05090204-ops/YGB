/**
 * postmessage_graph.cpp — postMessage Channel Analysis
 *
 * Maps postMessage communication patterns:
 *   - Missing origin validation
 *   - Wildcard targetOrigin ("*")
 *   - Data deserialization without validation
 *   - Cross-origin message handler chains
 *   - eval() or innerHTML in message handlers
 *
 * Field 1: Client-Side Web Application Security
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace client_side {

// =========================================================================
// POSTMESSAGE ANALYSIS RESULT
// =========================================================================

struct PostMessageResult {
  uint32_t handlers_found;
  uint32_t missing_origin_check;
  uint32_t wildcard_target;
  uint32_t unsafe_deserialize;
  uint32_t cross_origin_chains;
  uint32_t eval_in_handler;
  uint32_t innerhtml_in_handler;
  double channel_risk; // 0.0–1.0
  bool critical;
};

// =========================================================================
// POSTMESSAGE GRAPH ENGINE
// =========================================================================

class PostMessageGraph {
public:
  PostMessageResult analyze(uint32_t handlers, uint32_t no_origin,
                            uint32_t wildcard, uint32_t unsafe_deser,
                            uint32_t cross_chains, uint32_t eval_use,
                            uint32_t innerhtml_use) {
    PostMessageResult r;
    std::memset(&r, 0, sizeof(r));

    r.handlers_found = handlers;
    r.missing_origin_check = no_origin;
    r.wildcard_target = wildcard;
    r.unsafe_deserialize = unsafe_deser;
    r.cross_origin_chains = cross_chains;
    r.eval_in_handler = eval_use;
    r.innerhtml_in_handler = innerhtml_use;

    // Risk scoring
    double weighted = no_origin * 4.0 + eval_use * 4.0 + innerhtml_use * 3.5 +
                      wildcard * 3.0 + unsafe_deser * 2.5 + cross_chains * 2.0;
    double max_w = (handlers > 0) ? handlers * 4.0 : 1.0;
    r.channel_risk = std::fmin(weighted / max_w, 1.0);
    r.critical =
        (eval_use > 0 && no_origin > 0) || (innerhtml_use > 0 && no_origin > 0);

    return r;
  }
};

} // namespace client_side
