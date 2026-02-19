/**
 * cross_device_validator.cpp — Cross-Device Determinism Validation
 *
 * Rules:
 *   - Compare exported model hash across N devices
 *   - Validate identical precision ± 0.0001
 *   - Validate identical ECE ± 0.0001
 *   - Reject distributed merge on ANY mismatch
 *   - Enforce fixed seed = 42 across all nodes
 *   - Log rejection reason for audit
 *   - No auto-approval — mismatch always blocks
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace determinism {

static constexpr uint32_t MAX_DEVICES = 16;
static constexpr uint64_t REQUIRED_SEED = 42;
static constexpr double PRECISION_TOLERANCE = 0.0001;
static constexpr double ECE_TOLERANCE = 0.0001;

struct DeviceReport {
  char device_id[64];
  char model_hash[128];
  double precision;
  double ece;
  uint64_t seed;
  uint32_t epoch;
  uint32_t field_id;
  uint64_t timestamp_ms;
};

enum class ValidationResult : uint8_t {
  PASS = 0,
  HASH_MISMATCH = 1,
  PRECISION_MISMATCH = 2,
  ECE_MISMATCH = 3,
  SEED_MISMATCH = 4,
  EPOCH_MISMATCH = 5,
  FIELD_MISMATCH = 6,
  INSUFFICIENT_DEVICES = 7
};

struct CrossDeviceState {
  ValidationResult result;
  bool merge_allowed;
  uint32_t device_count;
  uint32_t mismatches;
  char rejection_reason[512];
  // Reference values (from device 0)
  char reference_hash[128];
  double reference_precision;
  double reference_ece;
};

class CrossDeviceValidator {
public:
  CrossDeviceValidator() : count_(0) {
    std::memset(&state_, 0, sizeof(state_));
    std::memset(reports_, 0, sizeof(reports_));
  }

  bool add_device_report(const DeviceReport &report) {
    if (count_ >= MAX_DEVICES)
      return false;
    reports_[count_++] = report;
    return true;
  }

  // ---- Run validation across all added devices ----
  CrossDeviceState validate() {
    std::memset(&state_, 0, sizeof(state_));
    state_.device_count = count_;

    if (count_ < 2) {
      state_.result = ValidationResult::INSUFFICIENT_DEVICES;
      state_.merge_allowed = false;
      std::snprintf(state_.rejection_reason, sizeof(state_.rejection_reason),
                    "INSUFFICIENT: need ≥ 2 devices, got %u", count_);
      return state_;
    }

    // Use device 0 as reference
    const auto &ref = reports_[0];
    std::strncpy(state_.reference_hash, ref.model_hash, 127);
    state_.reference_precision = ref.precision;
    state_.reference_ece = ref.ece;

    uint32_t mismatches = 0;

    for (uint32_t i = 0; i < count_; i++) {
      const auto &dev = reports_[i];

      // 1. Seed must be REQUIRED_SEED
      if (dev.seed != REQUIRED_SEED) {
        mismatches++;
        state_.result = ValidationResult::SEED_MISMATCH;
        std::snprintf(state_.rejection_reason, sizeof(state_.rejection_reason),
                      "SEED_MISMATCH: device '%s' seed=%llu expected=%llu",
                      dev.device_id, (unsigned long long)dev.seed,
                      (unsigned long long)REQUIRED_SEED);
        break;
      }

      // 2. Field must match
      if (dev.field_id != ref.field_id) {
        mismatches++;
        state_.result = ValidationResult::FIELD_MISMATCH;
        std::snprintf(state_.rejection_reason, sizeof(state_.rejection_reason),
                      "FIELD_MISMATCH: device '%s' field=%u vs ref field=%u",
                      dev.device_id, dev.field_id, ref.field_id);
        break;
      }

      // 3. Epoch must match
      if (dev.epoch != ref.epoch) {
        mismatches++;
        state_.result = ValidationResult::EPOCH_MISMATCH;
        std::snprintf(state_.rejection_reason, sizeof(state_.rejection_reason),
                      "EPOCH_MISMATCH: device '%s' epoch=%u vs ref epoch=%u",
                      dev.device_id, dev.epoch, ref.epoch);
        break;
      }

      // Compare against reference (skip ref against itself)
      if (i == 0)
        continue;

      // 4. Hash must be identical
      if (std::strcmp(dev.model_hash, ref.model_hash) != 0) {
        mismatches++;
        state_.result = ValidationResult::HASH_MISMATCH;
        std::snprintf(
            state_.rejection_reason, sizeof(state_.rejection_reason),
            "HASH_MISMATCH: device '%s' hash='%.32s...' vs ref='%.32s...'",
            dev.device_id, dev.model_hash, ref.model_hash);
        break;
      }

      // 5. Precision within tolerance
      if (std::fabs(dev.precision - ref.precision) > PRECISION_TOLERANCE) {
        mismatches++;
        state_.result = ValidationResult::PRECISION_MISMATCH;
        std::snprintf(state_.rejection_reason, sizeof(state_.rejection_reason),
                      "PRECISION_MISMATCH: device '%s' prec=%.6f vs "
                      "ref=%.6f (delta=%.6f > %.6f)",
                      dev.device_id, dev.precision, ref.precision,
                      std::fabs(dev.precision - ref.precision),
                      PRECISION_TOLERANCE);
        break;
      }

      // 6. ECE within tolerance
      if (std::fabs(dev.ece - ref.ece) > ECE_TOLERANCE) {
        mismatches++;
        state_.result = ValidationResult::ECE_MISMATCH;
        std::snprintf(state_.rejection_reason, sizeof(state_.rejection_reason),
                      "ECE_MISMATCH: device '%s' ece=%.6f vs ref=%.6f "
                      "(delta=%.6f > %.6f)",
                      dev.device_id, dev.ece, ref.ece,
                      std::fabs(dev.ece - ref.ece), ECE_TOLERANCE);
        break;
      }
    }

    state_.mismatches = mismatches;

    if (mismatches == 0) {
      state_.result = ValidationResult::PASS;
      state_.merge_allowed = true;
      std::snprintf(
          state_.rejection_reason, sizeof(state_.rejection_reason),
          "PASS: %u devices deterministic (hash=%s prec=%.6f ece=%.6f)", count_,
          ref.model_hash, ref.precision, ref.ece);
    } else {
      state_.merge_allowed = false;
    }

    return state_;
  }

  void reset() {
    count_ = 0;
    std::memset(&state_, 0, sizeof(state_));
    std::memset(reports_, 0, sizeof(reports_));
  }

  const CrossDeviceState &state() const { return state_; }

  // ---- Self-test ----
  static bool run_tests() {
    int failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (!cond) {
        std::printf("  FAIL: %s\n", name);
        failed++;
      }
    };

    // Helper to create a device report
    auto make_report = [](const char *id, const char *hash, double prec,
                          double ece, uint64_t seed, uint32_t epoch,
                          uint32_t field) -> DeviceReport {
      DeviceReport r;
      std::memset(&r, 0, sizeof(r));
      std::strncpy(r.device_id, id, 63);
      std::strncpy(r.model_hash, hash, 127);
      r.precision = prec;
      r.ece = ece;
      r.seed = seed;
      r.epoch = epoch;
      r.field_id = field;
      r.timestamp_ms = 0;
      return r;
    };

    // Test 1: Two identical devices → PASS
    {
      CrossDeviceValidator v;
      v.add_device_report(
          make_report("gpu-0", "abc123hash", 0.960000, 0.015000, 42, 10, 0));
      v.add_device_report(
          make_report("gpu-1", "abc123hash", 0.960000, 0.015000, 42, 10, 0));
      auto s = v.validate();
      test(s.result == ValidationResult::PASS, "identical devices → PASS");
      test(s.merge_allowed == true, "merge allowed with identical devices");
      test(s.mismatches == 0, "zero mismatches");
    }

    // Test 2: Hash mismatch → REJECT
    {
      CrossDeviceValidator v;
      v.add_device_report(
          make_report("gpu-0", "hashAAAA", 0.96, 0.015, 42, 10, 0));
      v.add_device_report(
          make_report("gpu-1", "hashBBBB", 0.96, 0.015, 42, 10, 0));
      auto s = v.validate();
      test(s.result == ValidationResult::HASH_MISMATCH, "hash mismatch");
      test(s.merge_allowed == false, "merge blocked on hash mismatch");
    }

    // Test 3: Precision just over tolerance → REJECT
    {
      CrossDeviceValidator v;
      v.add_device_report(
          make_report("gpu-0", "hash1", 0.960000, 0.015, 42, 10, 0));
      v.add_device_report(
          make_report("gpu-1", "hash1", 0.960200, 0.015, 42, 10, 0));
      auto s = v.validate();
      // delta=0.0002 > 0.0001
      test(s.result == ValidationResult::PRECISION_MISMATCH,
           "precision over tolerance → reject");
      test(s.merge_allowed == false, "merge blocked on precision mismatch");
    }

    // Test 4: ECE within tolerance → PASS
    {
      CrossDeviceValidator v;
      v.add_device_report(
          make_report("gpu-0", "hash1", 0.96, 0.015000, 42, 10, 0));
      v.add_device_report(
          make_report("gpu-1", "hash1", 0.96, 0.015050, 42, 10, 0));
      auto s = v.validate();
      // delta=0.00005 < 0.0001 → pass
      test(s.result == ValidationResult::PASS, "ECE within tolerance → PASS");
    }

    // Test 5: Wrong seed → REJECT
    {
      CrossDeviceValidator v;
      v.add_device_report(
          make_report("gpu-0", "hash1", 0.96, 0.015, 42, 10, 0));
      v.add_device_report(
          make_report("gpu-1", "hash1", 0.96, 0.015, 99, 10, 0));
      auto s = v.validate();
      test(s.result == ValidationResult::SEED_MISMATCH, "wrong seed → reject");
      test(s.merge_allowed == false, "merge blocked on seed mismatch");
    }

    // Test 6: Field mismatch → REJECT
    {
      CrossDeviceValidator v;
      v.add_device_report(
          make_report("gpu-0", "hash1", 0.96, 0.015, 42, 10, 0));
      v.add_device_report(
          make_report("gpu-1", "hash1", 0.96, 0.015, 42, 10, 1));
      auto s = v.validate();
      test(s.result == ValidationResult::FIELD_MISMATCH,
           "field mismatch → reject");
    }

    // Test 7: Single device → INSUFFICIENT
    {
      CrossDeviceValidator v;
      v.add_device_report(
          make_report("gpu-0", "hash1", 0.96, 0.015, 42, 10, 0));
      auto s = v.validate();
      test(s.result == ValidationResult::INSUFFICIENT_DEVICES,
           "single device → insufficient");
      test(s.merge_allowed == false, "merge blocked with 1 device");
    }

    // Test 8: Three devices, all matching → PASS
    {
      CrossDeviceValidator v;
      v.add_device_report(make_report("gpu-0", "xyz", 0.955, 0.018, 42, 5, 2));
      v.add_device_report(make_report("gpu-1", "xyz", 0.955, 0.018, 42, 5, 2));
      v.add_device_report(make_report("gpu-2", "xyz", 0.955, 0.018, 42, 5, 2));
      auto s = v.validate();
      test(s.result == ValidationResult::PASS, "3 devices all matching → PASS");
      test(s.device_count == 3, "device count is 3");
    }

    // Test 9: Epoch mismatch → REJECT
    {
      CrossDeviceValidator v;
      v.add_device_report(
          make_report("gpu-0", "hash1", 0.96, 0.015, 42, 10, 0));
      v.add_device_report(
          make_report("gpu-1", "hash1", 0.96, 0.015, 42, 11, 0));
      auto s = v.validate();
      test(s.result == ValidationResult::EPOCH_MISMATCH,
           "epoch mismatch → reject");
    }

    return failed == 0;
  }

private:
  DeviceReport reports_[MAX_DEVICES];
  uint32_t count_;
  CrossDeviceState state_;
};

} // namespace determinism
