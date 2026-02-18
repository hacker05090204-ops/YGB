/**
 * mode_progression_guard.cpp — MODE-A → MODE-B → MODE-C Strict Chaining
 *
 * Progression gates:
 *   - Lab precision >= 96%
 *   - ECE <= 0.018
 *   - Duplicate detection >= 90%
 *   - 7-day temporal stability PASS
 *   - No containment events for 7 days
 *
 * No skipping modes. No production autonomy. No governance unlock.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace performance {

// =========================================================================
// OPERATIONAL MODE
// =========================================================================

enum class OpMode : uint8_t {
  MODE_A_LAB = 0,
  MODE_B_SHADOW = 1,
  MODE_C_PRODUCTION = 2
};

static const char *mode_name(OpMode m) {
  switch (m) {
  case OpMode::MODE_A_LAB:
    return "MODE_A_LAB";
  case OpMode::MODE_B_SHADOW:
    return "MODE_B_SHADOW";
  case OpMode::MODE_C_PRODUCTION:
    return "MODE_C_PRODUCTION";
  default:
    return "UNKNOWN";
  }
}

// =========================================================================
// PROGRESSION GATES
// =========================================================================

struct ProgressionGates {
  double min_precision;         // 0.96
  double max_ece;               // 0.018
  double min_dup_detection;     // 0.90
  uint32_t stability_days;      // 7
  uint32_t no_containment_days; // 7
};

static ProgressionGates default_gates() { return {0.96, 0.018, 0.90, 7, 7}; }

// =========================================================================
// PROGRESSION RESULT
// =========================================================================

struct ProgressionResult {
  bool precision_pass;
  bool ece_pass;
  bool dup_pass;
  bool stability_pass;
  bool containment_pass;
  bool all_pass;
  OpMode current;
  OpMode requested;
  bool allowed;
  char reason[256];
};

// =========================================================================
// MODE PROGRESSION GUARD
// =========================================================================

class ModeProgressionGuard {
public:
  static constexpr bool ALLOW_SKIP = false;
  static constexpr bool ALLOW_AUTONOMY = false;

  explicit ModeProgressionGuard(ProgressionGates gates = default_gates())
      : gates_(gates), current_(OpMode::MODE_A_LAB) {}

  ProgressionResult evaluate(double precision, double ece, double dup_detection,
                             uint32_t stable_days, uint32_t no_containment_days,
                             OpMode requested) {
    ProgressionResult r;
    std::memset(&r, 0, sizeof(r));
    r.current = current_;
    r.requested = requested;

    // No skipping
    if (static_cast<uint8_t>(requested) > static_cast<uint8_t>(current_) + 1) {
      r.allowed = false;
      std::snprintf(r.reason, sizeof(r.reason),
                    "SKIP_BLOCKED: %s -> %s (must go step by step)",
                    mode_name(current_), mode_name(requested));
      return r;
    }

    // No backward (handled by lifecycle engine but double-checked)
    if (requested <= current_) {
      r.allowed = false;
      std::snprintf(r.reason, sizeof(r.reason), "BACKWARD_BLOCKED: %s -> %s",
                    mode_name(current_), mode_name(requested));
      return r;
    }

    // Gate checks
    r.precision_pass = (precision >= gates_.min_precision);
    r.ece_pass = (ece <= gates_.max_ece);
    r.dup_pass = (dup_detection >= gates_.min_dup_detection);
    r.stability_pass = (stable_days >= gates_.stability_days);
    r.containment_pass = (no_containment_days >= gates_.no_containment_days);

    r.all_pass = r.precision_pass && r.ece_pass && r.dup_pass &&
                 r.stability_pass && r.containment_pass;

    if (r.all_pass) {
      current_ = requested;
      r.allowed = true;
      std::snprintf(r.reason, sizeof(r.reason),
                    "PROGRESSION: %s -> %s APPROVED", mode_name(r.current),
                    mode_name(requested));
    } else {
      r.allowed = false;
      std::snprintf(r.reason, sizeof(r.reason),
                    "GATES_FAILED: prec=%s ece=%s dup=%s stab=%s cont=%s",
                    r.precision_pass ? "OK" : "FAIL",
                    r.ece_pass ? "OK" : "FAIL", r.dup_pass ? "OK" : "FAIL",
                    r.stability_pass ? "OK" : "FAIL",
                    r.containment_pass ? "OK" : "FAIL");
    }

    return r;
  }

  OpMode current() const { return current_; }

  // Force lock to MODE-A (stress loop trigger)
  void force_mode_a() { current_ = OpMode::MODE_A_LAB; }

private:
  ProgressionGates gates_;
  OpMode current_;
};

} // namespace performance
