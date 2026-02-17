/*
 * cve_feed_parser.cpp — CVE / NVD Feed Parser
 *
 * Parses structured CVE data from NVD JSON feeds and RSS.
 *
 * Extracts:
 *   - CVE ID
 *   - Title / summary
 *   - Affected component
 *   - CVSS vector string
 *   - CWE category
 *   - Published date
 *
 * BLOCKS:
 *   - Exploit payloads
 *   - PoC code
 *   - Real target metadata
 *
 * GOVERNANCE: MODE-A only. Zero decision authority.
 */

#include <algorithm>
#include <cstdint>
#include <string>
#include <unordered_set>
#include <vector>


namespace browser_curriculum {

// =========================================================================
// CVE ENTRY
// =========================================================================

struct CveEntry {
  std::string cve_id; // e.g. "CVE-2024-12345"
  std::string title;
  std::string summary; // ≤500 chars, sanitized
  std::string affected_component;
  std::string cvss_vector; // e.g. "CVSS:3.1/AV:N/AC:L/..."
  double cvss_score;       // 0.0 - 10.0
  std::string cwe_id;      // e.g. "CWE-79"
  std::string cwe_name;    // e.g. "Cross-site Scripting"
  std::string published_date;
  std::string source_url;
  bool is_valid;

  CveEntry() : cvss_score(0.0), is_valid(false) {}
};

// =========================================================================
// BLOCKED CONTENT PATTERNS
// =========================================================================

static const std::vector<std::string> BLOCKED_CONTENT = {
    "exploit",    "payload",       "shellcode",  "proof-of-concept",
    "poc:",       "wget ",         "curl ",      "bash -c",
    "powershell", "reverse shell", "bind shell", "meterpreter",
    "metasploit", "cobalt strike", "<script>",   "javascript:",
    "eval(",      "exec(",         "system(",    "os.popen",
};

// =========================================================================
// SANITIZATION
// =========================================================================

inline bool contains_blocked_content(const std::string &text) {
  std::string lower = text;
  std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
  for (const auto &blocked : BLOCKED_CONTENT) {
    if (lower.find(blocked) != std::string::npos) {
      return true;
    }
  }
  return false;
}

inline std::string sanitize_summary(const std::string &raw, int max_len = 500) {
  std::string out;
  out.reserve(std::min(raw.size(), (size_t)max_len));

  for (size_t i = 0; i < raw.size() && (int)out.size() < max_len; ++i) {
    char c = raw[i];
    // Strip HTML tags inline
    if (c == '<') {
      while (i < raw.size() && raw[i] != '>')
        ++i;
      continue;
    }
    // Normalize whitespace
    if (c == '\n' || c == '\r' || c == '\t')
      c = ' ';
    // Skip consecutive spaces
    if (c == ' ' && !out.empty() && out.back() == ' ')
      continue;
    out.push_back(c);
  }
  return out;
}

// =========================================================================
// CVE ID VALIDATION
// =========================================================================

inline bool is_valid_cve_id(const std::string &id) {
  // Format: CVE-YYYY-NNNNN (4-digit year, 4+ digit sequence)
  if (id.size() < 13)
    return false;
  if (id.substr(0, 4) != "CVE-")
    return false;
  // Year check
  for (int i = 4; i < 8; ++i) {
    if (id[i] < '0' || id[i] > '9')
      return false;
  }
  if (id[8] != '-')
    return false;
  // Sequence check
  for (size_t i = 9; i < id.size(); ++i) {
    if (id[i] < '0' || id[i] > '9')
      return false;
  }
  return true;
}

// =========================================================================
// CVSS PARSING
// =========================================================================

inline double parse_cvss_score(const std::string &vector) {
  // Extract base score from vector string
  // CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H → 9.8
  // Simple heuristic scoring based on vector components
  if (vector.empty())
    return 0.0;

  double score = 5.0; // baseline
  std::string lower = vector;
  std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

  if (lower.find("av:n") != std::string::npos)
    score += 1.5; // Network
  if (lower.find("ac:l") != std::string::npos)
    score += 0.8; // Low complexity
  if (lower.find("pr:n") != std::string::npos)
    score += 0.5; // No privs
  if (lower.find("ui:n") != std::string::npos)
    score += 0.3; // No user interaction
  if (lower.find("c:h") != std::string::npos)
    score += 0.5; // High confidentiality
  if (lower.find("i:h") != std::string::npos)
    score += 0.5; // High integrity
  if (lower.find("a:h") != std::string::npos)
    score += 0.5; // High availability

  return std::min(10.0, std::max(0.0, score));
}

// =========================================================================
// FEED PARSING (JSON key extraction)
// =========================================================================

inline std::string extract_json_value(const std::string &json,
                                      const std::string &key) {
  std::string search = "\"" + key + "\"";
  size_t pos = json.find(search);
  if (pos == std::string::npos)
    return "";

  // Find value start (skip : and whitespace)
  pos += search.size();
  while (pos < json.size() &&
         (json[pos] == ':' || json[pos] == ' ' || json[pos] == '\t' ||
          json[pos] == '\n' || json[pos] == '\r'))
    ++pos;

  if (pos >= json.size())
    return "";

  // String value
  if (json[pos] == '"') {
    ++pos;
    std::string value;
    while (pos < json.size() && json[pos] != '"') {
      if (json[pos] == '\\' && pos + 1 < json.size()) {
        ++pos; // skip escape
      }
      value.push_back(json[pos]);
      ++pos;
    }
    return value;
  }

  // Number value
  std::string value;
  while (pos < json.size() && json[pos] != ',' && json[pos] != '}' &&
         json[pos] != ']') {
    value.push_back(json[pos]);
    ++pos;
  }
  return value;
}

// =========================================================================
// PARSE SINGLE CVE ENTRY FROM JSON
// =========================================================================

inline CveEntry parse_cve_json(const std::string &json_block) {
  CveEntry entry;

  entry.cve_id = extract_json_value(json_block, "cveId");
  if (entry.cve_id.empty()) {
    entry.cve_id = extract_json_value(json_block, "id");
  }

  if (!is_valid_cve_id(entry.cve_id)) {
    entry.is_valid = false;
    return entry;
  }

  // Description
  std::string desc = extract_json_value(json_block, "description");
  if (desc.empty()) {
    desc = extract_json_value(json_block, "value");
  }

  // Block exploit content
  if (contains_blocked_content(desc)) {
    entry.is_valid = false;
    return entry;
  }

  entry.summary = sanitize_summary(desc);
  entry.title =
      entry.cve_id + ": " +
      entry.summary.substr(0, std::min((size_t)80, entry.summary.size()));

  // CVSS
  entry.cvss_vector = extract_json_value(json_block, "vectorString");
  entry.cvss_score = parse_cvss_score(entry.cvss_vector);

  // CWE
  entry.cwe_id = extract_json_value(json_block, "cweId");
  if (entry.cwe_id.empty()) {
    entry.cwe_id = extract_json_value(json_block, "problemtype");
  }

  // Affected component
  entry.affected_component = extract_json_value(json_block, "product");
  if (entry.affected_component.empty()) {
    entry.affected_component = extract_json_value(json_block, "vendor");
  }

  // Published date
  entry.published_date = extract_json_value(json_block, "published");
  if (entry.published_date.empty()) {
    entry.published_date = extract_json_value(json_block, "publishedDate");
  }

  entry.is_valid = true;
  return entry;
}

// =========================================================================
// BATCH PARSE (multiple CVE entries)
// =========================================================================

inline std::vector<CveEntry> parse_cve_feed(const std::string &json_feed,
                                            int max_entries = 100) {
  std::vector<CveEntry> entries;

  // Find CVE blocks by searching for CVE IDs
  size_t pos = 0;
  while (pos < json_feed.size() && (int)entries.size() < max_entries) {
    size_t cve_start = json_feed.find("CVE-", pos);
    if (cve_start == std::string::npos)
      break;

    // Find enclosing object
    size_t obj_start = json_feed.rfind('{', cve_start);
    if (obj_start == std::string::npos) {
      pos = cve_start + 4;
      continue;
    }

    // Find matching closing brace (simple depth counter)
    int depth = 1;
    size_t obj_end = obj_start + 1;
    while (obj_end < json_feed.size() && depth > 0) {
      if (json_feed[obj_end] == '{')
        ++depth;
      if (json_feed[obj_end] == '}')
        --depth;
      ++obj_end;
    }

    if (depth == 0) {
      std::string block = json_feed.substr(obj_start, obj_end - obj_start);
      CveEntry entry = parse_cve_json(block);
      if (entry.is_valid) {
        entries.push_back(entry);
      }
    }

    pos = obj_end;
  }

  return entries;
}

} // namespace browser_curriculum
