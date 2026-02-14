/*
 * dom_diff_tracker.cpp — DOM State Change Tracker
 *
 * Tracks DOM mutations between hunting steps.
 * Records element changes, attribute mutations, text modifications.
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int MAX_DIFFS = 10000;
static constexpr int MAX_SELECTOR = 256;
static constexpr int MAX_VALUE = 1024;

// =========================================================================
// TYPES
// =========================================================================

enum class DiffType {
  ELEMENT_ADDED,
  ELEMENT_REMOVED,
  ATTRIBUTE_CHANGED,
  TEXT_CHANGED,
  CLASS_ADDED,
  CLASS_REMOVED,
  STYLE_CHANGED,
  INPUT_VALUE_CHANGED,
  FORM_SUBMITTED
};

struct DomDiff {
  int sequence;
  int parent_step; // Links to ActionRecorder step
  time_t timestamp;
  DiffType type;
  char selector[MAX_SELECTOR];
  char attribute[MAX_SELECTOR];
  char old_value[MAX_VALUE];
  char new_value[MAX_VALUE];
};

// =========================================================================
// DOM DIFF TRACKER
// =========================================================================

class DomDiffTracker {
private:
  DomDiff diffs_[MAX_DIFFS];
  int diff_count_;

public:
  DomDiffTracker() : diff_count_(0) { std::memset(diffs_, 0, sizeof(diffs_)); }

  bool record_diff(int parent_step, DiffType type, const char *selector,
                   const char *attribute, const char *old_value,
                   const char *new_value) {
    if (diff_count_ >= MAX_DIFFS)
      return false;

    DomDiff &d = diffs_[diff_count_];
    d.sequence = diff_count_;
    d.parent_step = parent_step;
    d.timestamp = std::time(nullptr);
    d.type = type;

    std::strncpy(d.selector, selector ? selector : "", MAX_SELECTOR - 1);
    std::strncpy(d.attribute, attribute ? attribute : "", MAX_SELECTOR - 1);
    std::strncpy(d.old_value, old_value ? old_value : "", MAX_VALUE - 1);
    std::strncpy(d.new_value, new_value ? new_value : "", MAX_VALUE - 1);

    diff_count_++;
    return true;
  }

  int diff_count() const { return diff_count_; }

  const DomDiff *get_diff(int i) const {
    return (i >= 0 && i < diff_count_) ? &diffs_[i] : nullptr;
  }

  // Get all diffs for a specific step
  int get_diffs_for_step(int step, const DomDiff **out, int max_out) const {
    int count = 0;
    for (int i = 0; i < diff_count_ && count < max_out; i++) {
      if (diffs_[i].parent_step == step)
        out[count++] = &diffs_[i];
    }
    return count;
  }

  int count_by_type(DiffType type) const {
    int c = 0;
    for (int i = 0; i < diff_count_; i++)
      if (diffs_[i].type == type)
        c++;
    return c;
  }

  // Guards
  static bool can_modify_diff() { return false; }
  static bool can_delete_diff() { return false; }
};
