/**
 * scope_parser.cpp — Program Scope Parser
 *
 * Parses scope from bug bounty program policy text.
 * Extracts in-scope domains, IPs, wildcards, exclusions.
 *
 * NO mock data. NO auto-submit. NO authority unlock.
 */

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <regex>
#include <string>
#include <vector>


namespace scope_engine {

// --- Scope Entry Types ---
enum class ScopeType : uint8_t {
  DOMAIN = 0,
  WILDCARD = 1, // *.example.com
  IP_ADDRESS = 2,
  IP_RANGE = 3, // 10.0.0.0/24
  URL_PATH = 4, // example.com/api/*
  EXCLUSION = 5 // Explicitly out of scope
};

struct ScopeEntry {
  ScopeType type;
  char pattern[256];
  char original_text[512];
  bool is_exclusion;
  uint16_t port_min; // 0 = any
  uint16_t port_max;
};

struct ParsedScope {
  std::vector<ScopeEntry> in_scope;
  std::vector<ScopeEntry> out_of_scope;
  bool parsed_successfully;
  uint32_t total_entries;
  char parse_errors[1024];
};

// --- Scope Parser ---
class ScopeParser {
public:
  ScopeParser() = default;

  // --- Parse scope text ---
  ParsedScope parse(const std::string &scope_text) {
    ParsedScope result;
    result.parsed_successfully = true;
    result.total_entries = 0;
    std::memset(result.parse_errors, 0, sizeof(result.parse_errors));

    if (scope_text.empty()) {
      result.parsed_successfully = false;
      std::strncpy(result.parse_errors, "Empty scope text",
                   sizeof(result.parse_errors) - 1);
      return result;
    }

    // Split by newlines
    std::vector<std::string> lines;
    std::string current;
    for (char c : scope_text) {
      if (c == '\n' || c == '\r') {
        if (!current.empty()) {
          lines.push_back(current);
          current.clear();
        }
      } else {
        current += c;
      }
    }
    if (!current.empty())
      lines.push_back(current);

    bool in_exclusion_section = false;

    for (const auto &line : lines) {
      std::string trimmed = trim(line);
      if (trimmed.empty())
        continue;

      // Detect section headers
      std::string lower = to_lower(trimmed);
      if (lower.find("out of scope") != std::string::npos ||
          lower.find("out-of-scope") != std::string::npos ||
          lower.find("exclusion") != std::string::npos ||
          lower.find("not in scope") != std::string::npos) {
        in_exclusion_section = true;
        continue;
      }
      if (lower.find("in scope") != std::string::npos ||
          lower.find("in-scope") != std::string::npos) {
        in_exclusion_section = false;
        continue;
      }

      // Try to parse as scope entry
      ScopeEntry entry;
      std::memset(&entry, 0, sizeof(entry));
      entry.is_exclusion = in_exclusion_section;
      std::strncpy(entry.original_text, trimmed.c_str(),
                   sizeof(entry.original_text) - 1);

      // Remove list markers
      std::string clean = trimmed;
      if (clean.size() > 2 &&
          (clean[0] == '-' || clean[0] == '*' || clean[0] == '+')) {
        clean = trim(clean.substr(1));
      }
      if (clean.size() > 3 &&
          std::isdigit(static_cast<unsigned char>(clean[0])) &&
          (clean[1] == '.' || clean[1] == ')')) {
        clean = trim(clean.substr(2));
      }

      if (parse_entry(clean, entry)) {
        if (entry.is_exclusion) {
          entry.type = ScopeType::EXCLUSION;
          result.out_of_scope.push_back(entry);
        } else {
          result.in_scope.push_back(entry);
        }
        result.total_entries++;
      }
    }

    if (result.total_entries == 0) {
      result.parsed_successfully = false;
      std::strncpy(result.parse_errors, "No valid scope entries found",
                   sizeof(result.parse_errors) - 1);
    }

    return result;
  }

  // --- Self-test ---
  static bool run_tests() {
    ScopeParser parser;
    int passed = 0, failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (cond) {
        ++passed;
      } else {
        ++failed;
      }
    };

    // Test 1: Parse basic scope
    auto r1 = parser.parse("In Scope:\n"
                           "- *.example.com\n"
                           "- api.target.io\n"
                           "- 10.0.0.0/24\n"
                           "\n"
                           "Out of Scope:\n"
                           "- staging.example.com\n"
                           "- *.internal.example.com\n");
    test(r1.parsed_successfully, "Should parse successfully");
    test(r1.in_scope.size() == 3, "Should have 3 in-scope entries");
    test(r1.out_of_scope.size() == 2, "Should have 2 out-of-scope entries");

    // Test 2: Wildcard detection
    test(r1.in_scope[0].type == ScopeType::WILDCARD,
         "*.example.com should be WILDCARD");

    // Test 3: Domain detection
    test(r1.in_scope[1].type == ScopeType::DOMAIN,
         "api.target.io should be DOMAIN");

    // Test 4: IP range detection
    test(r1.in_scope[2].type == ScopeType::IP_RANGE,
         "10.0.0.0/24 should be IP_RANGE");

    // Test 5: Empty scope
    auto r2 = parser.parse("");
    test(!r2.parsed_successfully, "Empty should fail");

    return failed == 0;
  }

private:
  bool parse_entry(const std::string &text, ScopeEntry &entry) {
    if (text.empty() || text.size() < 3)
      return false;

    std::strncpy(entry.pattern, text.c_str(), sizeof(entry.pattern) - 1);

    // Detect type
    if (text.find("*.") == 0) {
      entry.type = ScopeType::WILDCARD;
    } else if (is_ip_range(text)) {
      entry.type = ScopeType::IP_RANGE;
    } else if (is_ip_address(text)) {
      entry.type = ScopeType::IP_ADDRESS;
    } else if (text.find('/') != std::string::npos &&
               text.find('.') != std::string::npos) {
      entry.type = ScopeType::URL_PATH;
    } else if (text.find('.') != std::string::npos) {
      entry.type = ScopeType::DOMAIN;
    } else {
      return false;
    }

    // Extract port if present (domain:8080)
    auto colon = text.rfind(':');
    if (colon != std::string::npos && colon > 0) {
      std::string port_str = text.substr(colon + 1);
      bool all_digits = !port_str.empty();
      for (char c : port_str) {
        if (!std::isdigit(static_cast<unsigned char>(c))) {
          all_digits = false;
          break;
        }
      }
      if (all_digits) {
        int port = std::stoi(port_str);
        if (port > 0 && port < 65536) {
          entry.port_min = static_cast<uint16_t>(port);
          entry.port_max = entry.port_min;
          // Remove port from pattern
          std::strncpy(entry.pattern, text.substr(0, colon).c_str(),
                       sizeof(entry.pattern) - 1);
        }
      }
    }

    return true;
  }

  bool is_ip_address(const std::string &text) const {
    int dots = 0, digits = 0;
    for (char c : text) {
      if (c == '.') {
        dots++;
        digits = 0;
      } else if (std::isdigit(static_cast<unsigned char>(c))) {
        digits++;
      } else
        return false;
    }
    return dots == 3 && digits > 0;
  }

  bool is_ip_range(const std::string &text) const {
    return text.find('/') != std::string::npos &&
           is_ip_address(text.substr(0, text.find('/')));
  }

  static std::string trim(const std::string &s) {
    auto start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos)
      return "";
    auto end = s.find_last_not_of(" \t\r\n");
    return s.substr(start, end - start + 1);
  }

  static std::string to_lower(const std::string &s) {
    std::string result = s;
    for (char &c : result) {
      c = std::tolower(static_cast<unsigned char>(c));
    }
    return result;
  }
};

} // namespace scope_engine
