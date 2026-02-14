/*
 * submission_blocker.cpp — Report Submission Blocker
 *
 * IMMUTABLE RULES:
 *   - No auto-submission to any bug bounty platform
 *   - All export attempts logged
 *   - Manual approval required before export
 *   - Export = local file only, never network submission
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int MAX_EXPORT_LOG = 1000;
static constexpr int MAX_PATH_LEN = 512;

// =========================================================================
// TYPES
// =========================================================================

enum class ExportType {
  LOCAL_FILE,
  CLIPBOARD,
  NETWORK_SUBMIT // Always blocked
};

enum class ExportStatus { EXPORTED, BLOCKED, PENDING_APPROVAL };

struct ExportAttempt {
  int sequence;
  time_t timestamp;
  ExportType type;
  ExportStatus status;
  char report_id[64];
  char destination[MAX_PATH_LEN];
  bool user_approved;
  char reason[256];
};

// =========================================================================
// SUBMISSION BLOCKER
// =========================================================================

class SubmissionBlocker {
private:
  ExportAttempt log_[MAX_EXPORT_LOG];
  int log_count_;

  void log_attempt(ExportType type, ExportStatus status, const char *report_id,
                   const char *dest, bool approved, const char *reason) {
    if (log_count_ < MAX_EXPORT_LOG) {
      ExportAttempt &e = log_[log_count_];
      e.sequence = log_count_;
      e.timestamp = std::time(nullptr);
      e.type = type;
      e.status = status;
      std::strncpy(e.report_id, report_id, sizeof(e.report_id) - 1);
      std::strncpy(e.destination, dest, MAX_PATH_LEN - 1);
      e.user_approved = approved;
      std::strncpy(e.reason, reason, sizeof(e.reason) - 1);
      log_count_++;
    }
  }

public:
  SubmissionBlocker() : log_count_(0) { std::memset(log_, 0, sizeof(log_)); }

  // =======================================================================
  // SUBMISSION CONTROL
  // =======================================================================

  ExportStatus request_export(ExportType type, const char *report_id,
                              const char *destination, bool user_approved) {
    // HARD BLOCK: Network submission is NEVER allowed
    if (type == ExportType::NETWORK_SUBMIT) {
      log_attempt(type, ExportStatus::BLOCKED, report_id, destination, false,
                  "BLOCKED: Network submission permanently disabled");
      std::fprintf(stderr,
              "[SUBMISSION BLOCKER] Network submit BLOCKED for report %s\n",
              report_id);
      return ExportStatus::BLOCKED;
    }

    // Local export requires manual approval
    if (!user_approved) {
      log_attempt(type, ExportStatus::PENDING_APPROVAL, report_id, destination,
                  false, "Pending user approval for local export");
      return ExportStatus::PENDING_APPROVAL;
    }

    // Approved local export
    log_attempt(type, ExportStatus::EXPORTED, report_id, destination, true,
                "Exported with user approval");
    return ExportStatus::EXPORTED;
  }

  ExportStatus request_network_submit(const char *platform,
                                      const char *report_id) {
    char dest[MAX_PATH_LEN];
    std::snprintf(dest, sizeof(dest), "platform:%s", platform);
    log_attempt(ExportType::NETWORK_SUBMIT, ExportStatus::BLOCKED, report_id,
                dest, false,
                "BLOCKED: Auto-submission to external platform is prohibited");
    std::fprintf(stderr,
            "[SUBMISSION BLOCKER] Auto-submit to '%s' BLOCKED (report: %s)\n",
            platform, report_id);
    return ExportStatus::BLOCKED;
  }

  // =======================================================================
  // GUARDS
  // =======================================================================

  static bool can_auto_submit() { return false; }
  static bool can_submit_to_hackerone() { return false; }
  static bool can_submit_to_bugcrowd() { return false; }
  static bool can_submit_to_any_platform() { return false; }
  static bool can_bypass_approval() { return false; }
  static bool can_delete_export_log() { return false; }

  // =======================================================================
  // LOG ACCESS
  // =======================================================================

  int log_count() const { return log_count_; }

  int count_blocked() const {
    int c = 0;
    for (int i = 0; i < log_count_; i++)
      if (log_[i].status == ExportStatus::BLOCKED)
        c++;
    return c;
  }

  const ExportAttempt *get_entry(int i) const {
    return (i >= 0 && i < log_count_) ? &log_[i] : nullptr;
  }
};
