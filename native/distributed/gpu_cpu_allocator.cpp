/**
 * gpu_cpu_allocator.cpp — GPU/CPU Role Allocator
 *
 * Assigns specific roles to each hardware node:
 *   - RTX 3050:     Primary training (largest CUDA core count)
 *   - RTX 2050 #1:  Drift & adversarial stress testing
 *   - RTX 2050 #2:  Duplicate detection model
 *   - Mac M1:       Calibration + merge validation
 *   - CPU nodes:    Regression & fuzz testing
 *
 * No mid-training merges. Merge only after field certification.
 */

#include <cstdint>
#include <cstdio>
#include <cstring>


namespace distributed {

// =========================================================================
// NODE ROLE
// =========================================================================

enum class NodeRole : uint8_t {
  PRIMARY_TRAINING = 0,
  DRIFT_ADVERSARIAL = 1,
  DUPLICATE_DETECTION = 2,
  CALIBRATION_MERGE = 3,
  REGRESSION_FUZZ = 4,
  UNASSIGNED = 5
};

static const char *role_name(NodeRole r) {
  switch (r) {
  case NodeRole::PRIMARY_TRAINING:
    return "PRIMARY_TRAINING";
  case NodeRole::DRIFT_ADVERSARIAL:
    return "DRIFT_ADVERSARIAL";
  case NodeRole::DUPLICATE_DETECTION:
    return "DUPLICATE_DETECTION";
  case NodeRole::CALIBRATION_MERGE:
    return "CALIBRATION_MERGE";
  case NodeRole::REGRESSION_FUZZ:
    return "REGRESSION_FUZZ";
  default:
    return "UNASSIGNED";
  }
}

// =========================================================================
// NODE ASSIGNMENT
// =========================================================================

struct NodeAssignment {
  uint32_t node_id;
  NodeRole role;
  char device_name[64];
  char field_name[64];    // must match active field
  double utilization_cap; // GPU% cap for this role
  bool assigned;
};

// =========================================================================
// ALLOCATION RESULT
// =========================================================================

struct AllocationResult {
  uint32_t assigned_count;
  uint32_t gpu_nodes;
  uint32_t cpu_nodes;
  bool primary_assigned;
  bool all_roles_filled;
  char summary[256];
};

// =========================================================================
// GPU / CPU ALLOCATOR
// =========================================================================

static constexpr uint32_t MAX_ASSIGNMENTS = 8;

class GpuCpuAllocator {
public:
  static constexpr bool ALLOW_MID_TRAINING_MERGE = false;

  GpuCpuAllocator() : count_(0) {
    std::memset(assignments_, 0, sizeof(assignments_));
  }

  int assign(uint32_t node_id, const char *device, NodeRole role,
             const char *field, double util_cap) {
    if (count_ >= MAX_ASSIGNMENTS)
      return -1;

    // Check for duplicate role (except REGRESSION_FUZZ which can have multiple)
    if (role != NodeRole::REGRESSION_FUZZ) {
      for (uint32_t i = 0; i < count_; ++i) {
        if (assignments_[i].role == role)
          return -2; // role already taken
      }
    }

    NodeAssignment &a = assignments_[count_];
    a.node_id = node_id;
    a.role = role;
    std::strncpy(a.device_name, device, 63);
    a.device_name[63] = '\0';
    std::strncpy(a.field_name, field, 63);
    a.field_name[63] = '\0';
    a.utilization_cap = util_cap;
    a.assigned = true;

    return static_cast<int>(count_++);
  }

  AllocationResult summarize() const {
    AllocationResult r;
    std::memset(&r, 0, sizeof(r));
    r.assigned_count = count_;

    bool roles[6] = {false};
    for (uint32_t i = 0; i < count_; ++i) {
      uint8_t ri = static_cast<uint8_t>(assignments_[i].role);
      if (ri < 5)
        roles[ri] = true;
      // GPU vs CPU heuristic: roles 0-3 are GPU, 4 is CPU
      if (ri <= 3)
        r.gpu_nodes++;
      else
        r.cpu_nodes++;
    }

    r.primary_assigned = roles[0];
    r.all_roles_filled =
        roles[0] && roles[1] && roles[2] && roles[3] && roles[4];

    std::snprintf(
        r.summary, sizeof(r.summary),
        "ALLOCATION: %u nodes (%u GPU + %u CPU), primary=%s, complete=%s",
        count_, r.gpu_nodes, r.cpu_nodes, r.primary_assigned ? "yes" : "no",
        r.all_roles_filled ? "yes" : "no");
    return r;
  }

  const NodeAssignment *assignment(uint32_t idx) const {
    return (idx < count_) ? &assignments_[idx] : nullptr;
  }

private:
  NodeAssignment assignments_[MAX_ASSIGNMENTS];
  uint32_t count_;
};

} // namespace distributed
