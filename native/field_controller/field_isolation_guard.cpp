/**
 * field_isolation_guard.cpp — Cross-Field Isolation Guard
 *
 * Prevents:
 *   - Cross-field dataset loading
 *   - Company-specific specialization
 *   - Mixed-field training batches
 *   - Unauthorized field access during training
 *
 * All datasets must carry a field tag matched against active field.
 */

#include <cstdint>
#include <cstdio>
#include <cstring>


namespace field_controller {

// =========================================================================
// FIELD TAG
// =========================================================================

struct FieldTag {
  char field_name[64];
  char category[64];
  bool is_generic; // must be true; company-specific = false = BLOCKED
};

// =========================================================================
// ISOLATION VERDICT
// =========================================================================

struct IsolationVerdict {
  bool allowed;
  bool field_matched;
  bool generic_check_pass;
  bool no_cross_contamination;
  char reason[256];
};

// =========================================================================
// FIELD ISOLATION GUARD
// =========================================================================

class FieldIsolationGuard {
public:
  static constexpr bool ALLOW_COMPANY_SPECIFIC = false;
  static constexpr bool ALLOW_CROSS_FIELD = false;

  explicit FieldIsolationGuard(const char *active_field) {
    std::strncpy(active_field_, active_field, 63);
    active_field_[63] = '\0';
    total_checks_ = 0;
    total_blocks_ = 0;
  }

  IsolationVerdict check_dataset(const FieldTag &tag) {
    IsolationVerdict v;
    std::memset(&v, 0, sizeof(v));
    ++total_checks_;

    // Check field match
    v.field_matched = (std::strcmp(active_field_, tag.field_name) == 0);

    // Block company-specific datasets
    v.generic_check_pass = tag.is_generic;

    // No cross-field contamination
    v.no_cross_contamination = v.field_matched;

    v.allowed =
        v.field_matched && v.generic_check_pass && v.no_cross_contamination;

    if (!v.allowed) {
      ++total_blocks_;
      if (!v.field_matched) {
        std::snprintf(v.reason, sizeof(v.reason),
                      "CROSS_FIELD_BLOCKED: dataset '%s' != active '%s'",
                      tag.field_name, active_field_);
      } else if (!v.generic_check_pass) {
        std::snprintf(v.reason, sizeof(v.reason),
                      "COMPANY_SPECIFIC_BLOCKED: dataset is not generic");
      }
    } else {
      std::snprintf(v.reason, sizeof(v.reason),
                    "ISOLATION_OK: field '%s' matched, generic=true",
                    tag.field_name);
    }

    return v;
  }

  // Check if a training batch is field-pure
  bool verify_batch_purity(const FieldTag *tags, uint32_t count) {
    for (uint32_t i = 0; i < count; ++i) {
      if (std::strcmp(active_field_, tags[i].field_name) != 0)
        return false;
      if (!tags[i].is_generic)
        return false;
    }
    return true;
  }

  void set_active_field(const char *field) {
    std::strncpy(active_field_, field, 63);
    active_field_[63] = '\0';
  }

  uint32_t total_checks() const { return total_checks_; }
  uint32_t total_blocks() const { return total_blocks_; }

private:
  char active_field_[64];
  uint32_t total_checks_;
  uint32_t total_blocks_;
};

} // namespace field_controller
