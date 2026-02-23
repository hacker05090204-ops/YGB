/*
 * signal_strength_validator.cpp — Data Quality Signal Validator (Phase 1)
 *
 * ██████████████████████████████████████████████████████████████████████
 * BOUNTY-READY DATA QUALITY — SIGNAL STRENGTH GATE
 * ██████████████████████████████████████████████████████████████████████
 *
 * Performance-critical validation (C++):
 *   1. Shannon entropy check — reject low-information signals
 *   2. Feature overlap detection — reject redundant/correlated features
 *   3. Structural fingerprint rejection — detect template/generated data
 *
 * Compile (Windows):
 *   g++ -shared -O2 -o signal_strength_validator.dll
 * signal_strength_validator.cpp
 */

#include <cmath>
#include <cstdio>
#include <cstring>

#ifdef _WIN32
#define SSV_EXPORT __declspec(dllexport)
#else
#define SSV_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* ================================================================== */
/*  THRESHOLDS                                                        */
/* ================================================================== */

#define MAX_FEATURES 4096
#define MAX_SAMPLES 65536
#define MIN_ENTROPY 1.50      /* Minimum bits of entropy per feature */
#define MAX_OVERLAP 0.85      /* Max Pearson correlation before flag */
#define FINGERPRINT_WIN 16    /* Window for repeating pattern scan  */
#define MAX_REPEAT_RATIO 0.30 /* Max 30% repeating blocks          */

/* ================================================================== */
/*  STATE                                                             */
/* ================================================================== */

typedef struct {
  int passed;
  double min_entropy;
  double max_overlap;
  double repeat_ratio;
  int features_checked;
  int samples_checked;
  int low_entropy_count;
  int high_overlap_pairs;
  int fingerprint_matches;
  char violation[256];
} SignalStrengthReport;

static SignalStrengthReport g_report;

/* ================================================================== */
/*  ENTROPY CHECK                                                     */
/* ================================================================== */

/*
 * Compute Shannon entropy for a single feature column.
 * Bins values into 64 buckets for continuous features.
 */
static double feature_entropy(const double *values, int n) {
  if (n <= 1)
    return 0.0;

  /* Find range */
  double vmin = values[0], vmax = values[0];
  for (int i = 1; i < n; i++) {
    if (values[i] < vmin)
      vmin = values[i];
    if (values[i] > vmax)
      vmax = values[i];
  }

  double range = vmax - vmin;
  if (range < 1e-12)
    return 0.0; /* Constant feature */

  /* Bin into 64 buckets */
  int bins[64] = {0};
  for (int i = 0; i < n; i++) {
    int b = (int)((values[i] - vmin) / range * 63.0);
    if (b < 0)
      b = 0;
    if (b > 63)
      b = 63;
    bins[b]++;
  }

  /* Shannon entropy */
  double h = 0.0;
  for (int b = 0; b < 64; b++) {
    if (bins[b] > 0) {
      double p = (double)bins[b] / n;
      h -= p * log2(p);
    }
  }
  return h;
}

/*
 * validate_entropy — Check all feature columns have sufficient entropy.
 * data: row-major [n_samples x n_features]
 * Returns: number of low-entropy features (0 = pass)
 */
SSV_EXPORT int validate_entropy(const double *data, int n_samples,
                                int n_features) {
  g_report.low_entropy_count = 0;
  g_report.min_entropy = 999.0;

  int check_features = n_features < MAX_FEATURES ? n_features : MAX_FEATURES;
  int check_samples = n_samples < MAX_SAMPLES ? n_samples : MAX_SAMPLES;

  /* Extract each column and check entropy */
  double col[MAX_SAMPLES];
  for (int f = 0; f < check_features; f++) {
    for (int s = 0; s < check_samples; s++) {
      col[s] = data[s * n_features + f];
    }
    double h = feature_entropy(col, check_samples);
    if (h < g_report.min_entropy)
      g_report.min_entropy = h;
    if (h < MIN_ENTROPY)
      g_report.low_entropy_count++;
  }

  g_report.features_checked = check_features;
  g_report.samples_checked = check_samples;
  return g_report.low_entropy_count;
}

/* ================================================================== */
/*  FEATURE OVERLAP CHECK                                             */
/* ================================================================== */

/*
 * Pearson correlation between two feature columns.
 */
static double pearson_corr(const double *x, const double *y, int n) {
  double sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0;
  for (int i = 0; i < n; i++) {
    sx += x[i];
    sy += y[i];
    sxx += x[i] * x[i];
    syy += y[i] * y[i];
    sxy += x[i] * y[i];
  }
  double num = n * sxy - sx * sy;
  double den = sqrt((n * sxx - sx * sx) * (n * syy - sy * sy));
  if (den < 1e-12)
    return 0.0;
  return fabs(num / den);
}

/*
 * validate_overlap — Check pairwise feature correlations.
 * Only checks first 128 features × first 128 features for performance.
 * Returns: number of highly-correlated pairs (0 = pass)
 */
SSV_EXPORT int validate_overlap(const double *data, int n_samples,
                                int n_features) {
  g_report.high_overlap_pairs = 0;
  g_report.max_overlap = 0.0;

  int check_f = n_features < 128 ? n_features : 128;
  int check_s = n_samples < 2048 ? n_samples : 2048;

  double col_a[2048], col_b[2048];

  for (int a = 0; a < check_f; a++) {
    for (int s = 0; s < check_s; s++)
      col_a[s] = data[s * n_features + a];

    for (int b = a + 1; b < check_f; b++) {
      for (int s = 0; s < check_s; s++)
        col_b[s] = data[s * n_features + b];

      double r = pearson_corr(col_a, col_b, check_s);
      if (r > g_report.max_overlap)
        g_report.max_overlap = r;
      if (r > MAX_OVERLAP)
        g_report.high_overlap_pairs++;
    }
  }

  return g_report.high_overlap_pairs;
}

/* ================================================================== */
/*  STRUCTURAL FINGERPRINT REJECTION                                  */
/* ================================================================== */

/*
 * validate_fingerprint — Detect repeating/template patterns in samples.
 *
 * Checks consecutive sample blocks for identical feature vectors.
 * Template/generated data often has repeating structural patterns.
 * Returns: number of fingerprint matches (0 = pass)
 */
SSV_EXPORT int validate_fingerprint(const double *data, int n_samples,
                                    int n_features) {
  g_report.fingerprint_matches = 0;

  if (n_samples < FINGERPRINT_WIN * 2)
    return 0;

  int check_s = n_samples < MAX_SAMPLES ? n_samples : MAX_SAMPLES;
  int repeats = 0;
  int total_blocks = 0;

  for (int i = 0; i + FINGERPRINT_WIN < check_s; i += FINGERPRINT_WIN) {
    total_blocks++;
    /* Compare this block with the next */
    int match = 1;
    for (int j = 0; j < FINGERPRINT_WIN && match; j++) {
      int row_a = i + j;
      int row_b = i + FINGERPRINT_WIN + j;
      if (row_b >= check_s) {
        match = 0;
        break;
      }

      /* Compare first 32 features of each row */
      int cmp_f = n_features < 32 ? n_features : 32;
      for (int f = 0; f < cmp_f; f++) {
        double diff =
            fabs(data[row_a * n_features + f] - data[row_b * n_features + f]);
        if (diff > 1e-10) {
          match = 0;
          break;
        }
      }
    }
    if (match)
      repeats++;
  }

  g_report.repeat_ratio =
      total_blocks > 0 ? (double)repeats / total_blocks : 0.0;
  g_report.fingerprint_matches = repeats;
  return repeats;
}

/* ================================================================== */
/*  FULL SIGNAL STRENGTH CHECK                                        */
/* ================================================================== */

SSV_EXPORT int validate_signal_strength(const double *data, int n_samples,
                                        int n_features) {
  memset(&g_report, 0, sizeof(g_report));

  /* Check 1: Entropy */
  int low_entropy = validate_entropy(data, n_samples, n_features);
  if (low_entropy > n_features / 4) {
    snprintf(g_report.violation, sizeof(g_report.violation),
             "Too many low-entropy features: %d/%d (min_h=%.3f)", low_entropy,
             n_features, g_report.min_entropy);
    g_report.passed = 0;
    return 0;
  }

  /* Check 2: Feature overlap */
  int overlaps = validate_overlap(data, n_samples, n_features);
  if (overlaps > n_features / 8) {
    snprintf(g_report.violation, sizeof(g_report.violation),
             "Too many correlated feature pairs: %d (max_r=%.3f)", overlaps,
             g_report.max_overlap);
    g_report.passed = 0;
    return 0;
  }

  /* Check 3: Structural fingerprint */
  int fingerprints = validate_fingerprint(data, n_samples, n_features);
  if (g_report.repeat_ratio > MAX_REPEAT_RATIO) {
    snprintf(g_report.violation, sizeof(g_report.violation),
             "Structural fingerprint detected: %.1f%% repeating blocks",
             g_report.repeat_ratio * 100);
    g_report.passed = 0;
    return 0;
  }

  g_report.passed = 1;
  return 1;
}

/* ================================================================== */
/*  STATUS QUERIES                                                    */
/* ================================================================== */

SSV_EXPORT int ssv_passed(void) { return g_report.passed; }
SSV_EXPORT double ssv_min_entropy(void) { return g_report.min_entropy; }
SSV_EXPORT double ssv_max_overlap(void) { return g_report.max_overlap; }
SSV_EXPORT double ssv_repeat_ratio(void) { return g_report.repeat_ratio; }
SSV_EXPORT int ssv_low_entropy_count(void) {
  return g_report.low_entropy_count;
}
SSV_EXPORT int ssv_overlap_pairs(void) { return g_report.high_overlap_pairs; }
SSV_EXPORT int ssv_fingerprint_count(void) {
  return g_report.fingerprint_matches;
}

SSV_EXPORT void ssv_get_violation(char *out, int len) {
  strncpy(out, g_report.violation, len - 1);
  out[len - 1] = '\0';
}

#ifdef __cplusplus
}
#endif
