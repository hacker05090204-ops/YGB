/**
 * hunt_scope_guard.cpp — Hunt-Mode Scope Validation Gate
 *
 * Rules:
 *   - Every finding must pass scope validation
 *   - No report generated without human approval
 *   - Validate target is in-scope before any processing
 *   - Track scope rejections for drift detection
 *   - NO auto-submission path
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace hunt_guard {

static constexpr uint32_t MAX_SCOPE_ENTRIES = 256;
static constexpr uint32_t MAX_SCOPE_LOG = 500;

enum class ScopeResult : uint8_t {
  IN_SCOPE = 0,
  OUT_OF_SCOPE = 1,
  SCOPE_UNKNOWN = 2,
  BLOCKED_NO_APPROVAL = 3,
  BLOCKED_NO_SCOPE_DATA = 4
};

struct ScopeEntry {
  char domain[128];
  bool wildcard;
  bool active;
};

struct ScopeCheck {
  uint32_t finding_id;
  char target_domain[128];
  bool human_approved;
  uint64_t timestamp_ms;
};

struct ScopeDecision {
  uint32_t finding_id;
  ScopeResult result;
  char reason[256];
};

struct ScopeGuardState {
  uint32_t checks_total;
  uint32_t in_scope;
  uint32_t out_of_scope;
  uint32_t blocked_no_approval;
  uint32_t scope_entries;
  bool guard_active;
};

class HuntScopeGuard {
public:
  HuntScopeGuard() : scope_count_(0), log_count_(0) {
    std::memset(&state_, 0, sizeof(state_));
    std::memset(scope_, 0, sizeof(scope_));
    std::memset(log_, 0, sizeof(log_));
    state_.guard_active = true;
  }

  // ---- Add scope entry ----
  bool add_scope(const char *domain, bool wildcard = false) {
    if (scope_count_ >= MAX_SCOPE_ENTRIES)
      return false;
    auto &s = scope_[scope_count_++];
    std::strncpy(s.domain, domain, sizeof(s.domain) - 1);
    s.wildcard = wildcard;
    s.active = true;
    state_.scope_entries = scope_count_;
    return true;
  }

  // ---- Evaluate scope ----
  ScopeDecision evaluate(const ScopeCheck &check) {
    ScopeDecision d;
    std::memset(&d, 0, sizeof(d));
    d.finding_id = check.finding_id;
    state_.checks_total++;

    // Gate 0: Scope data must exist
    if (scope_count_ == 0) {
      d.result = ScopeResult::BLOCKED_NO_SCOPE_DATA;
      std::snprintf(d.reason, sizeof(d.reason),
                    "BLOCKED: no scope entries defined — cannot validate");
      log_decision(d);
      return d;
    }

    // Gate 1: Human approval required (NO auto-submission)
    if (!check.human_approved) {
      d.result = ScopeResult::BLOCKED_NO_APPROVAL;
      std::snprintf(d.reason, sizeof(d.reason),
                    "BLOCKED: report requires human approval — NO auto-submit");
      state_.blocked_no_approval++;
      log_decision(d);
      return d;
    }

    // Gate 2: Check if target is in scope
    bool found = false;
    for (uint32_t i = 0; i < scope_count_; i++) {
      if (!scope_[i].active)
        continue;

      if (scope_[i].wildcard) {
        // Wildcard: check if target ends with scope domain
        size_t scope_len = std::strlen(scope_[i].domain);
        size_t target_len = std::strlen(check.target_domain);
        if (target_len >= scope_len) {
          const char *suffix = check.target_domain + (target_len - scope_len);
          if (std::strcmp(suffix, scope_[i].domain) == 0) {
            found = true;
            break;
          }
        }
      } else {
        if (std::strcmp(check.target_domain, scope_[i].domain) == 0) {
          found = true;
          break;
        }
      }
    }

    if (found) {
      d.result = ScopeResult::IN_SCOPE;
      std::snprintf(d.reason, sizeof(d.reason),
                    "IN_SCOPE: '%s' matches scope entry", check.target_domain);
      state_.in_scope++;
    } else {
      d.result = ScopeResult::OUT_OF_SCOPE;
      std::snprintf(d.reason, sizeof(d.reason),
                    "OUT_OF_SCOPE: '%s' not in any scope entry",
                    check.target_domain);
      state_.out_of_scope++;
    }

    log_decision(d);
    return d;
  }

  const ScopeGuardState &state() const { return state_; }

  void reset() {
    scope_count_ = 0;
    log_count_ = 0;
    std::memset(&state_, 0, sizeof(state_));
    std::memset(scope_, 0, sizeof(scope_));
    std::memset(log_, 0, sizeof(log_));
    state_.guard_active = true;
  }

  // ---- Self-test ----
  static bool run_tests() {
    HuntScopeGuard guard;
    int failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (!cond) {
        std::printf("  FAIL: %s\n", name);
        failed++;
      }
    };

    // No scope → blocked
    ScopeCheck c0 = {0, "example.com", true, 0};
    auto d0 = guard.evaluate(c0);
    test(d0.result == ScopeResult::BLOCKED_NO_SCOPE_DATA, "no scope = blocked");

    // Add scope
    guard.add_scope("example.com");
    guard.add_scope(".target.io", true);

    // In scope → pass
    ScopeCheck c1 = {1, "example.com", true, 1000};
    auto d1 = guard.evaluate(c1);
    test(d1.result == ScopeResult::IN_SCOPE, "exact match in scope");

    // Wildcard match
    ScopeCheck c2 = {2, "api.target.io", true, 2000};
    auto d2 = guard.evaluate(c2);
    test(d2.result == ScopeResult::IN_SCOPE, "wildcard match in scope");

    // Out of scope
    ScopeCheck c3 = {3, "evil.com", true, 3000};
    auto d3 = guard.evaluate(c3);
    test(d3.result == ScopeResult::OUT_OF_SCOPE, "out of scope blocked");

    // No approval → blocked
    ScopeCheck c4 = {4, "example.com", false, 4000};
    auto d4 = guard.evaluate(c4);
    test(d4.result == ScopeResult::BLOCKED_NO_APPROVAL, "no approval blocked");

    test(guard.state().checks_total == 5, "5 total checks");
    test(guard.state().in_scope == 2, "2 in scope");
    test(guard.state().out_of_scope == 1, "1 out of scope");

    return failed == 0;
  }

private:
  void log_decision(const ScopeDecision &d) {
    if (log_count_ < MAX_SCOPE_LOG) {
      log_[log_count_++] = d;
    }
  }

  ScopeEntry scope_[MAX_SCOPE_ENTRIES];
  uint32_t scope_count_;
  ScopeDecision log_[MAX_SCOPE_LOG];
  uint32_t log_count_;
  ScopeGuardState state_;
};

} // namespace hunt_guard
