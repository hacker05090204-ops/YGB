/**
 * graphql_schema_analyzer.cpp — GraphQL Schema Security Analysis
 *
 * Detects GraphQL-specific vulnerabilities:
 *   - Introspection enabled in production
 *   - Query depth attacks (deeply nested queries)
 *   - Batch query abuse (aliasing/Array requests)
 *   - Field-level authorization gaps
 *   - Mutation without proper auth
 *   - Schema information leakage
 *
 * Field 2: API / Business Logic Security
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace api_logic {

struct GraphqlResult {
  bool introspection_enabled;
  uint32_t max_query_depth;
  uint32_t depth_limit_bypass;
  uint32_t batch_abuse_vectors;
  uint32_t field_authz_gaps;
  uint32_t unauthed_mutations;
  uint32_t schema_leaks;
  double schema_risk; // 0.0–1.0
  bool critical;
};

class GraphqlSchemaAnalyzer {
public:
  GraphqlResult analyze(bool introspection, uint32_t max_depth,
                        uint32_t depth_bypass, uint32_t batch_abuse,
                        uint32_t authz_gaps, uint32_t unauthed_muts,
                        uint32_t schema_leaks) {
    GraphqlResult r;
    std::memset(&r, 0, sizeof(r));

    r.introspection_enabled = introspection;
    r.max_query_depth = max_depth;
    r.depth_limit_bypass = depth_bypass;
    r.batch_abuse_vectors = batch_abuse;
    r.field_authz_gaps = authz_gaps;
    r.unauthed_mutations = unauthed_muts;
    r.schema_leaks = schema_leaks;

    double weighted = (introspection ? 3.0 : 0.0) + unauthed_muts * 4.0 +
                      authz_gaps * 3.0 + depth_bypass * 2.5 +
                      batch_abuse * 2.0 + schema_leaks * 1.5;
    double max_w = 20.0;
    r.schema_risk = std::fmin(weighted / max_w, 1.0);
    r.critical = (unauthed_muts > 0) || (introspection && authz_gaps > 0);

    return r;
  }
};

} // namespace api_logic
