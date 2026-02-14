/*
 * scope_parser.cpp — Scope Extraction Engine
 *
 * Parses user-provided scope definitions.
 * Extracts domains, paths, wildcards, exclusions.
 * NO scraping — user-provided data only.
 */

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int MAX_SCOPE_ENTRIES = 100;
static constexpr int MAX_EXCLUSIONS = 50;
static constexpr int MAX_DOMAIN = 256;
static constexpr int MAX_PATH_LEN = 512;

// =========================================================================
// TYPES
// =========================================================================

enum class ScopeEntryType {
  DOMAIN,
  SUBDOMAIN_WILDCARD,
  PATH,
  API_ENDPOINT,
  IP_RANGE,
  EXCLUDED
};

struct ScopeEntry {
  ScopeEntryType type;
  char domain[MAX_DOMAIN];
  char path[MAX_PATH_LEN];
  bool in_scope;
  int priority; // Higher = more important
};

struct ParsedScope {
  ScopeEntry entries[MAX_SCOPE_ENTRIES];
  int entry_count;
  char exclusions[MAX_EXCLUSIONS][MAX_DOMAIN];
  int exclusion_count;
  char program_name[256];
  char platform[64]; // Informational only
  bool valid;
  char error[256];
};

// =========================================================================
// SCOPE PARSER
// =========================================================================

class ScopeParser {
private:
  // Detect if line is a wildcard pattern
  static bool is_wildcard(const char *line) {
    return (line[0] == '*' && line[1] == '.');
  }

  // Detect if line is an exclusion
  static bool is_exclusion(const char *line) {
    // Lines starting with !, -, "out of scope", "excluded"
    if (line[0] == '!' || line[0] == '-')
      return true;
    char lower[MAX_DOMAIN];
    int len = (int)std::strlen(line);
    if (len >= MAX_DOMAIN)
      len = MAX_DOMAIN - 1;
    for (int i = 0; i < len; i++)
      lower[i] = (char)std::tolower(line[i]);
    lower[len] = '\0';
    return (std::strstr(lower, "out of scope") != nullptr ||
            std::strstr(lower, "excluded") != nullptr ||
            std::strstr(lower, "not in scope") != nullptr);
  }

  // Detect type from text
  static ScopeEntryType detect_type(const char *line) {
    if (is_exclusion(line))
      return ScopeEntryType::EXCLUDED;
    if (is_wildcard(line))
      return ScopeEntryType::SUBDOMAIN_WILDCARD;
    if (std::strstr(line, "/api/") || std::strstr(line, "/v1/") ||
        std::strstr(line, "/v2/") || std::strstr(line, "/graphql"))
      return ScopeEntryType::API_ENDPOINT;
    if (std::strchr(line, '/'))
      return ScopeEntryType::PATH;
    // Check for IP pattern
    int dots = 0;
    for (int i = 0; line[i]; i++)
      if (line[i] == '.')
        dots++;
    if (dots == 3) {
      bool all_digits_or_dots = true;
      for (int i = 0; line[i]; i++) {
        if (!std::isdigit(line[i]) && line[i] != '.' && line[i] != '/' &&
            line[i] != '-')
          all_digits_or_dots = false;
      }
      if (all_digits_or_dots)
        return ScopeEntryType::IP_RANGE;
    }
    return ScopeEntryType::DOMAIN;
  }

public:
  ScopeParser() = default;

  ParsedScope parse(const char *scope_text, const char *program_name,
                    const char *platform) {
    ParsedScope result;
    std::memset(&result, 0, sizeof(result));

    if (!scope_text || std::strlen(scope_text) == 0) {
      result.valid = false;
      std::snprintf(result.error, sizeof(result.error), "Empty scope text");
      return result;
    }

    std::strncpy(result.program_name, program_name ? program_name : "",
                 sizeof(result.program_name) - 1);
    std::strncpy(result.platform, platform ? platform : "",
                 sizeof(result.platform) - 1);

    // Parse line by line
    const char *pos = scope_text;
    char line[MAX_DOMAIN + MAX_PATH_LEN];

    while (*pos && result.entry_count < MAX_SCOPE_ENTRIES) {
      // Read one line
      int llen = 0;
      while (*pos && *pos != '\n' && llen < (int)sizeof(line) - 1)
        line[llen++] = *pos++;
      line[llen] = '\0';
      if (*pos == '\n')
        pos++;

      // Skip empty lines and comments
      if (llen == 0)
        continue;
      if (line[0] == '#')
        continue;

      // Trim whitespace
      int start = 0;
      while (start < llen && std::isspace(line[start]))
        start++;
      if (start >= llen)
        continue;

      const char *trimmed = line + start;
      ScopeEntryType type = detect_type(trimmed);

      if (type == ScopeEntryType::EXCLUDED) {
        if (result.exclusion_count < MAX_EXCLUSIONS) {
          // Skip prefix (!, -, etc.)
          const char *excl = trimmed;
          if (*excl == '!' || *excl == '-')
            excl++;
          while (*excl == ' ')
            excl++;
          std::strncpy(result.exclusions[result.exclusion_count], excl,
                       MAX_DOMAIN - 1);
          result.exclusion_count++;
        }
        continue;
      }

      ScopeEntry &e = result.entries[result.entry_count];
      e.type = type;
      e.in_scope = true;
      e.priority = (type == ScopeEntryType::API_ENDPOINT)         ? 3
                   : (type == ScopeEntryType::SUBDOMAIN_WILDCARD) ? 2
                                                                  : 1;

      // Split domain/path
      const char *slash = std::strchr(trimmed, '/');
      if (slash && type != ScopeEntryType::IP_RANGE) {
        int dlen = (int)(slash - trimmed);
        if (dlen >= MAX_DOMAIN)
          dlen = MAX_DOMAIN - 1;
        std::memcpy(e.domain, trimmed, dlen);
        e.domain[dlen] = '\0';
        std::strncpy(e.path, slash, MAX_PATH_LEN - 1);
      } else {
        std::strncpy(e.domain, trimmed, MAX_DOMAIN - 1);
        std::strcpy(e.path, "/");
      }

      result.entry_count++;
    }

    result.valid = (result.entry_count > 0);
    if (!result.valid)
      std::snprintf(result.error, sizeof(result.error),
                    "No valid scope entries found");

    return result;
  }

  // Guards
  static bool can_scrape_scope() { return false; }
  static bool can_expand_scope_auto() { return false; }
};
