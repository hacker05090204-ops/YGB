/*
 * likelihood_estimator.cpp — Vulnerability Likelihood Estimator
 *
 * Estimates vulnerability likelihood % and bounty range
 * based on scope complexity analysis (user-provided data only).
 * NO scraping — public policy info only.
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int MAX_TARGETS = 100;

// =========================================================================
// TYPES
// =========================================================================

enum class DifficultyLevel {
  LOW,    // < 30%
  MEDIUM, // 30-60%
  HIGH,   // 60-85%
  EXPERT  // > 85%
};

struct BountyRange {
  int min_usd;
  int max_usd;
};

struct TargetEstimate {
  char domain[256];
  char program_name[256];
  char platform[64];         // Informational only
  double likelihood_percent; // 0-100
  DifficultyLevel difficulty;
  BountyRange bounty_range;
  int scope_size; // Number of in-scope items
  int api_endpoint_count;
  int wildcard_count;
  bool has_mobile_app;
  bool is_public_program;
  char analysis[512];
};

// =========================================================================
// LIKELIHOOD ESTIMATOR
// =========================================================================

class LikelihoodEstimator {
private:
  static DifficultyLevel classify_difficulty(double pct) {
    if (pct < 30.0)
      return DifficultyLevel::LOW;
    if (pct < 60.0)
      return DifficultyLevel::MEDIUM;
    if (pct < 85.0)
      return DifficultyLevel::HIGH;
    return DifficultyLevel::EXPERT;
  }

  static BountyRange estimate_bounty(int scope_size, int api_count,
                                     bool is_public) {
    BountyRange r;
    // Heuristic based on scope complexity
    int base = scope_size * 50 + api_count * 100;
    if (!is_public)
      base = (int)(base * 1.5); // Private programs pay more
    r.min_usd = base > 100 ? 100 : base;
    r.max_usd = base > 100 ? base * 3 : 500;
    if (r.max_usd > 50000)
      r.max_usd = 50000;
    return r;
  }

public:
  LikelihoodEstimator() = default;

  TargetEstimate estimate(const char *domain, const char *program_name,
                          const char *platform, int scope_size,
                          int api_endpoint_count, int wildcard_count,
                          bool has_mobile, bool is_public) {
    TargetEstimate est;
    std::memset(&est, 0, sizeof(est));

    std::strncpy(est.domain, domain ? domain : "", sizeof(est.domain) - 1);
    std::strncpy(est.program_name, program_name ? program_name : "",
            sizeof(est.program_name) - 1);
    std::strncpy(est.platform, platform ? platform : "", sizeof(est.platform) - 1);

    est.scope_size = scope_size;
    est.api_endpoint_count = api_endpoint_count;
    est.wildcard_count = wildcard_count;
    est.has_mobile_app = has_mobile;
    est.is_public_program = is_public;

    // Likelihood heuristic
    double likelihood = 40.0; // Baseline

    // More API endpoints = higher likelihood
    likelihood += api_endpoint_count * 3.0;

    // Wildcards increase attack surface
    likelihood += wildcard_count * 5.0;

    // Large scope = more opportunity
    if (scope_size > 10)
      likelihood += 10.0;
    if (scope_size > 20)
      likelihood += 5.0;

    // Public programs are more heavily tested
    if (is_public)
      likelihood -= 15.0;

    // Cap at 95%
    if (likelihood > 95.0)
      likelihood = 95.0;
    if (likelihood < 5.0)
      likelihood = 5.0;

    est.likelihood_percent = likelihood;
    est.difficulty = classify_difficulty(likelihood);
    est.bounty_range =
        estimate_bounty(scope_size, api_endpoint_count, is_public);

    // Generate analysis text
    const char *diff_label = "Medium";
    switch (est.difficulty) {
    case DifficultyLevel::LOW:
      diff_label = "Low";
      break;
    case DifficultyLevel::MEDIUM:
      diff_label = "Medium";
      break;
    case DifficultyLevel::HIGH:
      diff_label = "High";
      break;
    case DifficultyLevel::EXPERT:
      diff_label = "Expert";
      break;
    }

    std::snprintf(est.analysis, sizeof(est.analysis),
             "%s: %d scope items, %d API endpoints, %d wildcards. "
             "Difficulty: %s. Estimated likelihood: %.0f%%. "
             "Bounty range: $%d - $%d.",
             est.domain, scope_size, api_endpoint_count, wildcard_count,
             diff_label, likelihood, est.bounty_range.min_usd,
             est.bounty_range.max_usd);

    return est;
  }

  // Guards
  static bool can_scrape_for_data() { return false; }
  static bool can_auto_select_target() { return false; }
};
