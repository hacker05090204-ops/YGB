/*
 * duplicate_detector.cpp — Report Duplicate Detection Engine
 *
 * Compares new reports against previous reports using term overlap.
 * Blocks if similarity exceeds threshold (0.80).
 */

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>


// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int MAX_REPORTS = 500;
static constexpr int MAX_TERMS = 256;
static constexpr int MAX_TERM_LENGTH = 64;
static constexpr int MAX_FINGERPRINT_SIZE = 128;
static constexpr double DUPLICATE_THRESHOLD = 0.80; // 80%

// =========================================================================
// TYPES
// =========================================================================

struct ReportFingerprint {
  int report_id;
  time_t created_at;
  char endpoint[512];
  char parameter[128];
  char vuln_type[64];
  char terms[MAX_TERMS][MAX_TERM_LENGTH];
  int term_count;
  char title_hash[65];
};

struct DuplicateCheckResult {
  bool is_duplicate;
  double similarity;
  int matched_report_id;
  char reason[256];
};

// =========================================================================
// DUPLICATE DETECTOR
// =========================================================================

class DuplicateDetector {
private:
  ReportFingerprint reports_[MAX_REPORTS];
  int report_count_;

  // Extract key terms from text (simple word tokenizer)
  static int extract_terms(const char *text, char terms[][MAX_TERM_LENGTH],
                           int max_terms) {
    int count = 0;
    char word[MAX_TERM_LENGTH];
    int wlen = 0;

    for (int i = 0; text[i] && count < max_terms; i++) {
      if (std::isalnum(text[i])) {
        if (wlen < MAX_TERM_LENGTH - 1)
          word[wlen++] = (char)std::tolower(text[i]);
      } else {
        if (wlen >= 3) { // Ignore words < 3 chars
          word[wlen] = '\0';
          std::strncpy(terms[count], word, MAX_TERM_LENGTH - 1);
          count++;
        }
        wlen = 0;
      }
    }
    if (wlen >= 3) {
      word[wlen] = '\0';
      std::strncpy(terms[count], word, MAX_TERM_LENGTH - 1);
      count++;
    }
    return count;
  }

  // Compute Jaccard similarity between two term sets
  static double jaccard_similarity(const char a[][MAX_TERM_LENGTH], int a_count,
                                   const char b[][MAX_TERM_LENGTH],
                                   int b_count) {
    if (a_count == 0 && b_count == 0)
      return 1.0;
    if (a_count == 0 || b_count == 0)
      return 0.0;

    int intersection = 0;
    for (int i = 0; i < a_count; i++) {
      for (int j = 0; j < b_count; j++) {
        if (std::strcmp(a[i], b[j]) == 0) {
          intersection++;
          break;
        }
      }
    }

    int union_size = a_count + b_count - intersection;
    return union_size > 0 ? (double)intersection / (double)union_size : 0.0;
  }

public:
  DuplicateDetector() : report_count_(0) {
    std::memset(reports_, 0, sizeof(reports_));
  }

  // Register a report fingerprint
  bool register_report(int report_id, const char *endpoint,
                       const char *parameter, const char *vuln_type,
                       const char *full_text) {
    if (report_count_ >= MAX_REPORTS)
      return false;

    ReportFingerprint &f = reports_[report_count_];
    f.report_id = report_id;
    f.created_at = std::time(nullptr);
    std::strncpy(f.endpoint, endpoint ? endpoint : "", sizeof(f.endpoint) - 1);
    std::strncpy(f.parameter, parameter ? parameter : "", sizeof(f.parameter) - 1);
    std::strncpy(f.vuln_type, vuln_type ? vuln_type : "", sizeof(f.vuln_type) - 1);

    f.term_count = extract_terms(full_text, f.terms, MAX_TERMS);

    report_count_++;
    return true;
  }

  // Check if new report is a duplicate
  DuplicateCheckResult check_duplicate(const char *endpoint,
                                       const char *parameter,
                                       const char *vuln_type,
                                       const char *full_text) {
    DuplicateCheckResult result;
    std::memset(&result, 0, sizeof(result));
    result.matched_report_id = -1;

    // Extract terms from new report
    char new_terms[MAX_TERMS][MAX_TERM_LENGTH];
    int new_count = extract_terms(full_text, new_terms, MAX_TERMS);

    double max_similarity = 0;
    int max_id = -1;

    for (int i = 0; i < report_count_; i++) {
      // Exact match on endpoint+parameter+type = very likely duplicate
      bool exact_match = (std::strcmp(reports_[i].endpoint, endpoint) == 0) &&
                         (std::strcmp(reports_[i].parameter, parameter) == 0) &&
                         (std::strcmp(reports_[i].vuln_type, vuln_type) == 0);

      double sim = jaccard_similarity(
          (const char (*)[MAX_TERM_LENGTH])reports_[i].terms,
          reports_[i].term_count, (const char (*)[MAX_TERM_LENGTH])new_terms,
          new_count);

      // Boost similarity if exact metadata match
      if (exact_match)
        sim = sim * 0.5 + 0.5; // Boost by 50%

      if (sim > max_similarity) {
        max_similarity = sim;
        max_id = reports_[i].report_id;
      }
    }

    result.similarity = max_similarity;
    result.matched_report_id = max_id;

    if (max_similarity >= DUPLICATE_THRESHOLD) {
      result.is_duplicate = true;
      std::snprintf(result.reason, sizeof(result.reason),
               "BLOCKED: %.0f%% similarity with report #%d (threshold: %.0f%%)",
               max_similarity * 100, max_id, DUPLICATE_THRESHOLD * 100);
    } else {
      result.is_duplicate = false;
      std::snprintf(result.reason, sizeof(result.reason),
               "OK: %.0f%% similarity (below %.0f%% threshold)",
               max_similarity * 100, DUPLICATE_THRESHOLD * 100);
    }
    return result;
  }

  int report_count() const { return report_count_; }
  double threshold() const { return DUPLICATE_THRESHOLD; }

  // Guards
  static bool can_lower_threshold() { return false; }
  static bool can_bypass_duplicate_check() { return false; }
  static bool can_delete_fingerprints() { return false; }
};
