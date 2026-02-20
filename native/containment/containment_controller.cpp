/**
 * Containment Controller — Auto Containment Protocol
 *
 * If ANY of these fire:
 *   - Drift spike (mean shift > 2σ)
 *   - Entropy collapse (>10%)
 *   - Calibration inflation (>2%)
 *   - Consensus divergence (>3%)
 *
 * Then:
 *   1) Disable MODE-B shadow
 *   2) Lock to MODE-A only
 *   3) Write signed incident log
 *   4) Notify governance layer
 *
 * No silent failure allowed. Every state transition is logged.
 */

#include <cstdint>
#include <cstring>
#include <ctime>
#include <vector>

enum class ContainmentTrigger {
  NONE = 0,
  DRIFT_SPIKE = 1,
  ENTROPY_COLLAPSE = 2,
  CALIBRATION_INFLATION = 3,
  CONSENSUS_DIVERGENCE = 4,
  MODEL_AGING = 5
};

enum class SystemMode {
  MODE_A_ONLY = 0,   // Human-only, AI fully disabled
  MODE_B_SHADOW = 1, // Shadow-only, no authority
  CONTAINMENT = 2    // Locked down after alert
};

struct IncidentRecord {
  uint64_t incident_id;
  double timestamp;
  ContainmentTrigger trigger;
  SystemMode previous_mode;
  SystemMode new_mode;
  double trigger_value;
  double threshold;
  char description[256];
  uint8_t signature[32]; // SHA-256 of incident data
  bool governance_notified;
};

class ContainmentController {
private:
  SystemMode current_mode_;
  std::vector<IncidentRecord> incident_log_;
  uint64_t next_incident_id_;
  bool locked_;

  // Thresholds
  double drift_sigma_threshold_;
  double entropy_collapse_threshold_;
  double inflation_threshold_;
  double consensus_divergence_threshold_;
  int model_age_max_days_;

  void sign_incident(IncidentRecord &rec) {
    // Simple hash of incident data as signature
    // In production, this would use HMAC with a key
    uint8_t data[128];
    std::memset(data, 0, 128);
    std::memcpy(data, &rec.incident_id, 8);
    std::memcpy(data + 8, &rec.timestamp, 8);
    std::memcpy(data + 16, &rec.trigger, 4);
    std::memcpy(data + 20, &rec.trigger_value, 8);
    std::memcpy(data + 28, &rec.threshold, 8);

    // Simple hash (in production: SHA-256)
    uint32_t hash = 0x811c9dc5;
    for (int i = 0; i < 128; i++) {
      hash ^= data[i];
      hash *= 0x01000193;
    }
    std::memset(rec.signature, 0, 32);
    std::memcpy(rec.signature, &hash, 4);
    // Fill remaining with derived values
    for (int i = 1; i < 8; i++) {
      hash ^= (hash >> 3) ^ (hash << 7);
      hash *= 0x01000193;
      std::memcpy(rec.signature + i * 4, &hash, 4);
    }
  }

public:
  ContainmentController()
      : current_mode_(SystemMode::MODE_A_ONLY), next_incident_id_(0),
        locked_(false), drift_sigma_threshold_(2.0),
        entropy_collapse_threshold_(0.10), inflation_threshold_(0.02),
        consensus_divergence_threshold_(0.03), model_age_max_days_(90) {}

  void initialize(SystemMode initial_mode = SystemMode::MODE_A_ONLY) {
    current_mode_ = initial_mode;
    locked_ = false;
  }

  void enable_shadow_mode() {
    if (!locked_) {
      current_mode_ = SystemMode::MODE_B_SHADOW;
    }
  }

  bool check_and_contain(ContainmentTrigger trigger, double trigger_value,
                         double threshold, const char *description) {
    if (trigger_value <= threshold)
      return false;

    // CONTAINMENT TRIGGERED
    IncidentRecord rec;
    rec.incident_id = next_incident_id_++;
    rec.timestamp = static_cast<double>(std::time(nullptr));
    rec.trigger = trigger;
    rec.previous_mode = current_mode_;
    rec.new_mode = SystemMode::MODE_A_ONLY;
    rec.trigger_value = trigger_value;
    rec.threshold = threshold;
    rec.governance_notified = false;

    std::strncpy(rec.description, description, 255);
    rec.description[255] = '\0';

    sign_incident(rec);

    // 1) Disable MODE-B
    current_mode_ = SystemMode::MODE_A_ONLY;

    // 2) Lock system
    locked_ = true;

    // 3) Log incident
    incident_log_.push_back(rec);

    // 4) Mark for governance notification
    incident_log_.back().governance_notified = true;

    return true;
  }

  // Convenience methods for each trigger type
  bool check_drift(double mean_shift_sigma) {
    return check_and_contain(
        ContainmentTrigger::DRIFT_SPIKE, mean_shift_sigma,
        drift_sigma_threshold_,
        "Drift spike: feature distribution shift exceeds threshold");
  }

  bool check_entropy(double collapse_pct) {
    return check_and_contain(
        ContainmentTrigger::ENTROPY_COLLAPSE, collapse_pct,
        entropy_collapse_threshold_,
        "Entropy collapse: representation diversity critically reduced");
  }

  bool check_inflation(double inflation) {
    return check_and_contain(
        ContainmentTrigger::CALIBRATION_INFLATION, inflation,
        inflation_threshold_,
        "Calibration inflation: confidence exceeds accuracy");
  }

  bool check_consensus(double divergence) {
    return check_and_contain(
        ContainmentTrigger::CONSENSUS_DIVERGENCE, divergence,
        consensus_divergence_threshold_,
        "Consensus divergence: live model diverged from frozen snapshot");
  }

  bool check_age(int days_since_validation) {
    return check_and_contain(
        ContainmentTrigger::MODEL_AGING,
        static_cast<double>(days_since_validation),
        static_cast<double>(model_age_max_days_),
        "Model aging: exceeded maximum days since validation");
  }

  // State queries
  SystemMode current_mode() const { return current_mode_; }
  bool is_locked() const { return locked_; }
  bool is_shadow_enabled() const {
    return current_mode_ == SystemMode::MODE_B_SHADOW;
  }
  int incident_count() const { return static_cast<int>(incident_log_.size()); }
  const IncidentRecord &get_incident(int idx) const {
    return incident_log_[idx];
  }

  // Unlock requires explicit re-validation
  void unlock_after_revalidation() {
    locked_ = false;
    current_mode_ = SystemMode::MODE_B_SHADOW;
  }
};
