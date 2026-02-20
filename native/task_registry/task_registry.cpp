/**
 * Task Registry — Duplicate Task Collision Prevention (Phase 9)
 *
 * Provides an atomic locking mechanism for assigning targets to devices.
 * Ensures that no two devices can be assigned the same target ID
 * simultaneously, preventing duplicated work and wasted compute cycles.
 *
 * Features:
 * - In-memory locks bound to target_id
 * - Records device_id and assignment timestamp
 * - Tracks active locks and total assignments
 */

#include <ctime>
#include <mutex>
#include <string>
#include <unordered_map>


struct TaskLock {
  std::string device_id;
  std::time_t assigned_at;
};

class TaskRegistry {
private:
  std::unordered_map<std::string, TaskLock> active_locks_;
  std::mutex registry_mutex_;
  size_t total_assignments_;

public:
  TaskRegistry() : total_assignments_(0) {}

  // Attempts to lock a target for a specific device.
  // Returns true if successfully locked, false if already assigned to another
  // device.
  bool assign_target(const std::string &target_id,
                     const std::string &device_id) {
    std::lock_guard<std::mutex> lock(registry_mutex_);

    auto it = active_locks_.find(target_id);
    if (it != active_locks_.end()) {
      // Already locked. Allow re-assignment if it's the SAME device
      // (idempotent).
      if (it->second.device_id == device_id) {
        return true;
      }
      return false; // Collision prevented
    }

    // Create new lock
    TaskLock new_lock;
    new_lock.device_id = device_id;
    new_lock.assigned_at = std::time(nullptr);

    active_locks_[target_id] = new_lock;
    total_assignments_++;
    return true;
  }

  // Releases a lock when the task is completed or aborted.
  // Only the device that holds the lock can release it.
  bool release_target(const std::string &target_id,
                      const std::string &device_id) {
    std::lock_guard<std::mutex> lock(registry_mutex_);

    auto it = active_locks_.find(target_id);
    if (it != active_locks_.end() && it->second.device_id == device_id) {
      active_locks_.erase(it);
      return true;
    }
    return false;
  }

  // Check if a target is currently locked
  bool is_locked(const std::string &target_id) {
    std::lock_guard<std::mutex> lock(registry_mutex_);
    return active_locks_.find(target_id) != active_locks_.end();
  }

  // Get the device ID holding a lock (returns empty string if unlocked)
  std::string get_lock_owner(const std::string &target_id) {
    std::lock_guard<std::mutex> lock(registry_mutex_);
    auto it = active_locks_.find(target_id);
    if (it != active_locks_.end()) {
      return it->second.device_id;
    }
    return "";
  }

  size_t get_active_lock_count() {
    std::lock_guard<std::mutex> lock(registry_mutex_);
    return active_locks_.size();
  }

  size_t get_total_assignments() {
    std::lock_guard<std::mutex> lock(registry_mutex_);
    return total_assignments_;
  }

  // Clear all locks (reset)
  void reset() {
    std::lock_guard<std::mutex> lock(registry_mutex_);
    active_locks_.clear();
  }
};

// C API exported for Python/FFI

extern "C" {

TaskRegistry *task_registry_create() { return new TaskRegistry(); }

void task_registry_destroy(TaskRegistry *registry) { delete registry; }

bool task_registry_assign(TaskRegistry *registry, const char *target_id,
                          const char *device_id) {
  if (!registry || !target_id || !device_id)
    return false;
  return registry->assign_target(target_id, device_id);
}

bool task_registry_release(TaskRegistry *registry, const char *target_id,
                           const char *device_id) {
  if (!registry || !target_id || !device_id)
    return false;
  return registry->release_target(target_id, device_id);
}

bool task_registry_is_locked(TaskRegistry *registry, const char *target_id) {
  if (!registry || !target_id)
    return false;
  return registry->is_locked(target_id);
}

} // extern "C"
