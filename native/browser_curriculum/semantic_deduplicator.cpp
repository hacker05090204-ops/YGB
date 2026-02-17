/*
 * semantic_deduplicator.cpp — TF-IDF Semantic Deduplication
 *
 * Computes TF-IDF similarity between new content and existing corpus.
 * Skips ingestion if similarity > 0.85 threshold.
 *
 * GOVERNANCE: MODE-A only. Zero decision authority.
 */

#include <algorithm>
#include <cctype>
#include <cmath>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>


namespace browser_curriculum {

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr double SIMILARITY_THRESHOLD = 0.85;
static constexpr int MAX_VOCAB_SIZE = 10000;
static constexpr int MIN_TERM_LENGTH = 3;

// Stop words for filtering
static const std::vector<std::string> STOP_WORDS = {
    "the",   "a",     "an",     "is",    "are",   "was",  "were",  "be",
    "been",  "have",  "has",    "had",   "do",    "does", "did",   "will",
    "would", "could", "should", "may",   "might", "can",  "shall", "must",
    "and",   "or",    "but",    "nor",   "not",   "so",   "yet",   "for",
    "of",    "in",    "to",     "with",  "at",    "by",   "from",  "on",
    "as",    "if",    "that",   "this",  "it",    "its",  "he",    "she",
    "they",  "we",    "you",    "their", "his",   "her",  "our",   "my",
    "your",  "who",   "which",  "what",  "where", "when", "how",   "all",
    "each",  "every", "both",   "few",   "more",  "most", "other", "some",
    "such",  "than",  "too",
};

// =========================================================================
// TF-IDF VECTOR
// =========================================================================

struct TfIdfVector {
  std::unordered_map<std::string, double> weights;
  double magnitude;

  TfIdfVector() : magnitude(0.0) {}

  void compute_magnitude() {
    magnitude = 0.0;
    for (const auto &[term, w] : weights) {
      magnitude += w * w;
    }
    magnitude = std::sqrt(magnitude);
  }
};

// =========================================================================
// TOKENIZER
// =========================================================================

inline std::vector<std::string> tokenize(const std::string &text) {
  std::vector<std::string> tokens;
  std::string current;

  for (char c : text) {
    if (std::isalnum(c)) {
      current.push_back(std::tolower(c));
    } else {
      if (!current.empty() && (int)current.size() >= MIN_TERM_LENGTH) {
        tokens.push_back(current);
      }
      current.clear();
    }
  }
  if (!current.empty() && (int)current.size() >= MIN_TERM_LENGTH) {
    tokens.push_back(current);
  }

  return tokens;
}

inline bool is_stop_word(const std::string &word) {
  for (const auto &sw : STOP_WORDS) {
    if (word == sw)
      return true;
  }
  return false;
}

// =========================================================================
// SEMANTIC DEDUPLICATOR
// =========================================================================

class SemanticDeduplicator {
public:
  SemanticDeduplicator() : doc_count_(0), threshold_(SIMILARITY_THRESHOLD) {}

  // Add document to corpus
  void add_document(const std::string &doc_id, const std::string &text) {
    auto tokens = tokenize(text);
    std::unordered_map<std::string, int> tf;

    for (const auto &t : tokens) {
      if (!is_stop_word(t)) {
        tf[t]++;
      }
    }

    // Update document frequency
    for (const auto &[term, count] : tf) {
      df_[term]++;
    }

    doc_tf_[doc_id] = tf;
    doc_count_++;

    // Recompute vectors for all documents
    recompute_vectors();
  }

  // Check if new text is too similar to existing corpus
  bool is_duplicate(const std::string &text) const {
    double max_sim = max_similarity(text);
    return max_sim > threshold_;
  }

  // Get max similarity of text against corpus
  double max_similarity(const std::string &text) const {
    if (doc_count_ == 0)
      return 0.0;

    TfIdfVector query_vec = compute_vector(text);
    if (query_vec.magnitude < 1e-10)
      return 0.0;

    double max_sim = 0.0;
    for (const auto &[doc_id, vec] : vectors_) {
      double sim = cosine_similarity(query_vec, vec);
      max_sim = std::max(max_sim, sim);
    }
    return max_sim;
  }

  // Get corpus size
  int corpus_size() const { return doc_count_; }

  // Get threshold
  double threshold() const { return threshold_; }

  // Set threshold
  void set_threshold(double t) { threshold_ = std::max(0.0, std::min(1.0, t)); }

private:
  int doc_count_;
  double threshold_;
  std::unordered_map<std::string, int> df_; // document frequency
  std::unordered_map<std::string, std::unordered_map<std::string, int>> doc_tf_;
  std::unordered_map<std::string, TfIdfVector> vectors_;

  TfIdfVector compute_vector(const std::string &text) const {
    auto tokens = tokenize(text);
    std::unordered_map<std::string, int> tf;
    for (const auto &t : tokens) {
      if (!is_stop_word(t))
        tf[t]++;
    }

    TfIdfVector vec;
    int total_terms = static_cast<int>(tokens.size());
    if (total_terms == 0)
      return vec;

    for (const auto &[term, count] : tf) {
      double tf_val = (double)count / total_terms;
      auto it = df_.find(term);
      double idf =
          (it != df_.end())
              ? std::log((double)(doc_count_ + 1) / (it->second + 1)) + 1.0
              : std::log((double)(doc_count_ + 1)) + 1.0;
      vec.weights[term] = tf_val * idf;
    }
    vec.compute_magnitude();
    return vec;
  }

  void recompute_vectors() {
    vectors_.clear();
    for (const auto &[doc_id, tf] : doc_tf_) {
      TfIdfVector vec;
      int total = 0;
      for (const auto &[t, c] : tf)
        total += c;
      if (total == 0)
        continue;

      for (const auto &[term, count] : tf) {
        double tf_val = (double)count / total;
        auto it = df_.find(term);
        double idf =
            (it != df_.end())
                ? std::log((double)(doc_count_ + 1) / (it->second + 1)) + 1.0
                : std::log((double)(doc_count_ + 1)) + 1.0;
        vec.weights[term] = tf_val * idf;
      }
      vec.compute_magnitude();
      vectors_[doc_id] = vec;
    }
  }

  static double cosine_similarity(const TfIdfVector &a, const TfIdfVector &b) {
    if (a.magnitude < 1e-10 || b.magnitude < 1e-10)
      return 0.0;

    double dot = 0.0;
    // Iterate over smaller vector
    const auto &smaller =
        (a.weights.size() < b.weights.size()) ? a.weights : b.weights;
    const auto &larger =
        (a.weights.size() < b.weights.size()) ? b.weights : a.weights;

    for (const auto &[term, weight] : smaller) {
      auto it = larger.find(term);
      if (it != larger.end()) {
        dot += weight * it->second;
      }
    }

    return dot / (a.magnitude * b.magnitude);
  }
};

} // namespace browser_curriculum
