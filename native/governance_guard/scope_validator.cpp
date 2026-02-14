/*
 * scope_validator.cpp — Scope Validation Engine
 *
 * RULES:
 *   - Scope must be user-approved before hunting
 *   - Validates URLs against approved domain/path/wildcard rules
 *   - Out-of-scope targets are hard-blocked
 *   - No runtime scope expansion without user approval
 */

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>


// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int MAX_SCOPE_RULES = 64;
static constexpr int MAX_DOMAIN_LENGTH = 256;
static constexpr int MAX_PATH_LENGTH = 512;
static constexpr int MAX_URL_LENGTH = 1024;

// =========================================================================
// TYPES
// =========================================================================

enum class ScopeRuleType {
  DOMAIN_EXACT,    // example.com
  DOMAIN_WILDCARD, // *.example.com
  PATH_PREFIX,     // example.com/api/*
  PATH_EXACT,      // example.com/login
  URL_PATTERN      // https://example.com/api/v1/*
};

enum class ScopeStatus {
  IN_SCOPE,
  OUT_OF_SCOPE,
  SCOPE_NOT_SET,
  SCOPE_EXPIRED,
  INVALID_URL
};

struct ScopeRule {
  ScopeRuleType type;
  char domain[MAX_DOMAIN_LENGTH];
  char path[MAX_PATH_LENGTH];
  bool active;
  bool user_approved;
  time_t approved_at;
};

struct ScopeCheckResult {
  ScopeStatus status;
  bool allowed;
  int matched_rule_index;
  char reason[256];
};

struct ScopeDefinition {
  ScopeRule rules[MAX_SCOPE_RULES];
  int rule_count;
  bool locked; // Once approved, no modification without re-approval
  time_t approved_at;
  char approved_by[64]; // Must be "user"
};

// =========================================================================
// SCOPE VALIDATOR
// =========================================================================

class ScopeValidator {
private:
  ScopeDefinition scope_;

  // Extract domain from URL
  static bool extract_domain(const char *url, char *domain, int max_len) {
    const char *start = std::strstr(url, "://");
    if (!start)
      return false;
    start += 3;
    const char *end = std::strchr(start, '/');
    int len = end ? (int)(end - start) : (int)std::strlen(start);
    if (len <= 0 || len >= max_len)
      return false;
    std::memcpy(domain, start, len);
    domain[len] = '\0';
    // Lowercase
    for (int i = 0; i < len; i++)
      domain[i] = (char)std::tolower(domain[i]);
    return true;
  }

  // Extract path from URL
  static bool extract_path(const char *url, char *path, int max_len) {
    const char *start = std::strstr(url, "://");
    if (!start)
      return false;
    start += 3;
    const char *slash = std::strchr(start, '/');
    if (!slash) {
      std::strncpy(path, "/", max_len - 1);
      return true;
    }
    std::strncpy(path, slash, max_len - 1);
    path[max_len - 1] = '\0';
    return true;
  }

  // Wildcard domain match: *.example.com matches sub.example.com
  static bool wildcard_domain_match(const char *pattern, const char *domain) {
    if (pattern[0] == '*' && pattern[1] == '.') {
      const char *suffix = pattern + 1; // .example.com
      int suffix_len = (int)std::strlen(suffix);
      int domain_len = (int)std::strlen(domain);
      if (domain_len <= suffix_len)
        return false;
      return std::strcmp(domain + domain_len - suffix_len, suffix) == 0;
    }
    return std::strcmp(pattern, domain) == 0;
  }

  // Path prefix match: /api/* matches /api/v1/users
  static bool path_prefix_match(const char *pattern, const char *path) {
    int plen = (int)std::strlen(pattern);
    if (plen > 0 && pattern[plen - 1] == '*') {
      return std::strncmp(path, pattern, plen - 1) == 0;
    }
    return std::strcmp(path, pattern) == 0;
  }

public:
  ScopeValidator() { std::memset(&scope_, 0, sizeof(scope_)); }

  // =======================================================================
  // SCOPE MANAGEMENT
  // =======================================================================

  bool add_rule(ScopeRuleType type, const char *domain, const char *path,
                bool user_approved) {
    if (scope_.locked)
      return false;
    if (scope_.rule_count >= MAX_SCOPE_RULES)
      return false;
    if (!user_approved)
      return false; // Must be user-approved

    ScopeRule &r = scope_.rules[scope_.rule_count];
    r.type = type;
    std::strncpy(r.domain, domain, MAX_DOMAIN_LENGTH - 1);
    r.domain[MAX_DOMAIN_LENGTH - 1] = '\0';
    if (path) {
      std::strncpy(r.path, path, MAX_PATH_LENGTH - 1);
      r.path[MAX_PATH_LENGTH - 1] = '\0';
    }
    r.active = true;
    r.user_approved = true;
    r.approved_at = std::time(nullptr);
    scope_.rule_count++;
    return true;
  }

  void lock_scope() {
    scope_.locked = true;
    scope_.approved_at = std::time(nullptr);
    std::strncpy(scope_.approved_by, "user", sizeof(scope_.approved_by) - 1);
  }

  // =======================================================================
  // VALIDATION
  // =======================================================================

  ScopeCheckResult check_url(const char *url) {
    ScopeCheckResult result;
    std::memset(&result, 0, sizeof(result));
    result.matched_rule_index = -1;

    if (!url || std::strlen(url) == 0) {
      result.status = ScopeStatus::INVALID_URL;
      result.allowed = false;
      std::snprintf(result.reason, sizeof(result.reason), "Empty URL");
      return result;
    }

    if (scope_.rule_count == 0) {
      result.status = ScopeStatus::SCOPE_NOT_SET;
      result.allowed = false;
      std::snprintf(result.reason, sizeof(result.reason),
               "No scope rules defined — scope must be set first");
      return result;
    }

    char domain[MAX_DOMAIN_LENGTH];
    char path[MAX_PATH_LENGTH];

    if (!extract_domain(url, domain, MAX_DOMAIN_LENGTH)) {
      result.status = ScopeStatus::INVALID_URL;
      result.allowed = false;
      std::snprintf(result.reason, sizeof(result.reason), "Cannot parse domain");
      return result;
    }

    extract_path(url, path, MAX_PATH_LENGTH);

    // Check each rule
    for (int i = 0; i < scope_.rule_count; i++) {
      const ScopeRule &r = scope_.rules[i];
      if (!r.active || !r.user_approved)
        continue;

      bool match = false;
      switch (r.type) {
      case ScopeRuleType::DOMAIN_EXACT:
        match = (std::strcmp(domain, r.domain) == 0);
        break;
      case ScopeRuleType::DOMAIN_WILDCARD:
        match = wildcard_domain_match(r.domain, domain);
        break;
      case ScopeRuleType::PATH_PREFIX:
        match =
            (std::strcmp(domain, r.domain) == 0) && path_prefix_match(r.path, path);
        break;
      case ScopeRuleType::PATH_EXACT:
        match = (std::strcmp(domain, r.domain) == 0) && (std::strcmp(path, r.path) == 0);
        break;
      case ScopeRuleType::URL_PATTERN:
        match = wildcard_domain_match(r.domain, domain) &&
                path_prefix_match(r.path, path);
        break;
      }

      if (match) {
        result.status = ScopeStatus::IN_SCOPE;
        result.allowed = true;
        result.matched_rule_index = i;
        std::snprintf(result.reason, sizeof(result.reason), "Matched rule %d: %s%s",
                 i, r.domain, r.path);
        return result;
      }
    }

    result.status = ScopeStatus::OUT_OF_SCOPE;
    result.allowed = false;
    std::snprintf(result.reason, sizeof(result.reason),
             "URL '%s' does not match any approved scope rule", url);
    return result;
  }

  // =======================================================================
  // GUARDS
  // =======================================================================

  static bool can_expand_scope_without_approval() { return false; }
  static bool can_add_rule_without_user() { return false; }
  static bool can_unlock_scope() { return false; }

  bool is_locked() const { return scope_.locked; }
  int rule_count() const { return scope_.rule_count; }
};
