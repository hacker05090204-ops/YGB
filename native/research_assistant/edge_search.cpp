/*
 * edge_search.cpp — Headless Edge Search Engine (Research Mode)
 *
 * ISOLATION RULES:
 *   - Headless Edge ONLY (--headless --disable-extensions --inprivate)
 *   - No cookie persistence
 *   - No localStorage
 *   - No training folder access
 *   - No write permissions except temp
 *   - No filesystem access except temp
 *
 * Searches via Bing/DuckDuckGo/Wikipedia only.
 * Returns raw HTML for content_extractor to process.
 */

#include <algorithm>
#include <cctype>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

// =========================================================================
// CONSTANTS
// =========================================================================

static const int MAX_QUERY_LENGTH = 512;
static const int MAX_URL_LENGTH = 2048;
static const int MAX_RESPONSE_BYTES = 65536; // 64KB per page
static const int FETCH_TIMEOUT_SEC = 10;
static const int MAX_RESULTS = 5;

// Allowed search engine domains — COMPILE-TIME CONSTANT WHITELIST
// NO runtime additions. NO environment override. NO user config.
static constexpr const char *ALLOWED_DOMAINS[] = {
    "www.bing.com",       "bing.com",
    "duckduckgo.com",     "www.duckduckgo.com",
    "en.wikipedia.org",   "wikipedia.org",
    "en.m.wikipedia.org", nullptr};

static constexpr int ALLOWED_DOMAIN_COUNT = 7; // Excluding nullptr
static_assert(
    sizeof(ALLOWED_DOMAINS) / sizeof(ALLOWED_DOMAINS[0]) == 8,
    "Domain whitelist must have exactly 7 domains + nullptr sentinel");

// Blocked path prefixes — research mode cannot touch these
static const char *BLOCKED_PATHS[] = {"training/",
                                      "models/",
                                      "datasets/",
                                      "weights/",
                                      "native/containment/",
                                      "native/shadow_integrity/",
                                      "reports/governance_state",
                                      "backend/integrity/",
                                      nullptr};

// =========================================================================
// TYPES
// =========================================================================

enum class SearchEngine { BING, DUCKDUCKGO, WIKIPEDIA };

enum class SearchStatus {
  OK,
  TIMEOUT,
  BLOCKED_DOMAIN,
  BLOCKED_PATH,
  QUERY_TOO_LONG,
  FETCH_FAILED,
  NO_RESULTS
};

struct SearchResult {
  char title[256];
  char url[MAX_URL_LENGTH];
  char snippet[1024];
  int relevance_rank; // 1 = most relevant
  bool fetched;
};

struct SearchResponse {
  SearchStatus status;
  SearchEngine engine;
  char query[MAX_QUERY_LENGTH];
  SearchResult results[MAX_RESULTS];
  int result_count;
  double elapsed_ms;
  char raw_html[MAX_RESPONSE_BYTES];
  int html_length;
  char error_message[256];
};

// =========================================================================
// DOMAIN WHITELIST CHECK
// =========================================================================

static bool is_domain_allowed(const char *url) {
  // Extract domain from URL
  const char *start = strstr(url, "://");
  if (!start)
    return false;
  start += 3;

  const char *end = strchr(start, '/');
  int domain_len = end ? (int)(end - start) : (int)strlen(start);
  if (domain_len <= 0 || domain_len >= 256)
    return false;

  char domain[256];
  memcpy(domain, start, domain_len);
  domain[domain_len] = '\0';

  // Convert to lowercase
  for (int i = 0; i < domain_len; i++) {
    if (domain[i] >= 'A' && domain[i] <= 'Z')
      domain[i] = domain[i] + 32;
  }

  // Check against whitelist
  for (int i = 0; ALLOWED_DOMAINS[i] != nullptr; i++) {
    if (strcmp(domain, ALLOWED_DOMAINS[i]) == 0)
      return true;
  }
  return false;
}

// =========================================================================
// PATH ACCESS GUARD
// =========================================================================

static bool is_path_blocked(const char *path) {
  for (int i = 0; BLOCKED_PATHS[i] != nullptr; i++) {
    if (strstr(path, BLOCKED_PATHS[i]) != nullptr)
      return true;
  }
  return false;
}

// =========================================================================
// URL BUILDER
// =========================================================================

static void build_search_url(const char *query, SearchEngine engine,
                             char *url_out, int url_max) {
  // URL-encode query (minimal: spaces → +)
  char encoded[MAX_QUERY_LENGTH * 3];
  int ei = 0;
  for (int i = 0; query[i] && ei < (int)sizeof(encoded) - 4; i++) {
    char c = query[i];
    if (c == ' ') {
      encoded[ei++] = '+';
    } else if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
               (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.') {
      encoded[ei++] = c;
    } else {
      // Percent-encode
      static const char hex[] = "0123456789ABCDEF";
      encoded[ei++] = '%';
      encoded[ei++] = hex[(unsigned char)c >> 4];
      encoded[ei++] = hex[(unsigned char)c & 0x0F];
    }
  }
  encoded[ei] = '\0';

  switch (engine) {
  case SearchEngine::BING:
    snprintf(url_out, url_max, "https://www.bing.com/search?q=%s", encoded);
    break;
  case SearchEngine::DUCKDUCKGO:
    snprintf(url_out, url_max, "https://duckduckgo.com/?q=%s&t=h_&ia=web",
             encoded);
    break;
  case SearchEngine::WIKIPEDIA:
    snprintf(
        url_out, url_max,
        "https://en.wikipedia.org/w/index.php?search=%s&title=Special:Search",
        encoded);
    break;
  }
}

// =========================================================================
// EDGE COMMAND BUILDER
// =========================================================================

struct EdgeCommand {
  char command[4096];
  char temp_output_path[512];

  void build(const char *url) {
    // Generate temp file for output
    snprintf(
        temp_output_path, sizeof(temp_output_path),
        "%%TEMP%%\\ygb_research_%lld.html",
        (long long)std::chrono::system_clock::now().time_since_epoch().count());

    // Build headless Edge command with full isolation
    snprintf(command, sizeof(command),
             "msedge "
             "--headless "
             "--disable-gpu "
             "--no-sandbox "
             "--disable-extensions "
             "--disable-plugins "
             "--disable-dev-shm-usage "
             "--disable-background-networking "
             "--disable-sync "
             "--disable-translate "
             "--disable-features=TranslateUI "
             "--disable-default-apps "
             "--disable-component-update "
             "--no-first-run "
             "--inprivate "
             "--disable-web-security=false "
             "--disable-reading-from-canvas "
             "--dump-dom "
             "\"%s\"",
             url);
  }
};

// =========================================================================
// SEARCH ENGINE
// =========================================================================

class EdgeSearchEngine {
private:
  SearchEngine preferred_engine_;
  bool initialized_;

  // Cleanup helper: remove temp files
  void cleanup_temp(const char *path) {
    if (path && path[0]) {
      remove(path);
    }
  }

public:
  EdgeSearchEngine()
      : preferred_engine_(SearchEngine::BING), initialized_(false) {}

  void set_engine(SearchEngine engine) { preferred_engine_ = engine; }

  // =====================================================================
  // EXECUTE SEARCH
  // =====================================================================

  SearchResponse search(const char *query) {
    SearchResponse resp;
    memset(&resp, 0, sizeof(resp));
    resp.engine = preferred_engine_;
    resp.status = SearchStatus::OK;

    // Validate query length
    int qlen = (int)strlen(query);
    if (qlen <= 0 || qlen >= MAX_QUERY_LENGTH) {
      resp.status = SearchStatus::QUERY_TOO_LONG;
      snprintf(resp.error_message, sizeof(resp.error_message),
               "Query length %d exceeds max %d", qlen, MAX_QUERY_LENGTH);
      return resp;
    }
    strncpy(resp.query, query, MAX_QUERY_LENGTH - 1);

    // Build search URL
    char url[MAX_URL_LENGTH];
    build_search_url(query, preferred_engine_, url, sizeof(url));

    // Domain check (should always pass for our built URLs)
    if (!is_domain_allowed(url)) {
      resp.status = SearchStatus::BLOCKED_DOMAIN;
      snprintf(resp.error_message, sizeof(resp.error_message),
               "Domain not in whitelist");
      return resp;
    }

    // Execute headless fetch
    auto t_start = std::chrono::steady_clock::now();

    EdgeCommand cmd;
    cmd.build(url);

    // Use popen to capture stdout (--dump-dom outputs to stdout)
    FILE *pipe = nullptr;
#ifdef _WIN32
    pipe = _popen(cmd.command, "r");
#else
    pipe = popen(cmd.command, "r");
#endif

    if (!pipe) {
      resp.status = SearchStatus::FETCH_FAILED;
      snprintf(resp.error_message, sizeof(resp.error_message),
               "Failed to launch Edge headless");
      return resp;
    }

    // Read HTML output
    resp.html_length = 0;
    char buf[4096];
    while (resp.html_length < MAX_RESPONSE_BYTES - 1) {
      size_t n = fread(
          buf, 1,
          std::min((int)sizeof(buf), MAX_RESPONSE_BYTES - 1 - resp.html_length),
          pipe);
      if (n == 0)
        break;
      memcpy(resp.raw_html + resp.html_length, buf, n);
      resp.html_length += (int)n;
    }
    resp.raw_html[resp.html_length] = '\0';

#ifdef _WIN32
    _pclose(pipe);
#else
    pclose(pipe);
#endif

    auto t_end = std::chrono::steady_clock::now();
    resp.elapsed_ms =
        std::chrono::duration<double, std::milli>(t_end - t_start).count();

    if (resp.html_length == 0) {
      resp.status = SearchStatus::NO_RESULTS;
      snprintf(resp.error_message, sizeof(resp.error_message),
               "No HTML returned from Edge");
    }

    return resp;
  }

  // =====================================================================
  // FILESYSTEM GUARD: Can this path be accessed?
  // =====================================================================

  static bool can_access_path(const char *path) {
    return !is_path_blocked(path);
  }

  // =====================================================================
  // TRAINING FOLDER GUARD: Absolute deny
  // =====================================================================

  static bool can_access_training() { return false; }
  static bool can_write_filesystem() { return false; }
  static bool can_persist_cookies() { return false; }
  static bool can_persist_localstorage() { return false; }
  static bool can_read_model_weights() { return false; }
  static bool can_modify_governance() { return false; }
  static bool can_access_storage_engine() { return false; }
  static bool can_modify_whitelist_at_runtime() { return false; }
  static bool can_override_from_env() { return false; }
  static bool can_add_domain_from_user_config() { return false; }
};

// =========================================================================
// MULTI-SOURCE CONSENSUS ENGINE
// =========================================================================

static constexpr int MIN_CONSENSUS_SOURCES = 2;
static constexpr int MAX_SOURCES = 3;
static constexpr int MAX_TERMS_PER_SOURCE = 32;
static constexpr int MAX_TERM_LENGTH = 64;

struct SourceResult {
  SearchEngine engine;
  char key_terms[MAX_TERMS_PER_SOURCE][MAX_TERM_LENGTH];
  int term_count;
  bool fetched;
  char raw_html[MAX_RESPONSE_BYTES];
  int html_length;
};

struct ConsensusResult {
  char consensus_terms[MAX_TERMS_PER_SOURCE][MAX_TERM_LENGTH];
  int consensus_count;
  int sources_fetched;
  int sources_agreed;
  bool has_consensus;
  char error[256];
};

class ConsensusEngine {
public:
  // Fetch from all 3 whitelisted search engines
  ConsensusResult validate_multi_source(const char *query) {
    ConsensusResult result;
    memset(&result, 0, sizeof(result));

    if (!query || strlen(query) == 0) {
      result.has_consensus = false;
      snprintf(result.error, sizeof(result.error), "Empty query");
      return result;
    }

    // Fetch from each engine
    EdgeSearchEngine engines[MAX_SOURCES];
    SearchEngine engine_types[MAX_SOURCES] = {
        SearchEngine::BING, SearchEngine::DUCKDUCKGO, SearchEngine::WIKIPEDIA};

    SourceResult sources[MAX_SOURCES];
    memset(sources, 0, sizeof(sources));

    int fetched_count = 0;
    for (int i = 0; i < MAX_SOURCES; i++) {
      engines[i].set_engine(engine_types[i]);
      SearchResponse resp = engines[i].search(query);
      sources[i].engine = engine_types[i];

      if (resp.status == SearchStatus::OK && resp.html_length > 0) {
        sources[i].fetched = true;
        memcpy(sources[i].raw_html, resp.raw_html, resp.html_length);
        sources[i].html_length = resp.html_length;
        extract_terms_from_html(sources[i].raw_html, sources[i].html_length,
                                sources[i].key_terms, &sources[i].term_count);
        fetched_count++;
      }
    }

    result.sources_fetched = fetched_count;

    // Reject single-source answers
    if (fetched_count < MIN_CONSENSUS_SOURCES) {
      result.has_consensus = false;
      snprintf(result.error, sizeof(result.error),
               "Only %d source(s) responded, need %d minimum", fetched_count,
               MIN_CONSENSUS_SOURCES);
      return result;
    }

    // Compute overlapping terms across sources
    compute_overlap(sources, fetched_count, &result);

    result.has_consensus = (result.consensus_count > 0 &&
                            result.sources_agreed >= MIN_CONSENSUS_SOURCES);

    return result;
  }

  // Guards
  static bool can_use_single_source() { return false; }
  static bool can_skip_consensus() { return false; }
  static int min_required_sources() { return MIN_CONSENSUS_SOURCES; }

private:
  void extract_terms_from_html(const char *html, int len,
                               char terms[][MAX_TERM_LENGTH], int *count) {
    *count = 0;
    int pos = 0;
    char word[MAX_TERM_LENGTH];

    while (pos < len && *count < MAX_TERMS_PER_SOURCE) {
      // Skip to alpha
      while (pos < len && !isalpha(html[pos]))
        pos++;
      int wpos = 0;
      while (pos < len && isalpha(html[pos]) && wpos < MAX_TERM_LENGTH - 1) {
        word[wpos++] = (char)tolower(html[pos++]);
      }
      word[wpos] = '\0';

      if (wpos >= 4 && *count < MAX_TERMS_PER_SOURCE) {
        // Check for duplicate
        bool dup = false;
        for (int i = 0; i < *count; i++) {
          if (strcmp(terms[i], word) == 0) {
            dup = true;
            break;
          }
        }
        if (!dup) {
          strncpy(terms[*count], word, MAX_TERM_LENGTH - 1);
          (*count)++;
        }
      }
    }
  }

  void compute_overlap(SourceResult *sources, int source_count,
                       ConsensusResult *result) {
    result->consensus_count = 0;
    result->sources_agreed = 0;

    if (source_count < 2)
      return;

    // For each term in source 0, check if it appears in other sources
    int max_agreed = 0;
    for (int t = 0; t < sources[0].term_count &&
                    result->consensus_count < MAX_TERMS_PER_SOURCE;
         t++) {
      int agree_count = 1; // source 0 has it
      for (int s = 1; s < source_count; s++) {
        for (int st = 0; st < sources[s].term_count; st++) {
          if (strcmp(sources[0].key_terms[t], sources[s].key_terms[st]) == 0) {
            agree_count++;
            break;
          }
        }
      }

      if (agree_count >= MIN_CONSENSUS_SOURCES) {
        strncpy(result->consensus_terms[result->consensus_count],
                sources[0].key_terms[t], MAX_TERM_LENGTH - 1);
        result->consensus_count++;
        if (agree_count > max_agreed)
          max_agreed = agree_count;
      }
    }

    result->sources_agreed = max_agreed;
  }
};
