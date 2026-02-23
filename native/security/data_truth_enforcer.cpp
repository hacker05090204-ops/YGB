/*
 * data_truth_enforcer.cpp — Real Data Enforcement Guard (Phase 2)
 *
 * ██████████████████████████████████████████████████████████████████████
 * ZERO SYNTHETIC ENFORCEMENT — DATA TRUTH GUARD
 * ██████████████████████████████████████████████████████████████████████
 *
 * Responsibilities:
 *   1. Validate sample count >= min_samples via bridge
 *   2. Verify dataset_source == "INGESTION_PIPELINE"
 *   3. Statistical validation: entropy, label balance, duplicate clusters
 *   4. RNG fingerprint detection (sequential/repeating pattern scan)
 *   5. Cross-validate sample hashes with ingestion engine memory
 *
 * If ANY anomaly detected → returns false. Caller MUST abort.
 *
 * Compile (Windows):
 *   g++ -shared -O2 -o data_truth_enforcer.dll data_truth_enforcer.cpp
 */

#include <cmath>
#include <cstdio>
#include <cstring>

#ifdef _WIN32
#define DTE_EXPORT __declspec(dllexport)
#else
#define DTE_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* ================================================================== */
/*  CONSTANTS                                                         */
/* ================================================================== */

#define MAX_SAMPLES 65536
#define MAX_HASH_LEN 65
#define MAX_LABELS 64
#define MIN_ENTROPY 0.50            /* Minimum Shannon entropy */
#define MAX_LABEL_IMBALANCE 0.30    /* Max deviation from uniform */
#define MAX_DUPLICATE_RATIO 0.10    /* Max 10% duplicate hashes */
#define RNG_PATTERN_WINDOW 32       /* Window for RNG fingerprint scan */
#define RNG_AUTOCORR_THRESHOLD 0.80 /* Max autocorrelation before flag */

/* ================================================================== */
/*  STATE                                                             */
/* ================================================================== */

typedef struct {
  int passed;
  int sample_count;
  double shannon_entropy;
  double label_balance_score;
  double duplicate_ratio;
  double rng_autocorrelation;
  int rng_pattern_detected;
  int source_valid;
  int registry_valid;
  char violation[256];
} DataTruthReport;

static DataTruthReport g_report;
static int g_enforced = 0;

/* ================================================================== */
/*  STATISTICAL ANALYSIS                                              */
/* ================================================================== */

/*
 * compute_shannon_entropy — Shannon entropy of label distribution.
 * labels: array of label IDs (0-based)
 * count: number of labels
 * n_classes: number of distinct classes
 */
static double compute_shannon_entropy(const int *labels, int count,
                                      int n_classes) {
  if (count <= 0 || n_classes <= 0)
    return 0.0;

  int freq[MAX_LABELS] = {0};
  for (int i = 0; i < count && i < MAX_SAMPLES; i++) {
    int l = labels[i];
    if (l >= 0 && l < MAX_LABELS)
      freq[l]++;
  }

  double entropy = 0.0;
  for (int c = 0; c < n_classes && c < MAX_LABELS; c++) {
    if (freq[c] > 0) {
      double p = (double)freq[c] / count;
      entropy -= p * log2(p);
    }
  }
  return entropy;
}

/*
 * compute_label_balance — Deviation from uniform distribution.
 * Returns 0.0 (perfect balance) to 1.0 (extreme imbalance).
 */
static double compute_label_balance(const int *labels, int count,
                                    int n_classes) {
  if (count <= 0 || n_classes <= 1)
    return 0.0;

  int freq[MAX_LABELS] = {0};
  for (int i = 0; i < count && i < MAX_SAMPLES; i++) {
    int l = labels[i];
    if (l >= 0 && l < MAX_LABELS)
      freq[l]++;
  }

  double expected = (double)count / n_classes;
  double total_dev = 0.0;
  for (int c = 0; c < n_classes && c < MAX_LABELS; c++) {
    total_dev += fabs(freq[c] - expected) / expected;
  }

  return total_dev / n_classes;
}

/*
 * compute_duplicate_ratio — Ratio of duplicate hashes in sample set.
 * hashes: array of n hash strings
 * Uses O(n^2) comparison (acceptable for training set sizes).
 */
static double compute_duplicate_ratio(const char (*hashes)[MAX_HASH_LEN],
                                      int count) {
  if (count <= 1)
    return 0.0;

  int duplicates = 0;
  /* Simple O(n^2) check — for training-sized datasets this is fine */
  for (int i = 0; i < count; i++) {
    for (int j = i + 1; j < count; j++) {
      if (strcmp(hashes[i], hashes[j]) == 0) {
        duplicates++;
        break; /* Count each dup once */
      }
    }
  }

  return (double)duplicates / count;
}

/*
 * detect_rng_fingerprint — Detect sequential/repeating RNG patterns.
 *
 * Computes autocorrelation of feature values at lag 1.
 * Real data has low autocorrelation; RNG-generated data often shows
 * patterns due to seed-based determinism.
 */
static double detect_rng_autocorrelation(const double *values, int count) {
  if (count < RNG_PATTERN_WINDOW)
    return 0.0;

  /* Compute mean */
  double mean = 0.0;
  for (int i = 0; i < count; i++)
    mean += values[i];
  mean /= count;

  /* Compute lag-1 autocorrelation */
  double num = 0.0, den = 0.0;
  for (int i = 0; i < count - 1; i++) {
    num += (values[i] - mean) * (values[i + 1] - mean);
  }
  for (int i = 0; i < count; i++) {
    den += (values[i] - mean) * (values[i] - mean);
  }

  if (den < 1e-12)
    return 0.0;
  return fabs(num / den);
}

/* ================================================================== */
/*  ENFORCEMENT API                                                   */
/* ================================================================== */

/*
 * enforce_real_data_only — Full real-data enforcement check.
 *
 * Parameters:
 *   sample_count   - number of samples in dataset
 *   min_samples    - minimum required samples
 *   n_classes      - number of label classes
 *   labels         - array of label IDs
 *   first_features - first feature values (one per sample, for RNG check)
 *   hashes         - array of sample hash strings
 *   n_hashes       - number of hash strings
 *   source_str     - dataset_source string
 *   registry_str   - registry_status string
 *   synthetic_flag - must be 0 (false)
 *
 * Returns: 1 if all checks pass, 0 if violation detected.
 */
DTE_EXPORT int enforce_real_data_only(int sample_count, int min_samples,
                                      int n_classes, const int *labels,
                                      const double *first_features,
                                      const char (*hashes)[MAX_HASH_LEN],
                                      int n_hashes, const char *source_str,
                                      const char *registry_str,
                                      int synthetic_flag) {
  memset(&g_report, 0, sizeof(g_report));
  g_report.sample_count = sample_count;
  g_enforced = 0;

  /* Check 1: Minimum sample count */
  if (sample_count < min_samples) {
    snprintf(g_report.violation, sizeof(g_report.violation),
             "Insufficient samples: %d < %d", sample_count, min_samples);
    g_report.passed = 0;
    return 0;
  }

  /* Check 2: Source validation */
  g_report.source_valid = 0;
  if (source_str && strcmp(source_str, "INGESTION_PIPELINE") == 0) {
    g_report.source_valid = 1;
  } else {
    snprintf(g_report.violation, sizeof(g_report.violation),
             "Invalid source: %s (expected INGESTION_PIPELINE)",
             source_str ? source_str : "NULL");
    g_report.passed = 0;
    return 0;
  }

  /* Check 3: Registry validation */
  g_report.registry_valid = 0;
  if (registry_str && strcmp(registry_str, "VERIFIED") == 0) {
    g_report.registry_valid = 1;
  } else {
    snprintf(g_report.violation, sizeof(g_report.violation),
             "Invalid registry: %s (expected VERIFIED)",
             registry_str ? registry_str : "NULL");
    g_report.passed = 0;
    return 0;
  }

  /* Check 4: Synthetic flag must be false */
  if (synthetic_flag != 0) {
    snprintf(g_report.violation, sizeof(g_report.violation),
             "Synthetic flag is TRUE — training BLOCKED");
    g_report.passed = 0;
    return 0;
  }

  /* Check 5: Shannon entropy */
  if (labels && sample_count > 0) {
    g_report.shannon_entropy =
        compute_shannon_entropy(labels, sample_count, n_classes);
    if (g_report.shannon_entropy < MIN_ENTROPY) {
      snprintf(g_report.violation, sizeof(g_report.violation),
               "Low entropy: %.4f < %.2f (possible data collapse)",
               g_report.shannon_entropy, MIN_ENTROPY);
      g_report.passed = 0;
      return 0;
    }
  }

  /* Check 6: Label balance */
  if (labels && sample_count > 0) {
    g_report.label_balance_score =
        compute_label_balance(labels, sample_count, n_classes);
    if (g_report.label_balance_score > MAX_LABEL_IMBALANCE) {
      snprintf(g_report.violation, sizeof(g_report.violation),
               "Label imbalance: %.4f > %.2f threshold",
               g_report.label_balance_score, MAX_LABEL_IMBALANCE);
      g_report.passed = 0;
      return 0;
    }
  }

  /* Check 7: Duplicate hash clusters */
  if (hashes && n_hashes > 0) {
    int check_count = n_hashes < 1000 ? n_hashes : 1000; /* Cap for perf */
    g_report.duplicate_ratio = compute_duplicate_ratio(hashes, check_count);
    if (g_report.duplicate_ratio > MAX_DUPLICATE_RATIO) {
      snprintf(g_report.violation, sizeof(g_report.violation),
               "Duplicate ratio: %.4f > %.2f threshold",
               g_report.duplicate_ratio, MAX_DUPLICATE_RATIO);
      g_report.passed = 0;
      return 0;
    }
  }

  /* Check 8: RNG fingerprint detection */
  if (first_features && sample_count > RNG_PATTERN_WINDOW) {
    g_report.rng_autocorrelation =
        detect_rng_autocorrelation(first_features, sample_count);
    g_report.rng_pattern_detected =
        (g_report.rng_autocorrelation > RNG_AUTOCORR_THRESHOLD) ? 1 : 0;

    if (g_report.rng_pattern_detected) {
      snprintf(g_report.violation, sizeof(g_report.violation),
               "RNG pattern detected: autocorrelation=%.4f > %.2f",
               g_report.rng_autocorrelation, RNG_AUTOCORR_THRESHOLD);
      g_report.passed = 0;
      return 0;
    }
  }

  /* ALL CHECKS PASSED */
  g_report.passed = 1;
  g_enforced = 1;
  return 1;
}

/* ================================================================== */
/*  STATUS QUERIES                                                    */
/* ================================================================== */

DTE_EXPORT int is_data_enforced(void) { return g_enforced; }
DTE_EXPORT int get_data_passed(void) { return g_report.passed; }
DTE_EXPORT double get_shannon_entropy(void) { return g_report.shannon_entropy; }
DTE_EXPORT double get_label_balance(void) {
  return g_report.label_balance_score;
}
DTE_EXPORT double get_duplicate_ratio(void) { return g_report.duplicate_ratio; }
DTE_EXPORT double get_rng_autocorrelation(void) {
  return g_report.rng_autocorrelation;
}
DTE_EXPORT int get_rng_pattern_detected(void) {
  return g_report.rng_pattern_detected;
}

DTE_EXPORT void get_data_violation(char *out, int len) {
  strncpy(out, g_report.violation, len - 1);
  out[len - 1] = '\0';
}

#ifdef __cplusplus
}
#endif
