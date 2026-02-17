/**
 * wildcard_matcher.cpp — Wildcard Domain & Path Matcher
 *
 * Matches targets against *.domain.com, port ranges, path prefixes.
 * Used for scope compliance enforcement.
 *
 * NO mock data. NO auto-submit. NO authority unlock.
 */

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>


namespace scope_engine {

struct MatchResult {
  bool matches;
  bool is_wildcard_match;
  bool is_exact_match;
  bool port_matches;
  char matched_pattern[256];
  char reason[256];
};

// --- Wildcard Matcher ---
class WildcardMatcher {
public:
  WildcardMatcher() = default;

  // --- Match domain against pattern ---
  MatchResult match_domain(const std::string &target,
                           const std::string &pattern) const {
    MatchResult result;
    std::memset(&result, 0, sizeof(result));
    std::strncpy(result.matched_pattern, pattern.c_str(),
                 sizeof(result.matched_pattern) - 1);

    std::string t = to_lower(target);
    std::string p = to_lower(pattern);

    // Strip protocol
    t = strip_protocol(t);
    p = strip_protocol(p);

    // Extract port
    uint16_t t_port = 0, p_port = 0;
    t = extract_port(t, t_port);
    p = extract_port(p, p_port);

    // Strip trailing path
    auto slash = t.find('/');
    if (slash != std::string::npos) {
      t = t.substr(0, slash);
    }
    slash = p.find('/');
    if (slash != std::string::npos) {
      p = p.substr(0, slash);
    }

    // Strip trailing dot
    if (!t.empty() && t.back() == '.')
      t.pop_back();
    if (!p.empty() && p.back() == '.')
      p.pop_back();

    // Exact match
    if (t == p) {
      result.matches = true;
      result.is_exact_match = true;
      result.is_wildcard_match = false;
      std::snprintf(result.reason, sizeof(result.reason),
                    "Exact match: %s == %s", target.c_str(), pattern.c_str());
    }
    // Wildcard match: *.example.com
    else if (p.size() > 2 && p[0] == '*' && p[1] == '.') {
      std::string suffix = p.substr(1); // .example.com
      if (t.size() > suffix.size() &&
          t.substr(t.size() - suffix.size()) == suffix) {
        result.matches = true;
        result.is_wildcard_match = true;
        result.is_exact_match = false;
        std::snprintf(result.reason, sizeof(result.reason),
                      "Wildcard match: %s matches %s", target.c_str(),
                      pattern.c_str());
      }
      // Also match the bare domain
      else if (t == p.substr(2)) {
        result.matches = true;
        result.is_wildcard_match = false;
        result.is_exact_match = true;
        std::snprintf(result.reason, sizeof(result.reason),
                      "Base domain match: %s matches %s", target.c_str(),
                      pattern.c_str());
      }
    }

    if (!result.matches) {
      std::snprintf(result.reason, sizeof(result.reason),
                    "No match: %s does not match %s", target.c_str(),
                    pattern.c_str());
    }

    // Port check
    if (result.matches && p_port > 0) {
      result.port_matches = (t_port == p_port || t_port == 0);
      if (!result.port_matches) {
        result.matches = false;
        std::snprintf(result.reason, sizeof(result.reason),
                      "Port mismatch: target port %u != scope port %u", t_port,
                      p_port);
      }
    } else {
      result.port_matches = true;
    }

    return result;
  }

  // --- Match URL path against pattern ---
  MatchResult match_path(const std::string &target_path,
                         const std::string &pattern_path) const {
    MatchResult result;
    std::memset(&result, 0, sizeof(result));

    std::string t = to_lower(target_path);
    std::string p = to_lower(pattern_path);

    // Exact path match
    if (t == p) {
      result.matches = true;
      result.is_exact_match = true;
      std::snprintf(result.reason, sizeof(result.reason), "Exact path match");
      return result;
    }

    // Prefix match: /api/* matches /api/users
    if (p.size() > 1 && p.back() == '*') {
      std::string prefix = p.substr(0, p.size() - 1);
      if (t.substr(0, prefix.size()) == prefix) {
        result.matches = true;
        result.is_wildcard_match = true;
        std::snprintf(result.reason, sizeof(result.reason),
                      "Path prefix match: %s starts with %s", t.c_str(),
                      prefix.c_str());
        return result;
      }
    }

    result.matches = false;
    std::snprintf(result.reason, sizeof(result.reason),
                  "Path mismatch: %s vs %s", t.c_str(), p.c_str());
    return result;
  }

  // --- Self-test ---
  static bool run_tests() {
    WildcardMatcher matcher;
    int passed = 0, failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (cond) {
        ++passed;
      } else {
        ++failed;
      }
    };

    // Test 1: Exact match
    auto r1 = matcher.match_domain("api.example.com", "api.example.com");
    test(r1.matches && r1.is_exact_match, "Exact domain match");

    // Test 2: Wildcard match
    auto r2 = matcher.match_domain("sub.example.com", "*.example.com");
    test(r2.matches && r2.is_wildcard_match, "Wildcard match");

    // Test 3: Deep subdomain wildcard
    auto r3 = matcher.match_domain("deep.sub.example.com", "*.example.com");
    test(r3.matches, "Deep subdomain wildcard match");

    // Test 4: No match
    auto r4 = matcher.match_domain("api.other.com", "*.example.com");
    test(!r4.matches, "Different domain should not match");

    // Test 5: Base domain matches wildcard
    auto r5 = matcher.match_domain("example.com", "*.example.com");
    test(r5.matches, "Base domain should match wildcard");

    // Test 6: Port mismatch
    auto r6 =
        matcher.match_domain("api.example.com:8080", "api.example.com:443");
    test(!r6.matches, "Wrong port should not match");

    // Test 7: Path prefix
    auto r7 = matcher.match_path("/api/v1/users", "/api/*");
    test(r7.matches && r7.is_wildcard_match, "Path prefix match");

    // Test 8: Case insensitive
    auto r8 = matcher.match_domain("API.Example.COM", "api.example.com");
    test(r8.matches, "Case insensitive match");

    return failed == 0;
  }

private:
  static std::string to_lower(const std::string &s) {
    std::string result = s;
    for (char &c : result) {
      c = std::tolower(static_cast<unsigned char>(c));
    }
    return result;
  }

  static std::string strip_protocol(const std::string &s) {
    if (s.substr(0, 8) == "https://")
      return s.substr(8);
    if (s.substr(0, 7) == "http://")
      return s.substr(7);
    return s;
  }

  static std::string extract_port(const std::string &s, uint16_t &port) {
    port = 0;
    auto colon = s.rfind(':');
    if (colon == std::string::npos || colon == 0)
      return s;

    std::string after = s.substr(colon + 1);
    bool all_digits = !after.empty();
    for (char c : after) {
      if (!std::isdigit(static_cast<unsigned char>(c))) {
        all_digits = false;
        break;
      }
    }
    if (all_digits) {
      int p = std::stoi(after);
      if (p > 0 && p < 65536) {
        port = static_cast<uint16_t>(p);
        return s.substr(0, colon);
      }
    }
    return s;
  }
};

} // namespace scope_engine
