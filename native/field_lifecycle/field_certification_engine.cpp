/**
 * field_certification_engine.cpp — Dual-Threshold Certification
 *
 * Client-Side thresholds:
 *   Precision ≥ 0.96, FPR ≤ 0.04, Dup ≥ 0.88, ECE ≤ 0.018
 *
 * API thresholds:
 *   Precision ≥ 0.95, FPR ≤ 0.05, Dup ≥ 0.85, ECE ≤ 0.02
 *
 * Both require: 7-day stability PASS + human approval
 * NO auto-certification. NO authority unlock.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace field_lifecycle {

// =========================================================================
// THRESHOLDS
// =========================================================================

struct CertThresholds {
  double min_precision;
  double max_fpr;
  double min_dup;
  double max_ece;
  uint32_t min_stability_days;
};

static CertThresholds client_side_thresholds() {
  return {0.96, 0.04, 0.88, 0.018, 7};
}
static CertThresholds api_thresholds() { return {0.95, 0.05, 0.85, 0.02, 7}; }

// =========================================================================
// CERTIFICATION RESULT
// =========================================================================

struct CertResult {
  bool precision_pass;
  bool fpr_pass;
  bool dup_pass;
  bool ece_pass;
  bool stability_pass;
  bool human_pass;
  bool all_pass;
  uint32_t gates_passed;
  char summary[512];
};

// =========================================================================
// CERTIFICATION ENGINE
// =========================================================================

class FieldCertificationEngine {
public:
  static constexpr bool ALLOW_AUTO_CERT = false;
  static constexpr bool ALLOW_AUTHORITY_UNLOCK = false;

  CertResult evaluate_client_side(double prec, double fpr, double dup,
                                  double ece, uint32_t days, bool human) {
    return evaluate(prec, fpr, dup, ece, days, human, client_side_thresholds(),
                    "CLIENT_SIDE");
  }

  CertResult evaluate_api(double prec, double fpr, double dup, double ece,
                          uint32_t days, bool human) {
    return evaluate(prec, fpr, dup, ece, days, human, api_thresholds(), "API");
  }

  CertResult evaluate_extended(double prec, double fpr, double dup, double ece,
                               uint32_t days, bool human) {
    // Extended ladder fields use API thresholds as baseline
    return evaluate(prec, fpr, dup, ece, days, human, api_thresholds(),
                    "EXTENDED");
  }

private:
  CertResult evaluate(double prec, double fpr, double dup, double ece,
                      uint32_t days, bool human, const CertThresholds &t,
                      const char *tag) {
    CertResult r;
    std::memset(&r, 0, sizeof(r));

    r.precision_pass = (prec >= t.min_precision);
    r.fpr_pass = (fpr <= t.max_fpr);
    r.dup_pass = (dup >= t.min_dup);
    r.ece_pass = (ece <= t.max_ece);
    r.stability_pass = (days >= t.min_stability_days);
    r.human_pass = human;

    r.gates_passed = 0;
    if (r.precision_pass)
      ++r.gates_passed;
    if (r.fpr_pass)
      ++r.gates_passed;
    if (r.dup_pass)
      ++r.gates_passed;
    if (r.ece_pass)
      ++r.gates_passed;
    if (r.stability_pass)
      ++r.gates_passed;
    if (r.human_pass)
      ++r.gates_passed;
    r.all_pass = (r.gates_passed == 6);

    std::snprintf(r.summary, sizeof(r.summary),
                  "[%s] %u/6: prec=%.3f%s fpr=%.3f%s dup=%.3f%s "
                  "ece=%.4f%s stab=%ud%s human=%s%s",
                  tag, r.gates_passed, prec, r.precision_pass ? "OK" : "FAIL",
                  fpr, r.fpr_pass ? "OK" : "FAIL", dup,
                  r.dup_pass ? "OK" : "FAIL", ece, r.ece_pass ? "OK" : "FAIL",
                  days, r.stability_pass ? "OK" : "FAIL", human ? "yes" : "no",
                  r.human_pass ? "OK" : "FAIL");
    return r;
  }
};

} // namespace field_lifecycle
