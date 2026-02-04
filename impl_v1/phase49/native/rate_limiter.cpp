// rate_limiter.cpp
// Phase-49: Rate Limiter Implementation

#include "rate_limiter.h"
#include <algorithm>
#include <cstring>

namespace phase49 {

RateLimiter::RateLimiter() : initialized_(false) {}

RateLimiter::~RateLimiter() = default;

bool RateLimiter::initialize(const RateLimiterConfig &config) {
  config_ = config;
  domain_states_.clear();
  initialized_ = true;
  return true;
}

RateLimiter::DomainState *
RateLimiter::get_or_create_state(const std::string &domain) {
  for (auto &pair : domain_states_) {
    if (pair.first == domain) {
      return &pair.second;
    }
  }

  DomainState state;
  state.tokens = static_cast<double>(config_.burst_size);
  state.last_update = std::chrono::steady_clock::now();
  state.consecutive_429s = 0;
  state.backoff_until_ms = 0;
  state.total_requests = 0;
  state.throttle_count = 0;

  domain_states_.push_back({domain, state});
  return &domain_states_.back().second;
}

void RateLimiter::refill_tokens(DomainState &state) {
  auto now = std::chrono::steady_clock::now();
  auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
                     now - state.last_update)
                     .count();

  // Calculate tokens to add
  double tokens_to_add = (elapsed / 1000.0) * config_.requests_per_second;
  state.tokens = std::min(state.tokens + tokens_to_add,
                          static_cast<double>(config_.burst_size));
  state.last_update = now;
}

RateLimitStatus RateLimiter::check_request(const std::string &domain) {
  if (!initialized_) {
    return RateLimitStatus::BLOCKED;
  }

  DomainState *state = get_or_create_state(domain);

  // Check if in backoff period
  auto now_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now().time_since_epoch())
                    .count();

  if (state->backoff_until_ms > 0 &&
      static_cast<uint64_t>(now_ms) < state->backoff_until_ms) {
    return RateLimitStatus::BACKING_OFF;
  }

  // Refill tokens
  refill_tokens(*state);

  // Check if we have tokens
  if (state->tokens >= 1.0) {
    state->tokens -= 1.0;
    state->total_requests++;
    return RateLimitStatus::ALLOWED;
  }

  state->throttle_count++;
  return RateLimitStatus::THROTTLED;
}

void RateLimiter::record_response(const std::string &domain, int status_code) {
  if (!initialized_) {
    return;
  }

  DomainState *state = get_or_create_state(domain);

  if (status_code == 429) {
    // Rate limited - exponential backoff
    state->consecutive_429s++;

    int backoff = config_.backoff_seconds;
    for (int i = 1; i < state->consecutive_429s && i < 10; i++) {
      backoff *= 2;
    }
    backoff = std::min(backoff, config_.max_backoff_seconds);

    auto now_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                      std::chrono::steady_clock::now().time_since_epoch())
                      .count();
    state->backoff_until_ms = now_ms + (backoff * 1000);

    // Adaptive: reduce rate
    if (config_.adaptive && config_.requests_per_second > 1) {
      config_.requests_per_second =
          std::max(1, config_.requests_per_second / 2);
    }
  } else if (status_code >= 200 && status_code < 400) {
    // Success - reset consecutive 429s
    state->consecutive_429s = 0;

    // Adaptive: slowly increase rate if under limit
    if (config_.adaptive && state->consecutive_429s == 0 &&
        state->total_requests % 100 == 0) {
      config_.requests_per_second =
          std::min(10, config_.requests_per_second + 1);
    }
  }
}

uint64_t RateLimiter::get_delay_ms(const std::string &domain) const {
  if (!initialized_) {
    return 1000;
  }

  for (const auto &pair : domain_states_) {
    if (pair.first == domain) {
      // Check if in backoff
      auto now_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                        std::chrono::steady_clock::now().time_since_epoch())
                        .count();

      if (pair.second.backoff_until_ms > 0 &&
          static_cast<uint64_t>(now_ms) < pair.second.backoff_until_ms) {
        return pair.second.backoff_until_ms - now_ms;
      }

      // Calculate delay based on token availability
      if (pair.second.tokens < 1.0) {
        return static_cast<uint64_t>((1.0 - pair.second.tokens) /
                                     config_.requests_per_second * 1000);
      }
      return 0;
    }
  }

  return 0;
}

void RateLimiter::reset(const std::string &domain) {
  for (auto it = domain_states_.begin(); it != domain_states_.end(); ++it) {
    if (it->first == domain) {
      domain_states_.erase(it);
      return;
    }
  }
}

int RateLimiter::get_requests_made(const std::string &domain) const {
  for (const auto &pair : domain_states_) {
    if (pair.first == domain) {
      return pair.second.total_requests;
    }
  }
  return 0;
}

int RateLimiter::get_throttle_count(const std::string &domain) const {
  for (const auto &pair : domain_states_) {
    if (pair.first == domain) {
      return pair.second.throttle_count;
    }
  }
  return 0;
}

// C interface
extern "C" {

void *rate_limiter_create() { return new RateLimiter(); }

void rate_limiter_destroy(void *limiter) {
  delete static_cast<RateLimiter *>(limiter);
}

int rate_limiter_init(void *limiter, int rps, int burst, int backoff,
                      int max_backoff, int adaptive) {
  if (!limiter)
    return -1;

  RateLimiterConfig config;
  config.requests_per_second = rps > 0 ? rps : 1;
  config.burst_size = burst > 0 ? burst : 5;
  config.backoff_seconds = backoff > 0 ? backoff : 5;
  config.max_backoff_seconds = max_backoff > 0 ? max_backoff : 300;
  config.adaptive = adaptive != 0;

  return static_cast<RateLimiter *>(limiter)->initialize(config) ? 0 : -1;
}

int rate_limiter_check(void *limiter, const char *domain) {
  if (!limiter || !domain)
    return -1;
  return static_cast<int>(
      static_cast<RateLimiter *>(limiter)->check_request(domain));
}

void rate_limiter_record(void *limiter, const char *domain, int status_code) {
  if (!limiter || !domain)
    return;
  static_cast<RateLimiter *>(limiter)->record_response(domain, status_code);
}

uint64_t rate_limiter_get_delay(void *limiter, const char *domain) {
  if (!limiter || !domain)
    return 1000;
  return static_cast<RateLimiter *>(limiter)->get_delay_ms(domain);
}

} // extern "C"

} // namespace phase49
