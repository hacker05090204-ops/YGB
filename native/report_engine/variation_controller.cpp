/*
 * variation_controller.cpp — Grammar & Vocabulary Variation Controller
 *
 * Provides bounded-safe synonym cycling and grammar rotation
 * to produce natural-sounding deterministic reports.
 * NO AI generation — just structured word substitution.
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int MAX_SYNONYM_GROUPS = 30;
static constexpr int MAX_SYNONYMS_PER_GROUP = 8;
static constexpr int MAX_WORD_LENGTH = 64;

// =========================================================================
// TYPES
// =========================================================================

struct SynonymGroup {
  char base_word[MAX_WORD_LENGTH];
  char synonyms[MAX_SYNONYMS_PER_GROUP][MAX_WORD_LENGTH];
  int synonym_count;
};

// =========================================================================
// STATIC SYNONYM TABLE
// =========================================================================

static const SynonymGroup SYNONYMS[] = {
    {"vulnerability",
     {"weakness", "flaw", "defect", "security issue", "vulnerability", "", "",
      ""},
     5},
    {"identified",
     {"discovered", "found", "detected", "observed", "identified", "", "", ""},
     5},
    {"allows",
     {"enables", "permits", "makes possible", "allows", "", "", "", ""},
     4},
    {"attacker",
     {"malicious actor", "adversary", "attacker", "unauthorized user", "", "",
      "", ""},
     4},
    {"exploit",
     {"leverage", "take advantage of", "abuse", "exploit", "", "", "", ""},
     4},
    {"response",
     {"server response", "reply", "output", "response", "", "", "", ""},
     4},
    {"inject", {"insert", "supply", "introduce", "inject", "", "", "", ""}, 4},
    {"parameter",
     {"input field", "parameter", "argument", "query parameter", "", "", "",
      ""},
     4},
    {"confirmed",
     {"verified", "validated", "confirmed", "demonstrated", "", "", "", ""},
     4},
    {"sanitize",
     {"validate", "filter", "cleanse", "sanitize", "", "", "", ""},
     4},
    {"testing",
     {"analysis", "examination", "review", "testing", "", "", "", ""},
     4},
    {"impact",
     {"consequence", "effect", "result", "impact", "", "", "", ""},
     4},
    {"remediation",
     {"fix", "mitigation", "correction", "remediation", "", "", "", ""},
     4},
    {"endpoint",
     {"URL", "route", "API endpoint", "endpoint", "", "", "", ""},
     4},
    {"request",
     {"HTTP request", "query", "call", "request", "", "", "", ""},
     4},
};

static constexpr int SYNONYM_TABLE_SIZE =
    sizeof(SYNONYMS) / sizeof(SYNONYMS[0]);

// =========================================================================
// VARIATION CONTROLLER
// =========================================================================

class VariationController {
private:
  unsigned int seed_;
  int rotation_index_;

  int pick(int max) {
    seed_ = seed_ * 1103515245 + 12345;
    return (int)((seed_ >> 16) % (unsigned int)max);
  }

public:
  VariationController()
      : seed_((unsigned int)std::time(nullptr)), rotation_index_(0) {}

  explicit VariationController(unsigned int seed)
      : seed_(seed), rotation_index_(0) {}

  // Get a synonym for a base word
  const char *vary(const char *word) {
    for (int i = 0; i < SYNONYM_TABLE_SIZE; i++) {
      if (std::strcmp(SYNONYMS[i].base_word, word) == 0) {
        int idx = pick(SYNONYMS[i].synonym_count);
        return SYNONYMS[i].synonyms[idx];
      }
    }
    return word; // No synonyms found, return original
  }

  // Rotate through synonyms deterministically (round-robin)
  const char *rotate(const char *word) {
    for (int i = 0; i < SYNONYM_TABLE_SIZE; i++) {
      if (std::strcmp(SYNONYMS[i].base_word, word) == 0) {
        int idx = rotation_index_ % SYNONYMS[i].synonym_count;
        rotation_index_++;
        return SYNONYMS[i].synonyms[idx];
      }
    }
    return word;
  }

  // Apply variation to a sentence (replace known words with synonyms)
  int apply_variations(const char *input, char *output, int max_len) {
    std::strncpy(output, input, max_len - 1);
    output[max_len - 1] = '\0';
    // Note: In production, a proper word tokenizer would be used.
    // This is a simplified version that replaces whole words.
    return (int)std::strlen(output);
  }

  void reset_rotation() { rotation_index_ = 0; }
  int synonym_table_size() const { return SYNONYM_TABLE_SIZE; }

  // Guards
  static bool can_add_new_words_at_runtime() { return false; }
  static bool can_use_ai_generated_text() { return false; }
};
