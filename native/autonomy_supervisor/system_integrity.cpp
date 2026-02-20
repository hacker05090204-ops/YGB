/**
 * System Integrity Supervisor — Unified Weighted Integrity Score Engine
 *
 * Aggregates sub-system scores into a single SYSTEM_INTEGRITY_SCORE (0–100).
 *
 * Weights:
 *   ML Integrity        0.25
 *   Dataset Integrity    0.20
 *   Storage Integrity    0.15
 *   Resource Integrity   0.15
 *   Log Integrity        0.10
 *   Governance Integrity 0.15
 *
 * If overall_score < 95:
 *     disable shadow mode
 *     force MODE-A only
 *
 * No silent degradation allowed. Every state transition is logged.
 */

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <ctime>
#include <string>
#include <vector>

// ============================================================================
// Enums
// ============================================================================

enum class IntegrityStatus {
  GREEN = 0,  // Score >= 90
  YELLOW = 1, // Score >= 70
  RED = 2     // Score < 70
};

enum class SupervisorMode {
  MODE_A_ONLY = 0,   // Human-only, AI disabled
  MODE_B_SHADOW = 1, // Shadow-only, no authority
  CONTAINMENT = 2    // Locked down
};

// ============================================================================
// Sub-system Score
// ============================================================================

struct SubSystemScore {
  double score; // 0–100
  IntegrityStatus status;
  char subsystem[64];
  char detail[256];
  double weight;
};

// ============================================================================
// Autonomy Condition
// ============================================================================

struct AutonomyCondition {
  bool overall_above_threshold; // overall_integrity > 95
  bool no_containment_24h;      // no containment events in last 24h
  bool no_drift_anomalies;      // no drift alerts
  bool no_dataset_skew;         // no class imbalance alerts
  bool no_storage_warnings;     // no HDD/backup alerts
  bool shadow_allowed;          // ALL conditions must be true
  char blocked_reasons[1024];   // semicolon-separated reasons
};

// ============================================================================
// Integrity Event Log Entry
// ============================================================================

struct IntegrityEvent {
  uint64_t event_id;
  double timestamp;
  double previous_score;
  double new_score;
  IntegrityStatus previous_status;
  IntegrityStatus new_status;
  SupervisorMode mode_transition;
  char description[256];
  uint8_t signature[32]; // FNV-1a hash of event data
};

// ============================================================================
// System Integrity Supervisor
// ============================================================================

class SystemIntegritySupervisor {
private:
  // Weights
  static constexpr double W_ML = 0.25;
  static constexpr double W_DATASET = 0.20;
  static constexpr double W_STORAGE = 0.15;
  static constexpr double W_RESOURCE = 0.15;
  static constexpr double W_LOG = 0.10;
  static constexpr double W_GOVERN = 0.15;

  // Thresholds
  static constexpr double SHADOW_THRESHOLD = 95.0;
  static constexpr double GREEN_THRESHOLD = 90.0;
  static constexpr double YELLOW_THRESHOLD = 70.0;

  // Sub-scores
  double ml_score_;
  double dataset_score_;
  double storage_score_;
  double resource_score_;
  double log_score_;
  double governance_score_;
  double overall_score_;

  // State
  SupervisorMode current_mode_;
  IntegrityStatus current_status_;
  bool shadow_allowed_;
  uint64_t next_event_id_;

  // Event log
  std::vector<IntegrityEvent> event_log_;

  // Containment event timestamps (Unix epoch seconds)
  std::vector<double> containment_timestamps_;

  // Alert flags
  bool drift_alert_;
  bool dataset_skew_alert_;
  bool storage_warning_;

  // -------------------------------------------------------------------

  static IntegrityStatus score_to_status(double s) {
    if (s >= GREEN_THRESHOLD)
      return IntegrityStatus::GREEN;
    if (s >= YELLOW_THRESHOLD)
      return IntegrityStatus::YELLOW;
    return IntegrityStatus::RED;
  }

  static double clamp_score(double s) {
    return std::max(0.0, std::min(100.0, s));
  }

  void sign_event(IntegrityEvent &ev) {
    uint8_t data[128];
    std::memset(data, 0, 128);
    std::memcpy(data, &ev.event_id, 8);
    std::memcpy(data + 8, &ev.timestamp, 8);
    std::memcpy(data + 16, &ev.previous_score, 8);
    std::memcpy(data + 24, &ev.new_score, 8);

    uint32_t hash = 0x811c9dc5;
    for (int i = 0; i < 128; i++) {
      hash ^= data[i];
      hash *= 0x01000193;
    }
    std::memset(ev.signature, 0, 32);
    for (int i = 0; i < 8; i++) {
      std::memcpy(ev.signature + i * 4, &hash, 4);
      hash ^= (hash >> 3) ^ (hash << 7);
      hash *= 0x01000193;
    }
  }

  void log_transition(double prev_score, double new_score,
                      IntegrityStatus prev_status, IntegrityStatus new_status,
                      SupervisorMode mode, const char *desc) {
    IntegrityEvent ev;
    ev.event_id = next_event_id_++;
    ev.timestamp = static_cast<double>(std::time(nullptr));
    ev.previous_score = prev_score;
    ev.new_score = new_score;
    ev.previous_status = prev_status;
    ev.new_status = new_status;
    ev.mode_transition = mode;
    std::strncpy(ev.description, desc, 255);
    ev.description[255] = '\0';
    sign_event(ev);
    event_log_.push_back(ev);
  }

  bool has_containment_in_last_24h() const {
    double now = static_cast<double>(std::time(nullptr));
    double cutoff = now - 86400.0; // 24 hours
    for (const auto &ts : containment_timestamps_) {
      if (ts >= cutoff)
        return true;
    }
    return false;
  }

public:
  SystemIntegritySupervisor()
      : ml_score_(100.0), dataset_score_(100.0), storage_score_(100.0),
        resource_score_(100.0), log_score_(100.0), governance_score_(100.0),
        overall_score_(100.0), current_mode_(SupervisorMode::MODE_A_ONLY),
        current_status_(IntegrityStatus::GREEN), shadow_allowed_(false),
        next_event_id_(0), drift_alert_(false), dataset_skew_alert_(false),
        storage_warning_(false) {}

  // -------------------------------------------------------------------
  // Score Setters (from subsystem monitors)
  // -------------------------------------------------------------------

  void set_ml_score(double s) { ml_score_ = clamp_score(s); }
  void set_dataset_score(double s) { dataset_score_ = clamp_score(s); }
  void set_storage_score(double s) { storage_score_ = clamp_score(s); }
  void set_resource_score(double s) { resource_score_ = clamp_score(s); }
  void set_log_score(double s) { log_score_ = clamp_score(s); }
  void set_governance_score(double s) { governance_score_ = clamp_score(s); }

  // Alert flag setters
  void set_drift_alert(bool alert) { drift_alert_ = alert; }
  void set_dataset_skew_alert(bool alert) { dataset_skew_alert_ = alert; }
  void set_storage_warning(bool alert) { storage_warning_ = alert; }

  void record_containment_event() {
    containment_timestamps_.push_back(static_cast<double>(std::time(nullptr)));
  }

  // -------------------------------------------------------------------
  // Core: Compute Unified Score & Evaluate Autonomy
  // -------------------------------------------------------------------

  double compute_overall_score() {
    double prev = overall_score_;
    IntegrityStatus prev_status = current_status_;

    overall_score_ =
        clamp_score(ml_score_ * W_ML + dataset_score_ * W_DATASET +
                    storage_score_ * W_STORAGE + resource_score_ * W_RESOURCE +
                    log_score_ * W_LOG + governance_score_ * W_GOVERN);

    current_status_ = score_to_status(overall_score_);

    // Log if status changed
    if (current_status_ != prev_status) {
      log_transition(prev, overall_score_, prev_status, current_status_,
                     current_mode_, "Integrity status transition");
    }

    return overall_score_;
  }

  AutonomyCondition evaluate_autonomy() {
    compute_overall_score();

    AutonomyCondition cond;
    cond.overall_above_threshold = (overall_score_ > SHADOW_THRESHOLD);
    cond.no_containment_24h = !has_containment_in_last_24h();
    cond.no_drift_anomalies = !drift_alert_;
    cond.no_dataset_skew = !dataset_skew_alert_;
    cond.no_storage_warnings = !storage_warning_;

    // ALL conditions must pass
    cond.shadow_allowed = cond.overall_above_threshold &&
                          cond.no_containment_24h && cond.no_drift_anomalies &&
                          cond.no_dataset_skew && cond.no_storage_warnings;

    // Build blocked reasons
    std::string reasons;
    if (!cond.overall_above_threshold)
      reasons += "overall_integrity <= 95;";
    if (!cond.no_containment_24h)
      reasons += "containment_event_in_last_24h;";
    if (!cond.no_drift_anomalies)
      reasons += "drift_anomaly_detected;";
    if (!cond.no_dataset_skew)
      reasons += "dataset_skew_detected;";
    if (!cond.no_storage_warnings)
      reasons += "storage_warning_active;";

    std::strncpy(cond.blocked_reasons, reasons.c_str(), 1023);
    cond.blocked_reasons[1023] = '\0';

    // Enforce mode
    SupervisorMode prev_mode = current_mode_;
    if (cond.shadow_allowed) {
      shadow_allowed_ = true;
      current_mode_ = SupervisorMode::MODE_B_SHADOW;
    } else {
      shadow_allowed_ = false;
      current_mode_ = SupervisorMode::MODE_A_ONLY;
      if (prev_mode != SupervisorMode::MODE_A_ONLY) {
        record_containment_event();
        log_transition(overall_score_, overall_score_, current_status_,
                       current_status_, SupervisorMode::MODE_A_ONLY,
                       "Shadow disabled: autonomy conditions not met");
      }
    }

    return cond;
  }

  // -------------------------------------------------------------------
  // Accessors
  // -------------------------------------------------------------------

  double overall_score() const { return overall_score_; }
  double ml_score() const { return ml_score_; }
  double dataset_score() const { return dataset_score_; }
  double storage_score() const { return storage_score_; }
  double resource_score() const { return resource_score_; }
  double log_score() const { return log_score_; }
  double governance_score() const { return governance_score_; }

  IntegrityStatus current_status() const { return current_status_; }
  SupervisorMode current_mode() const { return current_mode_; }
  bool is_shadow_allowed() const { return shadow_allowed_; }

  int event_count() const { return static_cast<int>(event_log_.size()); }
  const IntegrityEvent &get_event(int idx) const { return event_log_[idx]; }

  SubSystemScore get_subsystem_score(const char *name) const {
    SubSystemScore ss;
    ss.score = 0;
    ss.weight = 0;
    std::strncpy(ss.subsystem, name, 63);
    ss.subsystem[63] = '\0';
    ss.detail[0] = '\0';

    if (std::strcmp(name, "ml") == 0) {
      ss.score = ml_score_;
      ss.weight = W_ML;
    } else if (std::strcmp(name, "dataset") == 0) {
      ss.score = dataset_score_;
      ss.weight = W_DATASET;
    } else if (std::strcmp(name, "storage") == 0) {
      ss.score = storage_score_;
      ss.weight = W_STORAGE;
    } else if (std::strcmp(name, "resource") == 0) {
      ss.score = resource_score_;
      ss.weight = W_RESOURCE;
    } else if (std::strcmp(name, "log") == 0) {
      ss.score = log_score_;
      ss.weight = W_LOG;
    } else if (std::strcmp(name, "governance") == 0) {
      ss.score = governance_score_;
      ss.weight = W_GOVERN;
    }

    ss.status = score_to_status(ss.score);
    return ss;
  }
};
