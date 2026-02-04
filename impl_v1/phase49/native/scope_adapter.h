// scope_adapter.h
// Phase-49: Platform Scope Adapter
//
// STRICT RULES:
// - Parse and enforce platform scope
// - NO scope mutation
// - Respect all exclusions

#ifndef PHASE49_SCOPE_ADAPTER_H
#define PHASE49_SCOPE_ADAPTER_H

#include <string>
#include <vector>

namespace phase49 {

// Platform type
enum class PlatformType { HACKERONE, BUGCROWD, INTIGRITI, CUSTOM };

// Scope entry
struct ScopeEntry {
  std::string identifier; // domain, IP, wildcard
  bool in_scope;          // true = in scope, false = excluded
  std::string asset_type; // url, domain, cidr, etc.
  bool eligible_for_submission;
};

// Parsed scope
struct PlatformScope {
  PlatformType platform;
  std::string program_handle;
  std::vector<ScopeEntry> entries;
  std::vector<std::string> out_of_scope_hints;
  bool is_public;
  bool allows_disclosure;
};

// Scope check result
struct ScopeCheckResult {
  bool in_scope;
  std::string reason;
  ScopeEntry matched_entry;
};

// Scope adapter
class ScopeAdapter {
public:
  ScopeAdapter();
  ~ScopeAdapter();

  bool initialize();

  // Parse scope from platform JSON
  PlatformScope parse_hackerone(const std::string &json);
  PlatformScope parse_bugcrowd(const std::string &json);
  PlatformScope parse_custom(const std::string &json);

  // Check if URL/domain is in scope
  ScopeCheckResult check_scope(const PlatformScope &scope,
                               const std::string &target);

  // Load scope from file
  PlatformScope load_from_file(const std::string &filepath);

private:
  bool initialized_;

  // Match target against scope entry
  bool matches_entry(const ScopeEntry &entry, const std::string &target) const;

  // Wildcard matching
  bool wildcard_match(const std::string &pattern,
                      const std::string &target) const;
};

// C interface
extern "C" {
void *scope_adapter_create();
void scope_adapter_destroy(void *adapter);
int scope_adapter_init(void *adapter);
int scope_adapter_load(void *adapter, const char *filepath, int platform_type);
int scope_adapter_check(void *adapter, const char *target, int *out_in_scope,
                        char *out_reason, int reason_size);
}

} // namespace phase49

#endif // PHASE49_SCOPE_ADAPTER_H
