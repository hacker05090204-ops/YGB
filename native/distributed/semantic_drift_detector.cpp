/*
 * semantic_drift_detector.cpp — Semantic Drift Detector (Phase F)
 *
 * Monitor:
 *   Embedding centroid shift
 *   Label entropy shift
 *   Reinforcement bias
 *
 * Freeze ingestion if drift exceeded.
 *
 * C API for Python bridge.
 */

#include <cmath>
#include <cstdint>
#include <cstring>


#ifdef __cplusplus
extern "C" {
#endif

#define MAX_DIM 512
#define CENTROID_LIMIT 0.10
#define ENTROPY_LIMIT 0.15
#define RL_BIAS_LIMIT 0.20

typedef struct {
  double centroid_shift;
  double entropy_shift;
  double rl_bias;
  int drift_detected;
  int ingestion_frozen;
} DriftReport;

/* Globals */
static double g_baseline_centroid[MAX_DIM];
static double g_current_centroid[MAX_DIM];
static int g_dim = 0;
static double g_baseline_entropy = 0.0;
static double g_current_entropy = 0.0;
static double g_rl_ratio = 0.0;
static int g_frozen = 0;
static int g_freeze_count = 0;

/* ---- Public API ---- */

int sdd_init(int dim) {
  if (dim > MAX_DIM)
    dim = MAX_DIM;
  g_dim = dim;
  memset(g_baseline_centroid, 0, sizeof(g_baseline_centroid));
  memset(g_current_centroid, 0, sizeof(g_current_centroid));
  g_baseline_entropy = 0.0;
  g_current_entropy = 0.0;
  g_rl_ratio = 0.0;
  g_frozen = 0;
  g_freeze_count = 0;
  return 0;
}

int sdd_set_baseline(const double *centroid, double entropy) {
  if (g_dim == 0)
    return -1;
  memcpy(g_baseline_centroid, centroid, g_dim * sizeof(double));
  g_baseline_entropy = entropy;
  return 0;
}

int sdd_update_current(const double *centroid, double entropy,
                       double rl_ratio) {
  if (g_dim == 0)
    return -1;
  memcpy(g_current_centroid, centroid, g_dim * sizeof(double));
  g_current_entropy = entropy;
  g_rl_ratio = rl_ratio;
  return 0;
}

static double compute_centroid_shift(void) {
  double sum = 0;
  for (int i = 0; i < g_dim; i++) {
    double d = g_current_centroid[i] - g_baseline_centroid[i];
    sum += d * d;
  }
  return sqrt(sum / g_dim);
}

DriftReport sdd_evaluate(void) {
  DriftReport r;
  memset(&r, 0, sizeof(r));

  r.centroid_shift = compute_centroid_shift();

  if (g_baseline_entropy > 0) {
    r.entropy_shift =
        fabs(g_current_entropy - g_baseline_entropy) / g_baseline_entropy;
  }

  r.rl_bias = g_rl_ratio;

  int drift = 0;
  if (r.centroid_shift > CENTROID_LIMIT)
    drift = 1;
  if (r.entropy_shift > ENTROPY_LIMIT)
    drift = 1;
  if (r.rl_bias > RL_BIAS_LIMIT)
    drift = 1;

  r.drift_detected = drift;

  if (drift && !g_frozen) {
    g_frozen = 1;
    g_freeze_count++;
  }
  r.ingestion_frozen = g_frozen;

  return r;
}

int sdd_is_drifting(void) { return sdd_evaluate().drift_detected; }
int sdd_is_frozen(void) { return g_frozen; }
int sdd_unfreeze(void) {
  g_frozen = 0;
  return 0;
}
int sdd_get_freeze_count(void) { return g_freeze_count; }

#ifdef __cplusplus
}
#endif
