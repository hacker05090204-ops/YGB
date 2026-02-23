/*
 * chaos_variance_injector.cpp — Chaos Variance Testing Engine (Phase 5)
 *
 * Validate model stability under adversarial variance:
 *   Latency jitter (0–500ms)
 *   Middleware rewrite (header/body transforms)
 *   TLS noise (certificate parameter variance)
 *   Header mutation (UA, Accept, encoding permutations)
 *
 * Model output must remain ≥95% consistent across chaos runs.
 * Reject findings that are unstable under chaos injection.
 *
 * C API for Python bridge.
 */

#include <cmath>
#include <cstring>

#ifdef __cplusplus
extern "C" {
#endif

#define MAX_CHAOS_RUNS 100
#define MAX_MUTATIONS 8
#define STABILITY_THRESHOLD 0.95
#define FIELD_LEN 128

/* ---- Chaos injection types ---- */
typedef enum {
  CHAOS_LATENCY_JITTER = 0,
  CHAOS_MIDDLEWARE_REWRITE = 1,
  CHAOS_TLS_NOISE = 2,
  CHAOS_HEADER_MUTATION = 3,
  CHAOS_ENCODING_SHIFT = 4,
  CHAOS_BODY_TRANSFORM = 5,
  CHAOS_STATUS_FLIP = 6,
  CHAOS_TIMEOUT_SPIKE = 7,
} ChaosType;

typedef struct {
  ChaosType type;
  double intensity;        /* 0.0–1.0 */
  double latency_delta_ms; /* added latency */
  int header_mutated;      /* 1 if UA/Accept changed */
  int tls_altered;         /* 1 if cert params varied */
  int body_transformed;    /* 1 if response body was rewritten */
} ChaosInjection;

typedef struct {
  int run_id;
  double original_confidence;
  double chaos_confidence;
  double delta;         /* |original - chaos| */
  int prediction_match; /* 1 if same class predicted */
  ChaosInjection injection;
} ChaosRunResult;

typedef struct {
  int total_runs;
  int matching_predictions;
  double stability_score; /* ratio of matching predictions */
  double mean_confidence_delta;
  double max_confidence_delta;
  int stable;           /* 1 if stability >= threshold */
  int worst_chaos_type; /* which injection caused most variance */
  double per_type_stability[MAX_MUTATIONS];
} ChaosReport;

/* ---- Globals ---- */
static ChaosRunResult g_runs[MAX_CHAOS_RUNS];
static int g_run_count = 0;

/* ---- Public API ---- */

int cvi_init(void) {
  memset(g_runs, 0, sizeof(g_runs));
  g_run_count = 0;
  return 0;
}

int cvi_record_run(int run_id, double original_confidence,
                   double chaos_confidence, int prediction_match,
                   int chaos_type, double intensity, double latency_delta_ms,
                   int header_mutated, int tls_altered, int body_transformed) {
  if (g_run_count >= MAX_CHAOS_RUNS)
    return -1;

  ChaosRunResult *r = &g_runs[g_run_count];
  r->run_id = run_id;
  r->original_confidence = original_confidence;
  r->chaos_confidence = chaos_confidence;
  r->delta = fabs(original_confidence - chaos_confidence);
  r->prediction_match = prediction_match;

  r->injection.type = (ChaosType)chaos_type;
  r->injection.intensity = intensity;
  r->injection.latency_delta_ms = latency_delta_ms;
  r->injection.header_mutated = header_mutated;
  r->injection.tls_altered = tls_altered;
  r->injection.body_transformed = body_transformed;

  g_run_count++;
  return 0;
}

ChaosReport cvi_evaluate(void) {
  ChaosReport rpt;
  memset(&rpt, 0, sizeof(rpt));
  rpt.total_runs = g_run_count;

  if (g_run_count == 0) {
    rpt.stable = 0;
    return rpt;
  }

  int matches = 0;
  double sum_delta = 0.0;
  double max_delta = 0.0;

  /* Per-type counters */
  int type_total[MAX_MUTATIONS];
  int type_match[MAX_MUTATIONS];
  memset(type_total, 0, sizeof(type_total));
  memset(type_match, 0, sizeof(type_match));

  for (int i = 0; i < g_run_count; i++) {
    ChaosRunResult *r = &g_runs[i];
    if (r->prediction_match)
      matches++;
    sum_delta += r->delta;
    if (r->delta > max_delta)
      max_delta = r->delta;

    int t = (int)r->injection.type;
    if (t >= 0 && t < MAX_MUTATIONS) {
      type_total[t]++;
      if (r->prediction_match)
        type_match[t]++;
    }
  }

  rpt.matching_predictions = matches;
  rpt.stability_score = (double)matches / g_run_count;
  rpt.mean_confidence_delta = sum_delta / g_run_count;
  rpt.max_confidence_delta = max_delta;
  rpt.stable = (rpt.stability_score >= STABILITY_THRESHOLD) ? 1 : 0;

  /* Find worst chaos type */
  double worst = 1.0;
  int worst_type = 0;
  for (int t = 0; t < MAX_MUTATIONS; t++) {
    double ts = 1.0;
    if (type_total[t] > 0)
      ts = (double)type_match[t] / type_total[t];
    rpt.per_type_stability[t] = ts;
    if (ts < worst) {
      worst = ts;
      worst_type = t;
    }
  }
  rpt.worst_chaos_type = worst_type;

  return rpt;
}

int cvi_get_run_count(void) { return g_run_count; }

int cvi_is_stable(void) {
  ChaosReport r = cvi_evaluate();
  return r.stable;
}

double cvi_get_stability(void) {
  ChaosReport r = cvi_evaluate();
  return r.stability_score;
}

#ifdef __cplusplus
}
#endif
