/**
 * state_machine_validator.cpp — State Transition Bypass Detection
 *
 * Validates state machine integrity in business workflows:
 *   - Skippable steps in multi-step processes
 *   - Replay attacks on state transitions
 *   - Race conditions in concurrent state changes
 *   - Invalid state transition paths
 *
 * Field 2: API / Business Logic Security
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace api_logic {

struct StateMachineResult {
  uint32_t workflows_checked;
  uint32_t skippable_steps;
  uint32_t replay_vulnerabilities;
  uint32_t race_conditions;
  uint32_t invalid_transitions;
  uint32_t missing_validations;
  double integrity_score; // 0.0–1.0 (higher = more secure)
  bool critical;
};

class StateMachineValidator {
public:
  StateMachineResult analyze(uint32_t workflows, uint32_t skippable,
                             uint32_t replay, uint32_t race, uint32_t invalid,
                             uint32_t missing_val) {
    StateMachineResult r;
    std::memset(&r, 0, sizeof(r));

    r.workflows_checked = workflows;
    r.skippable_steps = skippable;
    r.replay_vulnerabilities = replay;
    r.race_conditions = race;
    r.invalid_transitions = invalid;
    r.missing_validations = missing_val;

    uint32_t issues = skippable + replay + race + invalid + missing_val;
    uint32_t max_issues = workflows * 3;
    r.integrity_score = (max_issues > 0)
                            ? std::fmax(0.0, 1.0 - (double)issues / max_issues)
                            : 0.0;
    r.critical = (skippable > 0 && missing_val > 0) || (replay > 0 && race > 0);

    return r;
  }
};

} // namespace api_logic
