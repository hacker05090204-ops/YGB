/**
 * real_data_enforcer.cpp — STRICT_REAL_MODE Dataset Enforcer (Phase 2)
 *
 * C++ enforcement of dataset contract in STRICT_REAL_MODE:
 *   - Abort if SyntheticTrainingDataset referenced
 *   - Abort if dataset missing SHA-256 provenance
 *   - Abort if source_id missing
 *   - Abort if sample count below minimum
 *   - No fallback allowed
 *
 * Build:
 *   g++ -std=c++17 -shared -o real_data_enforcer.dll real_data_enforcer.cpp
 *
 * STRICT_REAL_MODE is ALWAYS TRUE — hardcoded. No override.
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

static constexpr int MIN_SAMPLE_COUNT = 100;
static constexpr int SHA256_HEX_LEN = 64;
static constexpr int MAX_VIOLATION_MSG = 512;

/* Forbidden dataset class names */
static const char *FORBIDDEN_DATASETS[] = {
    "SyntheticTrainingDataset", "FakeDataset",   "MockDataset", "DemoDataset",
    "PlaceholderDataset",       "RandomDataset", nullptr};

/* Forbidden module patterns */
static const char *FORBIDDEN_MODULES[] = {
    "g37_gpu_training_backend", "ScaledDatasetGenerator", "numpy.random",
    "random.Random", nullptr};

/* ================================================================== */
/*  STATE                                                             */
/* ================================================================== */

static int g_violations = 0;
static char g_last_violation[MAX_VIOLATION_MSG] = {0};

static void record_violation(const char *msg) {
  g_violations++;
  std::snprintf(g_last_violation, MAX_VIOLATION_MSG, "%s", msg);
  std::fprintf(stderr, "[REAL_DATA_ENFORCER] VIOLATION: %s\n", msg);
}

/* ================================================================== */
/*  STRING HELPERS                                                    */
/* ================================================================== */

static int str_contains(const char *haystack, const char *needle) {
  return std::strstr(haystack, needle) != nullptr;
}

static int is_valid_sha256_hex(const char *hex) {
  if (!hex)
    return 0;
  int len = (int)std::strlen(hex);
  if (len != SHA256_HEX_LEN)
    return 0;
  for (int i = 0; i < len; i++) {
    char c = hex[i];
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') ||
          (c >= 'A' && c <= 'F')))
      return 0;
  }
  return 1;
}

/* ================================================================== */
/*  PUBLIC API                                                        */
/* ================================================================== */

/**
 * STRICT_REAL_MODE is ALWAYS TRUE. No override. No toggle.
 */
EXPORT int is_strict_real_mode(void) {
  return 1; /* HARDCODED TRUE — never changes */
}

/**
 * Check if loaded module names contain forbidden patterns.
 * module_names: newline-separated list of loaded module names.
 * Returns: number of violations (0 = clean).
 */
EXPORT int check_module_names(const char *module_names) {
  if (!module_names)
    return 0;
  int violations = 0;

  for (int i = 0; FORBIDDEN_DATASETS[i] != nullptr; i++) {
    if (str_contains(module_names, FORBIDDEN_DATASETS[i])) {
      char msg[MAX_VIOLATION_MSG];
      std::snprintf(msg, sizeof(msg),
                    "Forbidden dataset class detected in loaded modules: %s",
                    FORBIDDEN_DATASETS[i]);
      record_violation(msg);
      violations++;
    }
  }

  for (int i = 0; FORBIDDEN_MODULES[i] != nullptr; i++) {
    if (str_contains(module_names, FORBIDDEN_MODULES[i])) {
      char msg[MAX_VIOLATION_MSG];
      std::snprintf(msg, sizeof(msg), "Forbidden module detected: %s",
                    FORBIDDEN_MODULES[i]);
      record_violation(msg);
      violations++;
    }
  }

  return violations;
}

/**
 * Enforce dataset contract.
 *
 * provenance_hash: SHA-256 hex string of dataset provenance (64 chars).
 * source_id:       Non-empty source identifier string.
 * sample_count:    Number of samples in dataset.
 * dataset_class:   Name of the dataset class being used.
 *
 * Returns: 1 if contract satisfied, 0 if violated (ABORT).
 */
EXPORT int enforce_dataset_contract(const char *provenance_hash,
                                    const char *source_id, int sample_count,
                                    const char *dataset_class) {
  int valid = 1;

  /* Check dataset class name */
  if (dataset_class) {
    for (int i = 0; FORBIDDEN_DATASETS[i] != nullptr; i++) {
      if (std::strcmp(dataset_class, FORBIDDEN_DATASETS[i]) == 0) {
        char msg[MAX_VIOLATION_MSG];
        std::snprintf(msg, sizeof(msg),
                      "ABORT: Forbidden dataset class '%s' in STRICT_REAL_MODE",
                      dataset_class);
        record_violation(msg);
        valid = 0;
      }
    }
  }

  /* Check SHA-256 provenance hash */
  if (!provenance_hash || !is_valid_sha256_hex(provenance_hash)) {
    record_violation("ABORT: Dataset missing valid SHA-256 provenance hash");
    valid = 0;
  }

  /* Check source_id */
  if (!source_id || std::strlen(source_id) == 0) {
    record_violation("ABORT: Dataset missing source_id");
    valid = 0;
  }

  /* Check sample count */
  if (sample_count < MIN_SAMPLE_COUNT) {
    char msg[MAX_VIOLATION_MSG];
    std::snprintf(msg, sizeof(msg), "ABORT: Sample count %d below minimum %d",
                  sample_count, MIN_SAMPLE_COUNT);
    record_violation(msg);
    valid = 0;
  }

  return valid;
}

/**
 * Get total violation count.
 */
EXPORT int get_violation_count(void) { return g_violations; }

/**
 * Get last violation message.
 */
EXPORT int get_last_violation(char *out, int len) {
  if (!out || len <= 0)
    return 0;
  std::snprintf(out, len, "%s", g_last_violation);
  return (int)std::strlen(g_last_violation);
}

/**
 * Reset violation state (for testing ONLY — never call in production).
 */
EXPORT void reset_violations(void) {
  g_violations = 0;
  g_last_violation[0] = '\0';
}

/**
 * Get minimum required sample count.
 */
EXPORT int get_min_sample_count(void) { return MIN_SAMPLE_COUNT; }

#ifdef __cplusplus
}
#endif
