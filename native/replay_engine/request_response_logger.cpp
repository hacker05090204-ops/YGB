/*
 * request_response_logger.cpp — HTTP Request/Response Pair Logger
 *
 * Captures full HTTP request/response pairs with timing.
 * Content is truncated to prevent memory abuse.
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int MAX_PAIRS = 5000;
static constexpr int MAX_URL = 1024;
static constexpr int MAX_HEADERS = 4096;
static constexpr int MAX_BODY = 8192;

// =========================================================================
// TYPES
// =========================================================================

enum class HttpMethod { GET, POST, PUT, DELETE_M, PATCH, HEAD, OPTIONS };

struct HttpPair {
  int sequence;
  int parent_step;
  time_t timestamp;

  // Request
  HttpMethod method;
  char url[MAX_URL];
  char request_headers[MAX_HEADERS];
  char request_body[MAX_BODY];
  int request_body_length;

  // Response
  int status_code;
  char response_headers[MAX_HEADERS];
  char response_body[MAX_BODY];
  int response_body_length;

  // Timing
  double elapsed_ms;
};

// =========================================================================
// REQUEST/RESPONSE LOGGER
// =========================================================================

class RequestResponseLogger {
private:
  HttpPair pairs_[MAX_PAIRS];
  int pair_count_;

public:
  RequestResponseLogger() : pair_count_(0) {
    std::memset(pairs_, 0, sizeof(pairs_));
  }

  bool log_pair(int parent_step, HttpMethod method, const char *url,
                const char *req_headers, const char *req_body, int req_len,
                int status_code, const char *resp_headers,
                const char *resp_body, int resp_len, double elapsed_ms) {
    if (pair_count_ >= MAX_PAIRS)
      return false;

    HttpPair &p = pairs_[pair_count_];
    p.sequence = pair_count_;
    p.parent_step = parent_step;
    p.timestamp = std::time(nullptr);
    p.method = method;
    p.status_code = status_code;
    p.elapsed_ms = elapsed_ms;

    std::strncpy(p.url, url ? url : "", MAX_URL - 1);
    std::strncpy(p.request_headers, req_headers ? req_headers : "", MAX_HEADERS - 1);

    // Truncate body to prevent abuse
    int safe_req = req_len < MAX_BODY - 1 ? req_len : MAX_BODY - 1;
    if (req_body && safe_req > 0)
      std::memcpy(p.request_body, req_body, safe_req);
    p.request_body_length = safe_req;

    std::strncpy(p.response_headers, resp_headers ? resp_headers : "",
            MAX_HEADERS - 1);

    int safe_resp = resp_len < MAX_BODY - 1 ? resp_len : MAX_BODY - 1;
    if (resp_body && safe_resp > 0)
      std::memcpy(p.response_body, resp_body, safe_resp);
    p.response_body_length = safe_resp;

    pair_count_++;
    return true;
  }

  int pair_count() const { return pair_count_; }

  const HttpPair *get_pair(int i) const {
    return (i >= 0 && i < pair_count_) ? &pairs_[i] : nullptr;
  }

  int get_pairs_for_step(int step, const HttpPair **out, int max_out) const {
    int count = 0;
    for (int i = 0; i < pair_count_ && count < max_out; i++) {
      if (pairs_[i].parent_step == step)
        out[count++] = &pairs_[i];
    }
    return count;
  }

  int count_by_status(int status) const {
    int c = 0;
    for (int i = 0; i < pair_count_; i++)
      if (pairs_[i].status_code == status)
        c++;
    return c;
  }

  double total_elapsed_ms() const {
    double t = 0;
    for (int i = 0; i < pair_count_; i++)
      t += pairs_[i].elapsed_ms;
    return t;
  }

  // Guards
  static bool can_modify_pair() { return false; }
  static bool can_delete_pair() { return false; }
};
