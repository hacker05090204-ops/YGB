/*
 * passive_live_shadow_validator.cpp — Passive Shadow Validator (Phase B)
 *
 * Cross-environment stability test.
 * Validates shadow predictions across multiple environments.
 * Blocks promotion on inconsistency.
 *
 * C API for Python bridge.
 */

#include <cmath>
#include <cstdint>
#include <cstring>


#ifdef __cplusplus
extern "C" {
#endif

#define MAX_ENVS 16
#define MAX_PREDICTIONS 256
#define CONSISTENCY_THRESH 0.85

typedef struct {
  int env_id;
  double prediction;
  double confidence;
} EnvPrediction;

typedef struct {
  int total_envs;
  int total_predictions;
  double consistency; /* agreement ratio across envs */
  double avg_confidence;
  int stable;
  int promotion_allowed;
} ShadowValidation;

/* Globals */
static EnvPrediction g_preds[MAX_PREDICTIONS];
static int g_pred_count = 0;
static int g_env_ids[MAX_ENVS];
static int g_env_count = 0;

static int find_or_add_env(int env_id) {
  for (int i = 0; i < g_env_count; i++) {
    if (g_env_ids[i] == env_id)
      return i;
  }
  if (g_env_count < MAX_ENVS) {
    g_env_ids[g_env_count] = env_id;
    g_env_count++;
    return g_env_count - 1;
  }
  return -1;
}

/* ---- Public API ---- */

int plsv_init(void) {
  memset(g_preds, 0, sizeof(g_preds));
  memset(g_env_ids, 0, sizeof(g_env_ids));
  g_pred_count = 0;
  g_env_count = 0;
  return 0;
}

int plsv_record(int env_id, double prediction, double confidence) {
  if (g_pred_count >= MAX_PREDICTIONS)
    return -1;
  find_or_add_env(env_id);
  EnvPrediction *p = &g_preds[g_pred_count];
  p->env_id = env_id;
  p->prediction = prediction;
  p->confidence = confidence;
  g_pred_count++;
  return 0;
}

ShadowValidation plsv_evaluate(void) {
  ShadowValidation r;
  memset(&r, 0, sizeof(r));
  r.total_envs = g_env_count;
  r.total_predictions = g_pred_count;

  if (g_pred_count < 2 || g_env_count < 2) {
    r.stable = 0;
    r.promotion_allowed = 0;
    return r;
  }

  /* Per-env mean prediction */
  double env_means[MAX_ENVS];
  int env_counts[MAX_ENVS];
  memset(env_means, 0, sizeof(env_means));
  memset(env_counts, 0, sizeof(env_counts));

  double conf_sum = 0;
  for (int i = 0; i < g_pred_count; i++) {
    int eidx = find_or_add_env(g_preds[i].env_id);
    if (eidx >= 0) {
      env_means[eidx] += g_preds[i].prediction;
      env_counts[eidx]++;
    }
    conf_sum += g_preds[i].confidence;
  }

  for (int i = 0; i < g_env_count; i++) {
    if (env_counts[i] > 0)
      env_means[i] /= env_counts[i];
  }

  /* Consistency: count pairs within 0.1 of each other */
  int pairs = 0, agree = 0;
  for (int i = 0; i < g_env_count; i++) {
    for (int j = i + 1; j < g_env_count; j++) {
      pairs++;
      if (fabs(env_means[i] - env_means[j]) < 0.1)
        agree++;
    }
  }

  r.consistency = (pairs > 0) ? (double)agree / pairs : 0.0;
  r.avg_confidence = conf_sum / g_pred_count;
  r.stable = (r.consistency >= CONSISTENCY_THRESH) ? 1 : 0;
  r.promotion_allowed = r.stable;
  return r;
}

int plsv_get_pred_count(void) { return g_pred_count; }
int plsv_get_env_count(void) { return g_env_count; }
int plsv_is_stable(void) { return plsv_evaluate().stable; }

#ifdef __cplusplus
}
#endif
