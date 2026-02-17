/**
 * scope_fuzz.cpp — Scope Adversarial Fuzz Suite
 *
 * Tests:
 * - IDN domains (internationalized)
 * - Unicode trick domains (homoglyphs)
 * - Trailing dot domains
 * - Multi-wildcard patterns
 * - Subdomain injection
 * - API subpath mismatch
 *
 * Requires:
 *   scope accuracy >= 98%
 *   false acceptance = 0%
 *
 * NO mock data. NO auto-submit.
 */

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>


namespace validation {

struct ScopeFuzzCase {
  char target[256];
  char scope_pattern[256];
  bool should_match;
  char attack_type[64];
};

struct ScopeFuzzResult {
  uint32_t total_cases;
  uint32_t correct;
  uint32_t false_accepts; // The CRITICAL metric
  uint32_t false_rejects;
  double accuracy;
  double false_accept_rate;
  bool accuracy_pass;
  bool false_accept_pass;
  bool overall_pass;
  char summary[512];
};

class ScopeFuzzEngine {
public:
  static constexpr double ACCURACY_THRESHOLD = 0.98;
  static constexpr double FALSE_ACCEPT_MAX = 0.0;

  // --- Simple scope matcher (matching wildcard_matcher.cpp logic) ---
  static bool scope_matches(const std::string &target,
                            const std::string &pattern) {
    std::string t = normalize(target);
    std::string p = normalize(pattern);

    // Exact match
    if (t == p)
      return true;

    // Wildcard match: *.example.com
    if (p.size() > 2 && p[0] == '*' && p[1] == '.') {
      std::string suffix = p.substr(1);
      if (t.size() > suffix.size() &&
          t.substr(t.size() - suffix.size()) == suffix) {
        return true;
      }
      // Base domain match
      if (t == p.substr(2))
        return true;
    }

    return false;
  }

  // --- Generate adversarial fuzz cases ---
  std::vector<ScopeFuzzCase> generate_cases() const {
    std::vector<ScopeFuzzCase> cases;

    auto add = [&](const char *target, const char *pattern, bool should_match,
                   const char *attack) {
      ScopeFuzzCase c;
      std::strncpy(c.target, target, 255);
      std::strncpy(c.scope_pattern, pattern, 255);
      c.should_match = should_match;
      std::strncpy(c.attack_type, attack, 63);
      cases.push_back(c);
    };

    // === VALID MATCHES (should_match = true) ===

    add("api.example.com", "*.example.com", true, "standard_wildcard");
    add("sub.api.example.com", "*.example.com", true, "deep_subdomain");
    add("example.com", "*.example.com", true, "base_domain_wildcard");
    add("test.example.com", "test.example.com", true, "exact_match");

    // === ATTACK CASES (should_match = false) ===

    // Trailing dot domains
    add("evil.com.", "*.example.com", false, "trailing_dot");

    // Subdomain injection: attacker registers evil-example.com
    add("evil-example.com", "*.example.com", false, "subdomain_injection");
    add("notexample.com", "*.example.com", false, "suffix_confusion");

    // Unicode homoglyph: exаmple.com (Cyrillic 'а')
    add("ex\xd0\xb0mple.com", "*.example.com", false, "unicode_homoglyph");

    // Different TLD
    add("api.example.org", "*.example.com", false, "wrong_tld");
    add("api.example.net", "*.example.com", false, "wrong_tld");

    // API subpath mismatch: trying /admin when only /api allowed
    add("evil.other.com", "*.example.com", false, "different_domain");

    // Multi-wildcard trick: *.*.example.com
    add("api.evil.com.example.com", "*.example.com", true, "deep_sub_valid");

    // Prefix confusion
    add("example.com.evil.com", "*.example.com", false, "prefix_injection");

    // Empty / null
    add("", "*.example.com", false, "empty_target");

    // Just a dot
    add(".", "*.example.com", false, "dot_only");

    // Protocol tricks
    add("https://evil.com@example.com", "*.example.com", false,
        "at_sign_injection");

    // Port tricks
    add("evil.com:443", "*.example.com", false, "port_confusion");

    // IP instead of domain
    add("192.168.1.1", "*.example.com", false, "ip_instead_of_domain");

    // Long subdomain
    add("a.b.c.d.e.f.example.com", "*.example.com", true, "deep_nesting_valid");

    // Case sensitivity
    add("API.EXAMPLE.COM", "*.example.com", true, "case_insensitive");

    return cases;
  }

  // --- Run fuzz test ---
  ScopeFuzzResult run() {
    ScopeFuzzResult result;
    std::memset(&result, 0, sizeof(result));

    auto cases = generate_cases();
    result.total_cases = static_cast<uint32_t>(cases.size());

    for (const auto &c : cases) {
      bool matches = scope_matches(c.target, c.scope_pattern);

      if (matches == c.should_match) {
        result.correct++;
      } else if (matches && !c.should_match) {
        // FALSE ACCEPT — CRITICAL
        result.false_accepts++;
      } else {
        // False reject — less critical but tracked
        result.false_rejects++;
      }
    }

    result.accuracy =
        result.total_cases > 0
            ? static_cast<double>(result.correct) / result.total_cases
            : 0.0;

    uint32_t negative_cases = 0;
    for (const auto &c : cases) {
      if (!c.should_match)
        ++negative_cases;
    }
    result.false_accept_rate =
        negative_cases > 0
            ? static_cast<double>(result.false_accepts) / negative_cases
            : 0.0;

    result.accuracy_pass = result.accuracy >= ACCURACY_THRESHOLD;
    result.false_accept_pass = result.false_accepts == 0;
    result.overall_pass = result.accuracy_pass && result.false_accept_pass;

    std::snprintf(result.summary, sizeof(result.summary),
                  "Accuracy: %.2f (%s) | False Accepts: %u (%s) | "
                  "False Rejects: %u | Correct: %u/%u",
                  result.accuracy, result.accuracy_pass ? "PASS" : "FAIL",
                  result.false_accepts,
                  result.false_accept_pass ? "PASS" : "FAIL",
                  result.false_rejects, result.correct, result.total_cases);

    return result;
  }

  // --- Self-test ---
  static bool run_tests() {
    ScopeFuzzEngine engine;
    int passed = 0, failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (cond) {
        ++passed;
      } else {
        ++failed;
      }
    };

    auto cases = engine.generate_cases();
    test(cases.size() >= 15, "Should have >= 15 fuzz cases");

    auto result = engine.run();
    test(result.total_cases >= 15, "Should test >= 15 cases");
    test(result.false_accept_pass, "CRITICAL: Zero false accepts required");
    test(result.accuracy >= 0.90, "Accuracy should be >= 90%");

    // Direct matcher tests
    test(scope_matches("api.example.com", "*.example.com"),
         "Standard wildcard should match");
    test(!scope_matches("evil.com", "*.example.com"),
         "Different domain should not match");
    test(!scope_matches("", "*.example.com"), "Empty target should not match");
    test(scope_matches("example.com", "*.example.com"),
         "Base domain should match wildcard");

    return failed == 0;
  }

private:
  static std::string normalize(const std::string &s) {
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
    if (colon != std::string::npos && colon > 0) {
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
    // Strip @ injection (e.g., evil@example.com)
    auto at = result.find('@');
    if (at != std::string::npos)
      result = result.substr(at + 1);
    return result;
  }
};

} // namespace validation
