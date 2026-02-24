/**
 * production_build_guard.cpp — Build-Time Protection (Phase 6)
 *
 * Enforces production build constraints:
 *   - PRODUCTION_BUILD flag from environment
 *   - Scans module names for forbidden mock/test patterns
 *   - Blocks synthetic datasets in production
 *   - Blocks mock governors
 *   - No test-mode bypass allowed
 *
 * Build:
 *   g++ -std=c++17 -shared -o production_build_guard.dll
 * production_build_guard.cpp
 */

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* ================================================================== */
/*  CONSTANTS                                                         */
/* ================================================================== */

static constexpr int MAX_VIOLATION_MSG = 512;
static constexpr int MAX_VIOLATIONS = 64;

/* Forbidden patterns in production builds */
static const char *FORBIDDEN_PATTERNS[] = {"MOCK_",
                                           "FAKE_",
                                           "DEMO_",
                                           "mock_data",
                                           "fake_data",
                                           "demo_data",
                                           "placeholder_data",
                                           "SyntheticTrainingDataset",
                                           "ScaledDatasetGenerator",
                                           "generate_fake",
                                           "generate_mock",
                                           "mock-signature",
                                           "test-signature",
                                           "fake-signature",
                                           nullptr};

/* Forbidden module imports in production */
static const char *FORBIDDEN_MODULES_PRODUCTION[] = {"g37_gpu_training_backend",
                                                     nullptr};

/* ================================================================== */
/*  STATE                                                             */
/* ================================================================== */

static int g_violation_count = 0;
static char g_violations[MAX_VIOLATIONS][MAX_VIOLATION_MSG];

static void add_violation(const char *msg) {
  if (g_violation_count < MAX_VIOLATIONS) {
    std::snprintf(g_violations[g_violation_count], MAX_VIOLATION_MSG, "%s",
                  msg);
    g_violation_count++;
  }
  std::fprintf(stderr, "[PRODUCTION_BUILD_GUARD] VIOLATION: %s\n", msg);
}

/* ================================================================== */
/*  PUBLIC API                                                        */
/* ================================================================== */

/**
 * Check if PRODUCTION_BUILD is enabled.
 * Reads from PRODUCTION_BUILD environment variable.
 * Returns: 1 if production build, 0 otherwise.
 */
EXPORT int is_production_build(void) {
  const char *val = std::getenv("PRODUCTION_BUILD");
  if (!val)
    return 0;
  return (std::strcmp(val, "1") == 0 || std::strcmp(val, "true") == 0 ||
          std::strcmp(val, "TRUE") == 0 || std::strcmp(val, "yes") == 0);
}

/**
 * Scan source content for forbidden production patterns.
 * content: source code text to scan.
 * filename: name of the file being scanned (for reporting).
 * Returns: number of violations found.
 */
EXPORT int scan_source_for_forbidden(const char *content,
                                     const char *filename) {
  if (!content || !filename)
    return 0;
  int violations = 0;

  for (int i = 0; FORBIDDEN_PATTERNS[i] != nullptr; i++) {
    if (std::strstr(content, FORBIDDEN_PATTERNS[i]) != nullptr) {
      char msg[MAX_VIOLATION_MSG];
      std::snprintf(msg, sizeof(msg), "Forbidden pattern '%s' found in %s",
                    FORBIDDEN_PATTERNS[i], filename);
      add_violation(msg);
      violations++;
    }
  }

  return violations;
}

/**
 * Enforce production mode constraints on loaded modules.
 * module_names: newline-separated list of loaded module names.
 * Returns: 1 if clean, 0 if violations detected (ABORT).
 */
EXPORT int enforce_production_mode(const char *module_names) {
  if (!is_production_build()) {
    /* Not production build — skip enforcement */
    return 1;
  }

  if (!module_names)
    return 1;
  int violations = 0;

  /* Check for mock/test patterns in module names */
  for (int i = 0; FORBIDDEN_PATTERNS[i] != nullptr; i++) {
    if (std::strstr(module_names, FORBIDDEN_PATTERNS[i]) != nullptr) {
      char msg[MAX_VIOLATION_MSG];
      std::snprintf(msg, sizeof(msg),
                    "PRODUCTION_BUILD: Forbidden module pattern '%s' loaded",
                    FORBIDDEN_PATTERNS[i]);
      add_violation(msg);
      violations++;
    }
  }

  /* Check for forbidden module imports */
  for (int i = 0; FORBIDDEN_MODULES_PRODUCTION[i] != nullptr; i++) {
    if (std::strstr(module_names, FORBIDDEN_MODULES_PRODUCTION[i]) != nullptr) {
      char msg[MAX_VIOLATION_MSG];
      std::snprintf(msg, sizeof(msg),
                    "PRODUCTION_BUILD: Forbidden module '%s' loaded",
                    FORBIDDEN_MODULES_PRODUCTION[i]);
      add_violation(msg);
      violations++;
    }
  }

  return violations == 0;
}

/**
 * Full production build check.
 * Combines module scan + environment validation.
 * Returns: 1 if all checks pass, 0 if any violation (FAIL-CLOSED).
 */
EXPORT int production_build_check(const char *module_names) {
  if (!is_production_build()) {
    /* Not in production mode — all checks pass by default */
    return 1;
  }

  int ok = 1;

  /* Check STRICT_REAL_MODE must be enabled */
  const char *srm = std::getenv("STRICT_REAL_MODE");
  if (srm && (std::strcmp(srm, "0") == 0 || std::strcmp(srm, "false") == 0 ||
              std::strcmp(srm, "FALSE") == 0)) {
    add_violation("PRODUCTION_BUILD: STRICT_REAL_MODE cannot be disabled");
    ok = 0;
  }

  /* Check JWT_SECRET exists and is not a placeholder */
  const char *jwt = std::getenv("JWT_SECRET");
  if (!jwt || std::strlen(jwt) < 32) {
    add_violation("PRODUCTION_BUILD: JWT_SECRET missing or too short");
    ok = 0;
  }

  /* Check module names */
  if (module_names && !enforce_production_mode(module_names)) {
    ok = 0;
  }

  return ok;
}

/**
 * Get number of recorded violations.
 */
EXPORT int get_violation_count(void) { return g_violation_count; }

/**
 * Get violation message by index.
 */
EXPORT int get_violation(int index, char *out, int len) {
  if (index < 0 || index >= g_violation_count)
    return 0;
  if (!out || len <= 0)
    return 0;
  std::snprintf(out, len, "%s", g_violations[index]);
  return (int)std::strlen(g_violations[index]);
}

/**
 * Reset all violations (testing only).
 */
EXPORT void reset_violations(void) { g_violation_count = 0; }

#ifdef __cplusplus
}
#endif
