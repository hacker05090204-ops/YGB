/*
 * result_summarizer.cpp — Local Text Summarizer for Research Results
 *
 * RULES:
 *   - Runs entirely locally — NO external API calls
 *   - Extracts key sentences using TF-IDF keyword scoring
 *   - Max 500-word output per query
 *   - No model weights or ML inference
 *   - No training data access
 *   - No governance modification
 */

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#ifdef _WIN32
#define strcasecmp _stricmp
#endif

// =========================================================================
// CONSTANTS
// =========================================================================

static const int MAX_SUMMARY_WORDS = 500;
static const int MAX_SENTENCES = 128;
static const int MAX_SENTENCE_LENGTH = 512;
static const int MAX_KEYWORDS = 64;
static const int MAX_KEY_TERMS = 10;
static const int MAX_PARAGRAPHS = 3;
static const int MAX_TITLE_LENGTH = 256;

// Common English stop words to exclude from keyword extraction
static const char *STOP_WORDS[] = {
    "the",  "a",     "an",    "is",     "are",   "was",   "were", "be",
    "been", "being", "have",  "has",    "had",   "do",    "does", "did",
    "will", "would", "could", "should", "may",   "might", "can",  "shall",
    "must", "and",   "or",    "but",    "nor",   "not",   "so",   "yet",
    "for",  "of",    "in",    "to",     "with",  "at",    "by",   "from",
    "on",   "as",    "if",    "that",   "this",  "it",    "its",  "he",
    "she",  "they",  "we",    "you",    "their", "his",   "her",  "our",
    "my",   "your",  "who",   "which",  "what",  "where", "when", "how",
    "all",  "each",  "every", "both",   "few",   "more",  "most", "other",
    "some", "such",  "than",  "too",    "very",  nullptr};

// Prompt injection banned words — sentences containing these are REJECTED
static const char *INJECTION_WORDS[] = {
    "ignore", "system",  "override", "execute", "expose", "weights",
    "delete", "run",     "bypass",   "admin",   "root",   "sudo",
    "inject", "payload", "shell",    "eval",    nullptr};

// Imperative verbs — sentences starting with these are REJECTED
static const char *IMPERATIVE_VERBS[] = {
    "ignore", "forget", "disregard", "override", "execute", "run",    "delete",
    "drop",   "expose", "reveal",    "show",     "print",   "output", "dump",
    "send",   "submit", "approve",   "confirm",  "launch",  "start",  nullptr};

// =========================================================================
// TYPES
// =========================================================================

struct Sentence {
  char text[MAX_SENTENCE_LENGTH];
  int word_count;
  float score;  // TF-IDF relevance score
  int position; // Position in original text
};

struct Keyword {
  char word[64];
  int frequency;
  float tf_idf;
};

struct ResearchSummary {
  char title[MAX_TITLE_LENGTH];
  char source[256];
  char top_paragraphs[MAX_PARAGRAPHS][MAX_SENTENCE_LENGTH];
  int paragraph_count;
  char key_terms[MAX_KEY_TERMS][64];
  int key_term_count;
  int total_words;
  bool success;
  char error[128];
};

// =========================================================================
// HELPERS
// =========================================================================

static bool is_stop_word(const char *word) {
  for (int i = 0; STOP_WORDS[i]; i++) {
    if (strcasecmp(word, STOP_WORDS[i]) == 0)
      return true;
  }
  return false;
}

static int extract_word(const char *text, int pos, int len, char *word_out,
                        int max) {
  while (pos < len && !isalpha(text[pos]))
    pos++;
  int wpos = 0;
  while (pos < len && (isalpha(text[pos]) || text[pos] == '\'') &&
         wpos < max - 1) {
    word_out[wpos++] = (char)tolower(text[pos++]);
  }
  word_out[wpos] = '\0';
  return pos;
}

// =========================================================================
// PROMPT INJECTION FILTER
// =========================================================================

static bool is_injection_sentence(const char *sentence, int len) {
  // Convert to lowercase for matching
  char lower[MAX_SENTENCE_LENGTH];
  int llen = len < MAX_SENTENCE_LENGTH - 1 ? len : MAX_SENTENCE_LENGTH - 1;
  for (int i = 0; i < llen; i++)
    lower[i] = (char)tolower(sentence[i]);
  lower[llen] = '\0';

  // Check for banned injection words anywhere in sentence
  for (int i = 0; INJECTION_WORDS[i]; i++) {
    if (strstr(lower, INJECTION_WORDS[i]) != nullptr)
      return true;
  }

  // Check for imperative verb at sentence start
  // Skip leading whitespace
  int start = 0;
  while (start < llen && (lower[start] == ' ' || lower[start] == '\t'))
    start++;

  // Extract first word
  char first_word[64];
  int wpos = 0;
  int pos = start;
  while (pos < llen && isalpha(lower[pos]) && wpos < 63) {
    first_word[wpos++] = lower[pos++];
  }
  first_word[wpos] = '\0';

  if (wpos > 0) {
    for (int i = 0; IMPERATIVE_VERBS[i]; i++) {
      if (strcmp(first_word, IMPERATIVE_VERBS[i]) == 0)
        return true;
    }
  }

  return false;
}

// =========================================================================
// RESULT SUMMARIZER
// =========================================================================

class ResultSummarizer {
public:
  // =====================================================================
  // SUMMARIZE extracted text
  // =====================================================================

  ResearchSummary summarize(const char *text, int text_length,
                            const char *title, const char *source) {
    ResearchSummary summary;
    memset(&summary, 0, sizeof(summary));
    summary.success = true;

    if (!text || text_length <= 0) {
      summary.success = false;
      snprintf(summary.error, sizeof(summary.error), "Empty text input");
      return summary;
    }

    // Set title and source
    if (title)
      strncpy(summary.title, title, MAX_TITLE_LENGTH - 1);
    if (source)
      strncpy(summary.source, source, 255);

    // Step 1: Split into sentences
    Sentence sentences[MAX_SENTENCES];
    int sentence_count =
        split_sentences(text, text_length, sentences, MAX_SENTENCES);

    if (sentence_count == 0) {
      summary.success = false;
      snprintf(summary.error, sizeof(summary.error), "No sentences found");
      return summary;
    }

    // Step 2: Extract keywords (TF-IDF)
    Keyword keywords[MAX_KEYWORDS];
    int keyword_count =
        extract_keywords(text, text_length, keywords, MAX_KEYWORDS);

    // Step 3: Score sentences by keyword relevance
    score_sentences(sentences, sentence_count, keywords, keyword_count);

    // Step 4: Select top sentences (keep original order)
    // Sort by score, take top MAX_PARAGRAPHS, then re-sort by position
    int indices[MAX_SENTENCES];
    for (int i = 0; i < sentence_count; i++)
      indices[i] = i;

    // Sort by score descending
    for (int i = 0; i < sentence_count - 1; i++) {
      for (int j = i + 1; j < sentence_count; j++) {
        if (sentences[indices[j]].score > sentences[indices[i]].score) {
          int tmp = indices[i];
          indices[i] = indices[j];
          indices[j] = tmp;
        }
      }
    }

    // Take top N, re-sort by position
    int selected_count =
        sentence_count < MAX_PARAGRAPHS ? sentence_count : MAX_PARAGRAPHS;
    int selected[MAX_PARAGRAPHS];
    for (int i = 0; i < selected_count; i++)
      selected[i] = indices[i];

    // Sort selected by position (preserve reading order)
    for (int i = 0; i < selected_count - 1; i++) {
      for (int j = i + 1; j < selected_count; j++) {
        if (sentences[selected[j]].position < sentences[selected[i]].position) {
          int tmp = selected[i];
          selected[i] = selected[j];
          selected[j] = tmp;
        }
      }
    }

    // Step 5: Build summary
    int total_words = 0;
    for (int i = 0; i < selected_count && total_words < MAX_SUMMARY_WORDS;
         i++) {
      strncpy(summary.top_paragraphs[i], sentences[selected[i]].text,
              MAX_SENTENCE_LENGTH - 1);
      total_words += sentences[selected[i]].word_count;
      summary.paragraph_count++;
    }
    summary.total_words = total_words;

    // Step 6: Extract key terms
    int kt_count =
        keyword_count < MAX_KEY_TERMS ? keyword_count : MAX_KEY_TERMS;
    for (int i = 0; i < kt_count; i++) {
      strncpy(summary.key_terms[i], keywords[i].word, 63);
      summary.key_term_count++;
    }

    return summary;
  }

  // Guards
  static bool can_call_external_api() { return false; }
  static bool can_use_model_weights() { return false; }
  static bool can_access_training() { return false; }
  static bool can_modify_integrity_score() { return false; }

private:
  // =====================================================================
  // SENTENCE SPLITTING
  // =====================================================================

  int split_sentences(const char *text, int len, Sentence *out,
                      int max_sentences) {
    int count = 0;
    int pos = 0;
    char buf[MAX_SENTENCE_LENGTH];
    int bpos = 0;
    int word_count = 0;

    while (pos < len && count < max_sentences) {
      char c = text[pos++];

      if (c == '.' || c == '!' || c == '?' || c == '\n') {
        if (bpos > 10) { // Minimum sentence length
          buf[bpos] = '\0';
          // Trim leading whitespace
          int start = 0;
          while (start < bpos && (buf[start] == ' ' || buf[start] == '\n'))
            start++;

          // INJECTION FILTER: reject sentences with banned words
          if (!is_injection_sentence(buf + start, bpos - start)) {
            strncpy(out[count].text, buf + start, MAX_SENTENCE_LENGTH - 1);
            out[count].text[MAX_SENTENCE_LENGTH - 1] = '\0';
            out[count].word_count = word_count;
            out[count].position = count;
            out[count].score = 0.0f;
            count++;
          }
        }
        bpos = 0;
        word_count = 0;
      } else {
        if (bpos < MAX_SENTENCE_LENGTH - 2) {
          buf[bpos++] = c;
          if (c == ' ' && bpos > 1 && buf[bpos - 2] != ' ')
            word_count++;
        }
      }
    }

    // Handle last sentence without period
    if (bpos > 10 && count < max_sentences) {
      buf[bpos] = '\0';
      int start = 0;
      while (start < bpos && buf[start] == ' ')
        start++;
      if (!is_injection_sentence(buf + start, bpos - start)) {
        strncpy(out[count].text, buf + start, MAX_SENTENCE_LENGTH - 1);
        out[count].word_count = word_count;
        out[count].position = count;
        out[count].score = 0.0f;
        count++;
      }
    }

    return count;
  }

  // =====================================================================
  // KEYWORD EXTRACTION (Term Frequency)
  // =====================================================================

  int extract_keywords(const char *text, int len, Keyword *out,
                       int max_keywords) {
    int count = 0;
    int pos = 0;
    char word[64];

    // Count total words
    int total_words = 0;
    int p = 0;
    while (p < len) {
      p = extract_word(text, p, len, word, 64);
      if (word[0])
        total_words++;
    }

    // Count word frequencies
    pos = 0;
    while (pos < len && count < max_keywords) {
      pos = extract_word(text, pos, len, word, 64);
      if (!word[0] || strlen(word) < 3)
        continue;
      if (is_stop_word(word))
        continue;

      // Check if already in list
      bool found = false;
      for (int i = 0; i < count; i++) {
        if (strcmp(out[i].word, word) == 0) {
          out[i].frequency++;
          found = true;
          break;
        }
      }

      if (!found && count < max_keywords) {
        strncpy(out[count].word, word, 63);
        out[count].frequency = 1;
        out[count].tf_idf = 0.0f;
        count++;
      }
    }

    // Compute TF scores and sort
    for (int i = 0; i < count; i++) {
      // TF = frequency / total_words
      // IDF approximated by word length bonus (longer = more specific)
      float tf = (float)out[i].frequency / (float)(total_words + 1);
      float length_bonus = 1.0f + 0.1f * (float)strlen(out[i].word);
      out[i].tf_idf = tf * length_bonus;
    }

    // Sort by TF-IDF descending
    for (int i = 0; i < count - 1; i++) {
      for (int j = i + 1; j < count; j++) {
        if (out[j].tf_idf > out[i].tf_idf) {
          Keyword tmp = out[i];
          out[i] = out[j];
          out[j] = tmp;
        }
      }
    }

    return count;
  }

  // =====================================================================
  // SENTENCE SCORING
  // =====================================================================

  void score_sentences(Sentence *sentences, int sent_count, Keyword *keywords,
                       int kw_count) {
    for (int s = 0; s < sent_count; s++) {
      float score = 0.0f;

      // Score by keyword presence
      for (int k = 0; k < kw_count && k < 20; k++) {
        // Case-insensitive substring search
        char sent_lower[MAX_SENTENCE_LENGTH];
        int slen = (int)strlen(sentences[s].text);
        for (int i = 0; i < slen; i++)
          sent_lower[i] = (char)tolower(sentences[s].text[i]);
        sent_lower[slen] = '\0';

        if (strstr(sent_lower, keywords[k].word)) {
          score += keywords[k].tf_idf * 10.0f;
        }
      }

      // Position bonus: first sentences get slight boost
      if (sentences[s].position < 3) {
        score *= 1.2f;
      }

      // Length penalty: very short sentences less useful
      if (sentences[s].word_count < 5) {
        score *= 0.5f;
      }

      sentences[s].score = score;
    }
  }
};
