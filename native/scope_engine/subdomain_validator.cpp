/**
 * subdomain_validator.cpp — Subdomain & Out-of-Scope Detection
 *
 * Validates targets against parsed scope.
 * Detects out-of-scope APIs.
 * Blocks report generation if non-compliant.
 *
 * NO mock data. NO auto-submit. NO authority unlock.
 */

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>


namespace scope_engine {

enum class ComplianceStatus : uint8_t {
  IN_SCOPE = 0,
  OUT_OF_SCOPE = 1,
  EXCLUDED = 2, // Explicitly excluded
  UNKNOWN = 3,  // Cannot determine
  BLOCKED = 4   // Report generation blocked
};

struct ComplianceResult {
  ComplianceStatus status;
  bool report_allowed;
  char target[256];
  char matched_rule[256];
  char explanation[512];
  double compliance_confidence; // 0-1
};

// --- Scope Rule ---
struct ScopeRule {
  char pattern[256];
  bool is_exclusion;
  bool is_wildcard;
  uint16_t port;
};

// --- Subdomain Validator ---
class SubdomainValidator {
private:
  std::vector<ScopeRule> in_scope_rules_;
  std::vector<ScopeRule> exclusion_rules_;
  uint64_t total_checked_;
  uint64_t total_blocked_;
  uint64_t total_allowed_;

public:
  SubdomainValidator()
      : total_checked_(0), total_blocked_(0), total_allowed_(0) {}

  // --- Add scope rules ---
  void add_in_scope(const std::string &pattern, bool is_wildcard,
                    uint16_t port = 0) {
    ScopeRule rule;
    std::memset(&rule, 0, sizeof(rule));
    std::strncpy(rule.pattern, pattern.c_str(), sizeof(rule.pattern) - 1);
    rule.is_exclusion = false;
    rule.is_wildcard = is_wildcard;
    rule.port = port;
    in_scope_rules_.push_back(rule);
  }

  void add_exclusion(const std::string &pattern, bool is_wildcard,
                     uint16_t port = 0) {
    ScopeRule rule;
    std::memset(&rule, 0, sizeof(rule));
    std::strncpy(rule.pattern, pattern.c_str(), sizeof(rule.pattern) - 1);
    rule.is_exclusion = true;
    rule.is_wildcard = is_wildcard;
    rule.port = port;
    exclusion_rules_.push_back(rule);
  }

  // --- Validate target against scope ---
  ComplianceResult validate(const std::string &target) {
    ComplianceResult result;
    std::memset(&result, 0, sizeof(result));
    std::strncpy(result.target, target.c_str(), sizeof(result.target) - 1);
    total_checked_++;

    std::string t = normalize(target);

    // Check exclusions FIRST (exclusions take priority)
    for (const auto &rule : exclusion_rules_) {
      if (matches(t, rule)) {
        result.status = ComplianceStatus::EXCLUDED;
        result.report_allowed = false;
        result.compliance_confidence = 0.95;
        std::strncpy(result.matched_rule, rule.pattern,
                     sizeof(result.matched_rule) - 1);
        std::snprintf(result.explanation, sizeof(result.explanation),
                      "BLOCKED: Target '%s' matches exclusion rule '%s'. "
                      "Report generation is prohibited.",
                      target.c_str(), rule.pattern);
        total_blocked_++;
        return result;
      }
    }

    // Check in-scope rules
    for (const auto &rule : in_scope_rules_) {
      if (matches(t, rule)) {
        result.status = ComplianceStatus::IN_SCOPE;
        result.report_allowed = true;
        result.compliance_confidence = 0.95;
        std::strncpy(result.matched_rule, rule.pattern,
                     sizeof(result.matched_rule) - 1);
        std::snprintf(result.explanation, sizeof(result.explanation),
                      "ALLOWED: Target '%s' matches in-scope rule '%s'.",
                      target.c_str(), rule.pattern);
        total_allowed_++;
        return result;
      }
    }

    // No match found
    result.status = ComplianceStatus::OUT_OF_SCOPE;
    result.report_allowed = false;
    result.compliance_confidence = 0.80;
    std::snprintf(result.explanation, sizeof(result.explanation),
                  "BLOCKED: Target '%s' does not match any in-scope rule. "
                  "Assumed out-of-scope. Report generation prohibited.",
                  target.c_str());
    total_blocked_++;
    return result;
  }

  // --- Batch validate ---
  std::vector<ComplianceResult>
  validate_batch(const std::vector<std::string> &targets) {
    std::vector<ComplianceResult> results;
    results.reserve(targets.size());
    for (const auto &t : targets) {
      results.push_back(validate(t));
    }
    return results;
  }

  // --- Stats ---
  uint64_t get_total() const { return total_checked_; }
  uint64_t get_blocked() const { return total_blocked_; }
  uint64_t get_allowed() const { return total_allowed_; }
  double block_rate() const {
    if (total_checked_ == 0)
      return 0.0;
    return static_cast<double>(total_blocked_) / total_checked_;
  }

  // --- Self-test ---
  static bool run_tests() {
    SubdomainValidator validator;
    int passed = 0, failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (cond) {
        ++passed;
      } else {
        ++failed;
      }
    };

    // Setup scope
    validator.add_in_scope("*.example.com", true);
    validator.add_in_scope("api.target.io", false);
    validator.add_exclusion("staging.example.com", false);
    validator.add_exclusion("*.internal.example.com", true);

    // Test 1: In-scope subdomain
    auto r1 = validator.validate("app.example.com");
    test(r1.status == ComplianceStatus::IN_SCOPE,
         "app.example.com should be in scope");
    test(r1.report_allowed, "Should allow report");

    // Test 2: Excluded subdomain
    auto r2 = validator.validate("staging.example.com");
    test(r2.status == ComplianceStatus::EXCLUDED,
         "staging.example.com should be excluded");
    test(!r2.report_allowed, "Should block report");

    // Test 3: Excluded wildcard
    auto r3 = validator.validate("db.internal.example.com");
    test(r3.status == ComplianceStatus::EXCLUDED,
         "*.internal should be excluded");

    // Test 4: Exact match
    auto r4 = validator.validate("api.target.io");
    test(r4.status == ComplianceStatus::IN_SCOPE,
         "api.target.io should match exactly");

    // Test 5: Out of scope
    auto r5 = validator.validate("api.other.com");
    test(r5.status == ComplianceStatus::OUT_OF_SCOPE,
         "api.other.com should be out of scope");
    test(!r5.report_allowed, "Should block OOS report");

    // Test 6: Stats
    test(validator.get_total() == 5, "Should have 5 checks");
    test(validator.get_blocked() >= 3, "Should have >=3 blocked");

    return failed == 0;
  }

private:
  std::string normalize(const std::string &s) const {
    std::string result = s;
    // Strip protocol
    if (result.substr(0, 8) == "https://")
      result = result.substr(8);
    if (result.substr(0, 7) == "http://")
      result = result.substr(7);
    // Strip path
    auto slash = result.find('/');
    if (slash != std::string::npos)
      result = result.substr(0, slash);
    // Strip port
    auto colon = result.rfind(':');
    if (colon != std::string::npos) {
      std::string after = result.substr(colon + 1);
      bool all_digits = !after.empty();
      for (char c : after) {
        if (!std::isdigit(static_cast<unsigned char>(c))) {
          all_digits = false;
          break;
        }
      }
      if (all_digits)
        result = result.substr(0, colon);
    }
    // Lowercase
    for (char &c : result) {
      c = std::tolower(static_cast<unsigned char>(c));
    }
    // Strip trailing dot
    if (!result.empty() && result.back() == '.')
      result.pop_back();
    return result;
  }

  bool matches(const std::string &target, const ScopeRule &rule) const {
    std::string p = normalize(std::string(rule.pattern));

    if (rule.is_wildcard && p.size() > 2 && p[0] == '*' && p[1] == '.') {
      std::string suffix = p.substr(1);
      // Subdomain match
      if (target.size() > suffix.size() &&
          target.substr(target.size() - suffix.size()) == suffix) {
        return true;
      }
      // Base domain match
      if (target == p.substr(2))
        return true;
    }

    // Exact match
    return target == p;
  }
};

} // namespace scope_engine
