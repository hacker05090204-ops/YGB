/**
 * similarity_index.cpp — TF-IDF Vector Store for CVE Descriptions
 *
 * Builds TF-IDF vectors from vulnerability descriptions.
 * Supports incremental indexing and cosine similarity search.
 *
 * NO mock data. NO synthetic fallback.
 */

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>


namespace duplicate_engine {

// --- Document entry ---
struct IndexEntry {
  std::string doc_id; // CVE-2024-XXXX or internal ID
  std::string raw_text;
  std::vector<double> tfidf_vector;
  double norm; // Precomputed L2 norm
};

// --- TF-IDF Similarity Index ---
class SimilarityIndex {
public:
  static constexpr size_t MAX_VOCAB_SIZE = 50000;
  static constexpr size_t MIN_TERM_FREQUENCY = 2;

private:
  std::unordered_map<std::string, uint32_t> vocab_;
  std::vector<std::string> vocab_reverse_;
  std::vector<uint32_t> document_frequency_;
  std::vector<IndexEntry> documents_;
  bool index_dirty_; // Needs recomputation

public:
  SimilarityIndex() : index_dirty_(false) {}

  // --- Tokenize text ---
  static std::vector<std::string> tokenize(const std::string &text) {
    std::vector<std::string> tokens;
    std::string current;

    for (char c : text) {
      if (std::isalnum(static_cast<unsigned char>(c))) {
        current += std::tolower(static_cast<unsigned char>(c));
      } else {
        if (current.size() >= 2) {
          tokens.push_back(current);
        }
        current.clear();
      }
    }
    if (current.size() >= 2) {
      tokens.push_back(current);
    }
    return tokens;
  }

  // --- Add document to index ---
  void add_document(const std::string &doc_id, const std::string &text) {
    IndexEntry entry;
    entry.doc_id = doc_id;
    entry.raw_text = text;
    entry.norm = 0.0;

    auto tokens = tokenize(text);

    // Update vocabulary
    std::unordered_map<std::string, uint32_t> local_tf;
    for (const auto &tok : tokens) {
      local_tf[tok]++;
    }

    // Update document frequency
    for (const auto &pair : local_tf) {
      if (vocab_.find(pair.first) == vocab_.end()) {
        if (vocab_.size() < MAX_VOCAB_SIZE) {
          uint32_t idx = static_cast<uint32_t>(vocab_.size());
          vocab_[pair.first] = idx;
          vocab_reverse_.push_back(pair.first);
          document_frequency_.push_back(0);
        }
      }
      auto it = vocab_.find(pair.first);
      if (it != vocab_.end()) {
        document_frequency_[it->second]++;
      }
    }

    documents_.push_back(std::move(entry));
    index_dirty_ = true;
  }

  // --- Rebuild TF-IDF vectors ---
  void rebuild() {
    if (!index_dirty_)
      return;

    size_t n_docs = documents_.size();
    size_t vocab_size = vocab_.size();

    for (auto &doc : documents_) {
      doc.tfidf_vector.assign(vocab_size, 0.0);

      auto tokens = tokenize(doc.raw_text);
      std::unordered_map<std::string, uint32_t> tf;
      for (const auto &tok : tokens) {
        tf[tok]++;
      }

      double max_tf = 0;
      for (const auto &p : tf) {
        if (p.second > max_tf)
          max_tf = p.second;
      }
      if (max_tf == 0)
        max_tf = 1;

      for (const auto &pair : tf) {
        auto it = vocab_.find(pair.first);
        if (it != vocab_.end()) {
          double term_freq = 0.5 + 0.5 * (pair.second / max_tf);
          double idf = std::log(static_cast<double>(n_docs + 1) /
                                (document_frequency_[it->second] + 1));
          doc.tfidf_vector[it->second] = term_freq * idf;
        }
      }

      // Precompute norm
      double norm_sq = 0;
      for (double v : doc.tfidf_vector) {
        norm_sq += v * v;
      }
      doc.norm = std::sqrt(norm_sq);
    }

    index_dirty_ = false;
  }

  // --- Cosine similarity between two vectors ---
  static double cosine_similarity(const std::vector<double> &a, double norm_a,
                                  const std::vector<double> &b, double norm_b) {
    if (norm_a < 1e-10 || norm_b < 1e-10)
      return 0.0;

    size_t n = std::min(a.size(), b.size());
    double dot = 0.0;
    for (size_t i = 0; i < n; ++i) {
      dot += a[i] * b[i];
    }
    return dot / (norm_a * norm_b);
  }

  // --- Query: find most similar documents ---
  struct SimilarityMatch {
    std::string doc_id;
    double similarity;
  };

  std::vector<SimilarityMatch> query(const std::string &text,
                                     size_t top_k = 10) {
    if (index_dirty_)
      rebuild();

    // Build query vector
    auto tokens = tokenize(text);
    std::unordered_map<std::string, uint32_t> tf;
    for (const auto &tok : tokens)
      tf[tok]++;

    double max_tf = 0;
    for (const auto &p : tf) {
      if (p.second > max_tf)
        max_tf = p.second;
    }
    if (max_tf == 0)
      max_tf = 1;

    std::vector<double> query_vec(vocab_.size(), 0.0);
    for (const auto &pair : tf) {
      auto it = vocab_.find(pair.first);
      if (it != vocab_.end()) {
        double term_freq = 0.5 + 0.5 * (pair.second / max_tf);
        double idf = std::log(static_cast<double>(documents_.size() + 1) /
                              (document_frequency_[it->second] + 1));
        query_vec[it->second] = term_freq * idf;
      }
    }

    double query_norm = 0;
    for (double v : query_vec)
      query_norm += v * v;
    query_norm = std::sqrt(query_norm);

    // Compute similarities
    std::vector<SimilarityMatch> matches;
    for (const auto &doc : documents_) {
      double sim =
          cosine_similarity(query_vec, query_norm, doc.tfidf_vector, doc.norm);
      if (sim > 0.01) {
        matches.push_back({doc.doc_id, sim});
      }
    }

    // Sort by similarity descending
    std::sort(matches.begin(), matches.end(),
              [](const SimilarityMatch &a, const SimilarityMatch &b) {
                return a.similarity > b.similarity;
              });

    if (matches.size() > top_k) {
      matches.resize(top_k);
    }
    return matches;
  }

  size_t document_count() const { return documents_.size(); }
  size_t vocabulary_size() const { return vocab_.size(); }

  // --- Self-test ---
  static bool run_tests() {
    SimilarityIndex idx;
    int passed = 0, failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (cond) {
        ++passed;
      } else {
        ++failed;
      }
    };

    // Add similar documents
    idx.add_document("CVE-2024-0001",
                     "SQL injection vulnerability in login form allows "
                     "authentication bypass");
    idx.add_document("CVE-2024-0002",
                     "Cross-site scripting XSS vulnerability in search "
                     "input field");
    idx.add_document("CVE-2024-0003",
                     "SQL injection in authentication module allows "
                     "database access bypass");

    idx.rebuild();

    test(idx.document_count() == 3, "Should have 3 documents");
    test(idx.vocabulary_size() > 5, "Should have vocabulary");

    // Query: similar to SQL injection
    auto matches = idx.query("SQL injection in login authentication bypass", 3);
    test(!matches.empty(), "Should find matches");

    if (!matches.empty()) {
      // CVE-0001 or CVE-0003 should be most similar
      test(matches[0].doc_id == "CVE-2024-0001" ||
               matches[0].doc_id == "CVE-2024-0003",
           "SQL injection should match SQL injection CVEs");
      test(matches[0].similarity > 0.5, "High similarity expected");
    }

    // Query: XSS should match CVE-0002
    auto xss_matches = idx.query("XSS cross site scripting", 3);
    test(!xss_matches.empty(), "Should find XSS matches");

    return failed == 0;
  }
};

} // namespace duplicate_engine
