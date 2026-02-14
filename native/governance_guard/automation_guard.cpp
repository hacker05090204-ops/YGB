/*
 * automation_guard.cpp — Governance Automation Guard
 *
 * IMMUTABLE RULES:
 *   - No auto-report submission to any platform
 *   - No authority unlock (severity, exploit, governance)
 *   - No platform automation beyond user-approved scope
 *   - All hunting actions logged with timestamp
 *   - Severity labeling locked (user-assigned only)
 *   - Exploit logic locked (no reasoning unlock)
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

// =========================================================================
// CONSTANTS — COMPILE-TIME, IMMUTABLE
// =========================================================================

static constexpr int MAX_ACTION_LOG = 10000;
static constexpr int MAX_ACTION_DESC = 512;
static constexpr int MAX_ACTOR_NAME = 64;

// =========================================================================
// TYPES
// =========================================================================

enum class ActionType {
  SCOPE_CHECK,
  TARGET_SELECT,
  HUNT_START,
  HUNT_STEP,
  EVIDENCE_CAPTURE,
  REPORT_BUILD,
  REPORT_EXPORT,
  REPORT_SUBMIT_ATTEMPT,
  AUTHORITY_REQUEST,
  MODE_CHANGE,
  VOICE_COMMAND
};

enum class ActionResult { ALLOWED, BLOCKED, LOGGED_ONLY };

struct ActionLogEntry {
  int sequence;
  time_t timestamp;
  ActionType action;
  ActionResult result;
  char actor[MAX_ACTOR_NAME];
  char description[MAX_ACTION_DESC];
  bool governance_approved;
};

// =========================================================================
// AUTOMATION GUARD
// =========================================================================

class AutomationGuard {
private:
  ActionLogEntry log_[MAX_ACTION_LOG];
  int log_count_;

  ActionResult log_action(ActionType type, ActionResult result,
                          const char *actor, const char *desc, bool approved) {
    if (log_count_ < MAX_ACTION_LOG) {
      ActionLogEntry &e = log_[log_count_];
      e.sequence = log_count_;
      e.timestamp = std::time(nullptr);
      e.action = type;
      e.result = result;
      std::strncpy(e.actor, actor, MAX_ACTOR_NAME - 1);
      e.actor[MAX_ACTOR_NAME - 1] = '\0';
      std::strncpy(e.description, desc, MAX_ACTION_DESC - 1);
      e.description[MAX_ACTION_DESC - 1] = '\0';
      e.governance_approved = approved;
      log_count_++;
    }
    return result;
  }

public:
  AutomationGuard() : log_count_(0) { std::memset(log_, 0, sizeof(log_)); }

  // =======================================================================
  // IMMUTABLE GUARDS — always return false
  // =======================================================================

  static bool can_auto_submit() { return false; }
  static bool can_unlock_authority() { return false; }
  static bool can_modify_severity_label() { return false; }
  static bool can_unlock_exploit_logic() { return false; }
  static bool can_impersonate_researcher() { return false; }
  static bool can_scrape_beyond_scope() { return false; }
  static bool can_bypass_manual_approval() { return false; }
  static bool can_auto_hunt_without_consent() { return false; }

  // =======================================================================
  // ACTION VALIDATORS
  // =======================================================================

  ActionResult request_submission(const char *platform, const char *report_id) {
    char desc[MAX_ACTION_DESC];
    std::snprintf(desc, sizeof(desc),
             "BLOCKED: Auto-submission attempt to %s (report: %s)", platform,
             report_id);
    std::fprintf(stderr, "[GOVERNANCE] %s\n", desc);
    return log_action(ActionType::REPORT_SUBMIT_ATTEMPT, ActionResult::BLOCKED,
                      "system", desc, false);
  }

  ActionResult request_authority_unlock(const char *authority_type) {
    char desc[MAX_ACTION_DESC];
    std::snprintf(desc, sizeof(desc), "BLOCKED: Authority unlock request for '%s'",
             authority_type);
    std::fprintf(stderr, "[GOVERNANCE] %s\n", desc);
    return log_action(ActionType::AUTHORITY_REQUEST, ActionResult::BLOCKED,
                      "system", desc, false);
  }

  ActionResult log_hunt_action(const char *actor, const char *description) {
    return log_action(ActionType::HUNT_STEP, ActionResult::LOGGED_ONLY, actor,
                      description, true);
  }

  ActionResult log_evidence_capture(const char *evidence_type,
                                    const char *hash) {
    char desc[MAX_ACTION_DESC];
    std::snprintf(desc, sizeof(desc), "Evidence captured: %s (hash: %.16s...)",
             evidence_type, hash);
    return log_action(ActionType::EVIDENCE_CAPTURE, ActionResult::ALLOWED,
                      "system", desc, true);
  }

  ActionResult request_report_export(bool manual_approval) {
    if (!manual_approval) {
      return log_action(ActionType::REPORT_EXPORT, ActionResult::BLOCKED,
                        "system", "BLOCKED: Export without manual approval",
                        false);
    }
    return log_action(ActionType::REPORT_EXPORT, ActionResult::ALLOWED, "user",
                      "Report export approved by user", true);
  }

  ActionResult request_target_selection(const char *domain,
                                        bool user_approved) {
    char desc[MAX_ACTION_DESC];
    if (!user_approved) {
      std::snprintf(desc, sizeof(desc), "BLOCKED: Target '%s' not user-approved",
               domain);
      return log_action(ActionType::TARGET_SELECT, ActionResult::BLOCKED,
                        "system", desc, false);
    }
    std::snprintf(desc, sizeof(desc), "Target '%s' approved by user", domain);
    return log_action(ActionType::TARGET_SELECT, ActionResult::ALLOWED, "user",
                      desc, true);
  }

  // =======================================================================
  // LOG ACCESS
  // =======================================================================

  int log_count() const { return log_count_; }

  const ActionLogEntry *get_log_entry(int index) const {
    if (index >= 0 && index < log_count_)
      return &log_[index];
    return nullptr;
  }

  int count_blocked() const {
    int count = 0;
    for (int i = 0; i < log_count_; i++) {
      if (log_[i].result == ActionResult::BLOCKED)
        count++;
    }
    return count;
  }

  int count_allowed() const {
    int count = 0;
    for (int i = 0; i < log_count_; i++) {
      if (log_[i].result == ActionResult::ALLOWED)
        count++;
    }
    return count;
  }
};
