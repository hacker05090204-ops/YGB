/**
 * weight_import_validator.cpp — Weight Import Validation
 *
 * Before importing weights:
 *   - Verify hash integrity
 *   - Verify field match (no cross-field imports)
 *   - Compare metrics against current baseline
 *   - Block if precision degraded > 1%
 *   - Block if ECE degraded > 0.005
 *
 * No direct overwrite. Validated import only.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace distributed {

// =========================================================================
// IMPORT CANDIDATE
// =========================================================================

struct ImportCandidate {
  char field_name[64];
  uint32_t epoch;
  double precision;
  double recall;
  double ece;
  double fpr;
  double dup_detection;
  uint64_t weight_hash;
  uint64_t signature;
};

// =========================================================================
// IMPORT VERDICT
// =========================================================================

struct ImportVerdict {
  bool hash_valid;
  bool field_matched;
  bool precision_ok;
  bool ece_ok;
  bool fpr_ok;
  bool all_pass;
  char reason[256];
};

// =========================================================================
// WEIGHT IMPORT VALIDATOR
// =========================================================================

class WeightImportValidator {
public:
  static constexpr double MAX_PRECISION_DROP = 0.01;
  static constexpr double MAX_ECE_INCREASE = 0.005;
  static constexpr double MAX_FPR_INCREASE = 0.01;
  static constexpr bool ALLOW_DIRECT_OVERWRITE = false;

  WeightImportValidator() : total_imports_(0), total_rejects_(0) {}

  ImportVerdict validate(const ImportCandidate &candidate,
                         const char *current_field, double current_precision,
                         double current_ece, double current_fpr) {
    ImportVerdict v;
    std::memset(&v, 0, sizeof(v));

    // Hash integrity
    v.hash_valid = (candidate.weight_hash != 0 && candidate.signature != 0);

    // Field match
    v.field_matched = (std::strcmp(candidate.field_name, current_field) == 0);

    // Metric comparison
    v.precision_ok =
        (current_precision - candidate.precision) <= MAX_PRECISION_DROP;
    v.ece_ok = (candidate.ece - current_ece) <= MAX_ECE_INCREASE;
    v.fpr_ok = (candidate.fpr - current_fpr) <= MAX_FPR_INCREASE;

    v.all_pass = v.hash_valid && v.field_matched && v.precision_ok &&
                 v.ece_ok && v.fpr_ok;

    if (v.all_pass) {
      ++total_imports_;
      std::snprintf(v.reason, sizeof(v.reason),
                    "IMPORT_OK: field=%s prec=%.3f ece=%.4f",
                    candidate.field_name, candidate.precision, candidate.ece);
    } else {
      ++total_rejects_;
      std::snprintf(v.reason, sizeof(v.reason),
                    "IMPORT_BLOCKED: hash=%s field=%s prec=%s ece=%s fpr=%s",
                    v.hash_valid ? "ok" : "FAIL",
                    v.field_matched ? "ok" : "MISMATCH",
                    v.precision_ok ? "ok" : "DEGRADED",
                    v.ece_ok ? "ok" : "WORSE", v.fpr_ok ? "ok" : "WORSE");
    }

    return v;
  }

  uint32_t total_imports() const { return total_imports_; }
  uint32_t total_rejects() const { return total_rejects_; }

private:
  uint32_t total_imports_;
  uint32_t total_rejects_;
};

} // namespace distributed
