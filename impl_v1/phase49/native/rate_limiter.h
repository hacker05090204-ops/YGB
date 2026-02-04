// rate_limiter.h
// Phase-49: Adaptive Rate Limiting Engine
//
// STRICT RULES:
// - Platform-safe pacing
// - Respect 429 responses
// - No aggressive crawling

#ifndef PHASE49_RATE_LIMITER_H
#define PHASE49_RATE_LIMITER_H

#include <chrono>
#include <cstdint>
#include <string>

namespace phase49 {

// Rate limit status
enum class RateLimitStatus { ALLOWED, THROTTLED, BLOCKED, BACKING_OFF };

// Rate limiter config
struct RateLimiterConfig {
  int requests_per_second; // Default: 1
  int burst_size;          // Token bucket burst
  int backoff_seconds;     // Initial backoff on 429
  int max_backoff_seconds; // Max backoff
  bool adaptive;           // Adjust based on responses
};

// Rate limiter
class RateLimiter {
public:
  RateLimiter();
  ~RateLimiter();

  bool initialize(const RateLimiterConfig &config);

  // Check if request is allowed
  RateLimitStatus check_request(const std::string &domain);

  // Record response (for adaptive pacing)
  void record_response(const std::string &domain, int status_code);

  // Get current delay required
  uint64_t get_delay_ms(const std::string &domain) const;

  // Reset for domain
  void reset(const std::string &domain);

  // Get stats
  int get_requests_made(const std::string &domain) const;
  int get_throttle_count(const std::string &domain) const;

private:
  RateLimiterConfig config_;
  bool initialized_;

  // Token bucket per domain
  struct DomainState {
    double tokens;
    std::chrono::steady_clock::time_point last_update;
    int consecutive_429s;
    uint64_t backoff_until_ms;
    int total_requests;
    int throttle_count;
  };

  std::vector<std::pair<std::string, DomainState>> domain_states_;

  DomainState *get_or_create_state(const std::string &domain);
  void refill_tokens(DomainState &state);
};

// C interface
extern "C" {
void *rate_limiter_create();
void rate_limiter_destroy(void *limiter);
int rate_limiter_init(void *limiter, int rps, int burst, int backoff,
                      int max_backoff, int adaptive);
int rate_limiter_check(void *limiter, const char *domain);
void rate_limiter_record(void *limiter, const char *domain, int status_code);
uint64_t rate_limiter_get_delay(void *limiter, const char *domain);
}

} // namespace phase49

#endif // PHASE49_RATE_LIMITER_H
