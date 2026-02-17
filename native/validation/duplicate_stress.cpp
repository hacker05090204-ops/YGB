/**
 * duplicate_stress.cpp — Duplicate Adversarial Test Suite
 *
 * Tests:
 * - Paraphrased vulnerability reports
 * - Template variations
 * - Obfuscated CVE descriptions
 * - Near-duplicate payload mutation
 *
 * Requires:
 *   duplicate detection recall >= 90%
 *   false duplicate flag <= 5%
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

struct DuplicatePair {
  char description_a[512];
  char description_b[512];
  bool is_actual_duplicate;
  char mutation_type[64];
};

struct DuplicateStressResult {
  uint32_t total_pairs;
  uint32_t true_duplicates;
  uint32_t detected_duplicates;
  uint32_t missed_duplicates;
  uint32_t false_duplicates;
  double recall;         // detected / true
  double false_dup_rate; // false / (total - true)
  bool recall_pass;      // >= 0.90
  bool false_dup_pass;   // <= 0.05
  bool overall_pass;
  char summary[512];
};

class DuplicateStressEngine {
public:
  static constexpr double RECALL_THRESHOLD = 0.90;
  static constexpr double FALSE_DUP_THRESHOLD = 0.05;
  static constexpr double SIMILARITY_THRESHOLD = 0.40;

  // --- Text similarity (Jaccard) ---
  static double text_similarity(const char *a, const char *b) {
    auto tokenize = [](const char *text) {
      std::vector<std::string> tokens;
      std::string cur;
      for (const char *p = text; *p; ++p) {
        if (std::isalnum(static_cast<unsigned char>(*p))) {
          cur += std::tolower(static_cast<unsigned char>(*p));
        } else if (!cur.empty()) {
          if (cur.size() >= 3)
            tokens.push_back(cur);
          cur.clear();
        }
      }
      if (cur.size() >= 3)
        tokens.push_back(cur);
      return tokens;
    };

    auto ta = tokenize(a);
    auto tb = tokenize(b);
    if (ta.empty() || tb.empty())
      return 0.0;

    std::sort(ta.begin(), ta.end());
    std::sort(tb.begin(), tb.end());

    size_t common = 0, i = 0, j = 0;
    while (i < ta.size() && j < tb.size()) {
      if (ta[i] == tb[j]) {
        ++common;
        ++i;
        ++j;
      } else if (ta[i] < tb[j])
        ++i;
      else
        ++j;
    }
    size_t uni = ta.size() + tb.size() - common;
    return uni > 0 ? static_cast<double>(common) / uni : 0.0;
  }

  // --- Generate adversarial duplicate pairs ---
  std::vector<DuplicatePair> generate_pairs() const {
    std::vector<DuplicatePair> pairs;

    // 1. Paraphrased duplicates
    auto add_dup = [&](const char *a, const char *b, const char *type) {
      DuplicatePair p;
      std::strncpy(p.description_a, a, 511);
      std::strncpy(p.description_b, b, 511);
      p.is_actual_duplicate = true;
      std::strncpy(p.mutation_type, type, 63);
      pairs.push_back(p);
    };

    auto add_non_dup = [&](const char *a, const char *b, const char *type) {
      DuplicatePair p;
      std::strncpy(p.description_a, a, 511);
      std::strncpy(p.description_b, b, 511);
      p.is_actual_duplicate = false;
      std::strncpy(p.mutation_type, type, 63);
      pairs.push_back(p);
    };

    // Paraphrased duplicates
    add_dup("SQL injection vulnerability in the login form allows "
            "authentication bypass via malicious input",
            "SQLi in login page enables auth bypass through "
            "crafted input parameters",
            "paraphrase");

    add_dup("Cross-site scripting XSS reflected in search parameter",
            "Reflected XSS vulnerability found in the search "
            "input field of the application",
            "paraphrase");

    add_dup("Server-side request forgery SSRF in image URL parameter "
            "allows internal network access",
            "SSRF vulnerability in image fetch function enables "
            "access to internal services",
            "paraphrase");

    // Template variations
    add_dup("Vulnerability Type: SQL Injection\n"
            "Endpoint: /api/login\n"
            "Parameter: username\n"
            "Impact: Authentication bypass",
            "I found an SQL injection bug in the /api/login "
            "endpoint username parameter that bypasses auth",
            "template_variation");

    add_dup("## Summary\nXSS in search\n## Impact\nSession hijacking",
            "Found cross-site scripting in the search function "
            "which could lead to session theft",
            "template_variation");

    // Obfuscated CVE descriptions
    add_dup("CVE-2024-1234: Buffer overflow in image processing "
            "library allows remote code execution",
            "Memory corruption in image parser component permits "
            "arbitrary code execution remotely",
            "obfuscated_cve");

    add_dup("CVE-2024-5678: Improper input validation in API "
            "gateway allows privilege escalation",
            "Missing input sanitization in the API access control "
            "layer enables privilege elevation",
            "obfuscated_cve");

    // Near-duplicate payload mutations
    add_dup("SQL injection using payload: ' OR 1=1-- in login",
            "SQL injection using payload: ' OR '1'='1'-- in login",
            "payload_mutation");

    add_dup("XSS with payload <script>alert(1)</script> in search",
            "XSS with payload <img src=x onerror=alert(1)> in search",
            "payload_mutation");

    // Non-duplicates (should NOT be flagged)
    add_non_dup("SQL injection in login form authentication bypass",
                "Cross-site scripting in user profile page",
                "different_vuln_type");

    add_non_dup("SSRF in image upload function",
                "SQL injection in admin panel search", "different_vuln_type");

    add_non_dup("Buffer overflow in custom JSON parser",
                "XSS reflected in error page output", "different_vuln_type");

    add_non_dup("IDOR in /api/users/123 allows accessing other accounts",
                "CSRF in password change form", "different_vuln_type");

    add_non_dup("Rate limiting bypass in login endpoint",
                "Open redirect in OAuth callback", "different_vuln_type");

    add_non_dup("Information disclosure via verbose error messages",
                "Broken access control in admin API", "different_vuln_type");

    return pairs;
  }

  // --- Run stress test ---
  DuplicateStressResult run() {
    DuplicateStressResult result;
    std::memset(&result, 0, sizeof(result));

    auto pairs = generate_pairs();
    result.total_pairs = static_cast<uint32_t>(pairs.size());

    for (const auto &pair : pairs) {
      double sim = text_similarity(pair.description_a, pair.description_b);
      bool detected = sim >= SIMILARITY_THRESHOLD;

      if (pair.is_actual_duplicate) {
        result.true_duplicates++;
        if (detected) {
          result.detected_duplicates++;
        } else {
          result.missed_duplicates++;
        }
      } else {
        if (detected) {
          result.false_duplicates++;
        }
      }
    }

    // Metrics
    result.recall = result.true_duplicates > 0
                        ? static_cast<double>(result.detected_duplicates) /
                              result.true_duplicates
                        : 0.0;

    uint32_t non_dups = result.total_pairs - result.true_duplicates;
    result.false_dup_rate =
        non_dups > 0 ? static_cast<double>(result.false_duplicates) / non_dups
                     : 0.0;

    result.recall_pass = result.recall >= RECALL_THRESHOLD;
    result.false_dup_pass = result.false_dup_rate <= FALSE_DUP_THRESHOLD;
    result.overall_pass = result.recall_pass && result.false_dup_pass;

    std::snprintf(result.summary, sizeof(result.summary),
                  "Recall: %.2f (%s) | False Dup: %.2f (%s) | "
                  "Detected: %u/%u | False: %u/%u | "
                  "Total pairs: %u",
                  result.recall, result.recall_pass ? "PASS" : "FAIL",
                  result.false_dup_rate,
                  result.false_dup_pass ? "PASS" : "FAIL",
                  result.detected_duplicates, result.true_duplicates,
                  result.false_duplicates, non_dups, result.total_pairs);

    return result;
  }

  // --- Self-test ---
  static bool run_tests() {
    DuplicateStressEngine engine;
    int passed = 0, failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (cond) {
        ++passed;
      } else {
        ++failed;
      }
    };

    auto pairs = engine.generate_pairs();
    test(pairs.size() >= 10, "Should have >= 10 pairs");

    // Count actuals
    uint32_t actual_dups = 0;
    for (const auto &p : pairs) {
      if (p.is_actual_duplicate)
        ++actual_dups;
    }
    test(actual_dups >= 5, "Should have >= 5 actual duplicates");

    // Run stress test
    auto result = engine.run();
    test(result.total_pairs >= 10, "Should test >= 10 pairs");
    test(result.recall_pass, "Recall should pass >= 90%");
    test(result.false_dup_pass, "False dup rate should be <= 5%");
    test(result.overall_pass, "Overall should pass");

    // Similarity sanity checks
    double sim1 = text_similarity("SQL injection in login form",
                                  "SQL injection in login page");
    test(sim1 > 0.5, "Similar texts should have high similarity");

    double sim2 = text_similarity("SQL injection in login",
                                  "Buffer overflow in image parser");
    test(sim2 < 0.3, "Different texts should have low similarity");

    return failed == 0;
  }
};

} // namespace validation
