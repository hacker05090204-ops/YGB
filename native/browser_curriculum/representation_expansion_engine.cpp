/*
 * representation_expansion_engine.cpp — Safe Representation Expansion
 *
 * Expands MODE-A representation using validated CVE/security data.
 *
 * ALLOWED expansion axes:
 *   - Protocol variations (HTTP methods, status codes, headers)
 *   - DOM structure diversity (tag depth, nesting patterns)
 *   - API schema structure (endpoint patterns, param types)
 *   - Auth flow topology (OAuth, JWT, session patterns)
 *
 * BLOCKED:
 *   - Exploit payload learning
 *   - Severity modeling
 *   - Real target ingestion
 *   - Platform metadata
 *
 * GOVERNANCE: MODE-A only. Zero decision authority.
 */

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>
#include <unordered_set>
#include <vector>


namespace browser_curriculum {

// =========================================================================
// EXPANSION AXIS TYPES
// =========================================================================

enum class ExpansionAxis {
  PROTOCOL_VARIATION,
  DOM_STRUCTURE,
  API_SCHEMA,
  AUTH_FLOW,
};

// =========================================================================
// BLOCKED CATEGORIES — NEVER EXPAND THESE
// =========================================================================

static const std::unordered_set<std::string> BLOCKED_CATEGORIES = {
    "exploit_payload",   "severity_model",  "real_target",
    "platform_metadata", "credential_data", "session_token",
    "personal_data",     "attack_tool",     "reverse_shell",
    "malware_signature", "zero_day",        "weaponized",
};

// =========================================================================
// EXPANSION INPUT (from CVE/security feed)
// =========================================================================

struct ExpansionInput {
  std::string source_id; // CVE ID or doc ID
  std::string category;  // Must not be in BLOCKED_CATEGORIES
  ExpansionAxis axis;
  std::string raw_text;
  double confidence; // 0.0 - 1.0

  bool is_valid() const {
    if (source_id.empty() || raw_text.empty())
      return false;
    if (confidence < 0.5)
      return false;
    if (BLOCKED_CATEGORIES.find(category) != BLOCKED_CATEGORIES.end())
      return false;
    return true;
  }
};

// =========================================================================
// EXPANSION RESULT
// =========================================================================

struct ExpansionResult {
  bool accepted;
  std::string source_id;
  ExpansionAxis axis;
  int features_added;
  double diversity_delta;
  std::string rejection_reason;

  ExpansionResult()
      : accepted(false), features_added(0), diversity_delta(0.0) {}
};

// =========================================================================
// FEATURE EXTRACTION PER AXIS
// =========================================================================

struct ProtocolFeatures {
  // HTTP method distribution
  double get_ratio;
  double post_ratio;
  double put_ratio;
  double delete_ratio;
  double patch_ratio;
  // Status code patterns
  int unique_status_codes;
  // Header diversity
  int unique_headers;
  double content_type_entropy;
};

struct DomFeatures {
  int max_depth;
  int unique_tags;
  double nesting_ratio;
  int form_count;
  int input_count;
  int link_count;
};

struct ApiSchemaFeatures {
  int endpoint_count;
  int unique_params;
  int auth_required_count;
  double param_type_entropy;
  int json_depth;
};

struct AuthFlowFeatures {
  bool has_oauth;
  bool has_jwt;
  bool has_session;
  bool has_api_key;
  bool has_basic_auth;
  int flow_steps;
  double complexity_score;
};

// =========================================================================
// BLOCKED CONTENT DETECTOR
// =========================================================================

inline bool is_blocked_content(const std::string &text) {
  std::string lower = text;
  std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

  static const std::vector<std::string> EXPLOIT_PATTERNS = {
      "shellcode",
      "payload",
      "reverse shell",
      "bind shell",
      "meterpreter",
      "cobalt strike",
      "exploit code",
      "proof of concept",
      "poc:",
      "weaponized",
      "0day",
      "zero-day",
      "dropper",
      "backdoor",
      "privilege escalation",
      "root access",
      "rm -rf",
      "format c:",
      "del /f",
  };

  for (const auto &p : EXPLOIT_PATTERNS) {
    if (lower.find(p) != std::string::npos)
      return true;
  }
  return false;
}

// =========================================================================
// EXPANSION ENGINE
// =========================================================================

class RepresentationExpansionEngine {
public:
  RepresentationExpansionEngine()
      : total_expanded_(0), total_blocked_(0), total_skipped_(0) {}

  ExpansionResult process(const ExpansionInput &input) {
    ExpansionResult result;
    result.source_id = input.source_id;
    result.axis = input.axis;

    // Validation gate 1: input validity
    if (!input.is_valid()) {
      result.rejection_reason = "Invalid input or blocked category";
      total_blocked_++;
      return result;
    }

    // Validation gate 2: exploit content check
    if (is_blocked_content(input.raw_text)) {
      result.rejection_reason = "Contains exploit/attack content";
      total_blocked_++;
      return result;
    }

    // Validation gate 3: minimum text quality
    if (input.raw_text.size() < 50) {
      result.rejection_reason = "Text too short for expansion";
      total_skipped_++;
      return result;
    }

    // Extract features based on axis
    int features = 0;
    switch (input.axis) {
    case ExpansionAxis::PROTOCOL_VARIATION:
      features = extract_protocol_features(input.raw_text);
      break;
    case ExpansionAxis::DOM_STRUCTURE:
      features = extract_dom_features(input.raw_text);
      break;
    case ExpansionAxis::API_SCHEMA:
      features = extract_api_features(input.raw_text);
      break;
    case ExpansionAxis::AUTH_FLOW:
      features = extract_auth_features(input.raw_text);
      break;
    }

    if (features == 0) {
      result.rejection_reason = "No extractable features";
      total_skipped_++;
      return result;
    }

    result.accepted = true;
    result.features_added = features;
    result.diversity_delta = compute_diversity_delta(features);
    total_expanded_++;
    return result;
  }

  // Statistics
  int total_expanded() const { return total_expanded_; }
  int total_blocked() const { return total_blocked_; }
  int total_skipped() const { return total_skipped_; }

private:
  int total_expanded_;
  int total_blocked_;
  int total_skipped_;

  int extract_protocol_features(const std::string &text) {
    int features = 0;
    std::string lower = text;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

    if (lower.find("http") != std::string::npos)
      features++;
    if (lower.find("https") != std::string::npos)
      features++;
    if (lower.find("get") != std::string::npos)
      features++;
    if (lower.find("post") != std::string::npos)
      features++;
    if (lower.find("header") != std::string::npos)
      features++;
    if (lower.find("content-type") != std::string::npos)
      features++;
    if (lower.find("status") != std::string::npos)
      features++;
    if (lower.find("redirect") != std::string::npos)
      features++;
    return features;
  }

  int extract_dom_features(const std::string &text) {
    int features = 0;
    std::string lower = text;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

    if (lower.find("dom") != std::string::npos)
      features++;
    if (lower.find("<form") != std::string::npos)
      features++;
    if (lower.find("<input") != std::string::npos)
      features++;
    if (lower.find("<a ") != std::string::npos)
      features++;
    if (lower.find("element") != std::string::npos)
      features++;
    if (lower.find("attribute") != std::string::npos)
      features++;
    if (lower.find("tag") != std::string::npos)
      features++;
    return features;
  }

  int extract_api_features(const std::string &text) {
    int features = 0;
    std::string lower = text;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

    if (lower.find("api") != std::string::npos)
      features++;
    if (lower.find("endpoint") != std::string::npos)
      features++;
    if (lower.find("parameter") != std::string::npos)
      features++;
    if (lower.find("json") != std::string::npos)
      features++;
    if (lower.find("rest") != std::string::npos)
      features++;
    if (lower.find("graphql") != std::string::npos)
      features++;
    if (lower.find("schema") != std::string::npos)
      features++;
    return features;
  }

  int extract_auth_features(const std::string &text) {
    int features = 0;
    std::string lower = text;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

    if (lower.find("oauth") != std::string::npos)
      features++;
    if (lower.find("jwt") != std::string::npos)
      features++;
    if (lower.find("token") != std::string::npos)
      features++;
    if (lower.find("session") != std::string::npos)
      features++;
    if (lower.find("authentication") != std::string::npos)
      features++;
    if (lower.find("authorization") != std::string::npos)
      features++;
    if (lower.find("cookie") != std::string::npos)
      features++;
    return features;
  }

  double compute_diversity_delta(int features) {
    // Logarithmic scaling — diminishing returns
    return std::log(1.0 + features) / std::log(10.0);
  }
};

} // namespace browser_curriculum
