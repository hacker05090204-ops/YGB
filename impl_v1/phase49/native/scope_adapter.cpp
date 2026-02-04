// scope_adapter.cpp
// Phase-49: Scope Adapter Implementation

#include "scope_adapter.h"
#include <cstring>
#include <fstream>
#include <regex>
#include <sstream>

namespace phase49 {

ScopeAdapter::ScopeAdapter() : initialized_(false) {}

ScopeAdapter::~ScopeAdapter() = default;

bool ScopeAdapter::initialize() {
  initialized_ = true;
  return true;
}

bool ScopeAdapter::wildcard_match(const std::string &pattern,
                                  const std::string &target) const {
  // Convert wildcard pattern to regex
  std::string regex_str;
  for (char c : pattern) {
    switch (c) {
    case '*':
      regex_str += ".*";
      break;
    case '?':
      regex_str += ".";
      break;
    case '.':
      regex_str += "\\.";
      break;
    default:
      regex_str += c;
    }
  }

  try {
    std::regex re(regex_str, std::regex::icase);
    return std::regex_match(target, re);
  } catch (...) {
    return false;
  }
}

bool ScopeAdapter::matches_entry(const ScopeEntry &entry,
                                 const std::string &target) const {
  // Check for wildcard
  if (entry.identifier.find('*') != std::string::npos) {
    return wildcard_match(entry.identifier, target);
  }

  // Direct match
  if (entry.identifier == target) {
    return true;
  }

  // Subdomain match (e.g., entry "example.com" matches "sub.example.com")
  if (target.size() > entry.identifier.size()) {
    size_t offset = target.size() - entry.identifier.size();
    if (target[offset - 1] == '.' &&
        target.substr(offset) == entry.identifier) {
      return true;
    }
  }

  return false;
}

PlatformScope ScopeAdapter::parse_hackerone(const std::string &json) {
  PlatformScope scope;
  scope.platform = PlatformType::HACKERONE;

  // Simple JSON parsing (in production, use a proper JSON library)
  // Look for "eligible_for_submission": true and extract target
  std::regex target_regex("\"identifier\"\\s*:\\s*\"([^\"]+)\"");
  std::regex eligible_regex("\"eligible_for_submission\"\\s*:\\s*(true|false)");
  std::regex type_regex("\"asset_type\"\\s*:\\s*\"([^\"]+)\"");

  std::sregex_iterator it(json.begin(), json.end(), target_regex);
  std::sregex_iterator end;

  while (it != end) {
    ScopeEntry entry;
    entry.identifier = (*it)[1].str();
    entry.in_scope = true; // Default to in-scope
    entry.eligible_for_submission = true;
    entry.asset_type = "url";
    scope.entries.push_back(entry);
    ++it;
  }

  return scope;
}

PlatformScope ScopeAdapter::parse_bugcrowd(const std::string &json) {
  PlatformScope scope;
  scope.platform = PlatformType::BUGCROWD;

  // Similar parsing logic for Bugcrowd format
  std::regex target_regex("\"target\"\\s*:\\s*\"([^\"]+)\"");

  std::sregex_iterator it(json.begin(), json.end(), target_regex);
  std::sregex_iterator end;

  while (it != end) {
    ScopeEntry entry;
    entry.identifier = (*it)[1].str();
    entry.in_scope = true;
    entry.eligible_for_submission = true;
    entry.asset_type = "url";
    scope.entries.push_back(entry);
    ++it;
  }

  return scope;
}

PlatformScope ScopeAdapter::parse_custom(const std::string &json) {
  PlatformScope scope;
  scope.platform = PlatformType::CUSTOM;

  // Simple line-by-line parsing for custom format
  std::istringstream stream(json);
  std::string line;

  while (std::getline(stream, line)) {
    // Skip comments and empty lines
    if (line.empty() || line[0] == '#') {
      continue;
    }

    ScopeEntry entry;

    // Check for exclusion prefix
    if (line[0] == '!' || line[0] == '-') {
      entry.in_scope = false;
      entry.identifier = line.substr(1);
    } else if (line[0] == '+') {
      entry.in_scope = true;
      entry.identifier = line.substr(1);
    } else {
      entry.in_scope = true;
      entry.identifier = line;
    }

    entry.eligible_for_submission = entry.in_scope;
    entry.asset_type = "domain";
    scope.entries.push_back(entry);
  }

  return scope;
}

ScopeCheckResult ScopeAdapter::check_scope(const PlatformScope &scope,
                                           const std::string &target) {
  ScopeCheckResult result;
  result.in_scope = false;
  result.reason = "No matching scope entry";

  // Check exclusions first (they take priority)
  for (const auto &entry : scope.entries) {
    if (!entry.in_scope && matches_entry(entry, target)) {
      result.in_scope = false;
      result.reason = "Explicitly excluded: " + entry.identifier;
      result.matched_entry = entry;
      return result;
    }
  }

  // Check inclusions
  for (const auto &entry : scope.entries) {
    if (entry.in_scope && matches_entry(entry, target)) {
      result.in_scope = true;
      result.reason = "Matches scope: " + entry.identifier;
      result.matched_entry = entry;
      return result;
    }
  }

  return result;
}

PlatformScope ScopeAdapter::load_from_file(const std::string &filepath) {
  std::ifstream file(filepath);
  if (!file.is_open()) {
    return PlatformScope();
  }

  std::ostringstream buffer;
  buffer << file.rdbuf();
  std::string content = buffer.str();

  // Detect format based on content
  if (content.find("hackerone") != std::string::npos ||
      content.find("\"eligible_for_submission\"") != std::string::npos) {
    return parse_hackerone(content);
  } else if (content.find("bugcrowd") != std::string::npos) {
    return parse_bugcrowd(content);
  } else {
    return parse_custom(content);
  }
}

// C interface
extern "C" {

static PlatformScope current_scope;

void *scope_adapter_create() { return new ScopeAdapter(); }

void scope_adapter_destroy(void *adapter) {
  delete static_cast<ScopeAdapter *>(adapter);
}

int scope_adapter_init(void *adapter) {
  if (!adapter)
    return -1;
  return static_cast<ScopeAdapter *>(adapter)->initialize() ? 0 : -1;
}

int scope_adapter_load(void *adapter, const char *filepath, int platform_type) {
  if (!adapter || !filepath)
    return -1;

  current_scope =
      static_cast<ScopeAdapter *>(adapter)->load_from_file(filepath);

  return current_scope.entries.empty() ? -1 : 0;
}

int scope_adapter_check(void *adapter, const char *target, int *out_in_scope,
                        char *out_reason, int reason_size) {
  if (!adapter || !target)
    return -1;

  ScopeCheckResult result =
      static_cast<ScopeAdapter *>(adapter)->check_scope(current_scope, target);

  if (out_in_scope)
    *out_in_scope = result.in_scope ? 1 : 0;

  if (out_reason && reason_size > 0) {
    strncpy(out_reason, result.reason.c_str(), reason_size - 1);
    out_reason[reason_size - 1] = '\0';
  }

  return 0;
}

} // extern "C"

} // namespace phase49
