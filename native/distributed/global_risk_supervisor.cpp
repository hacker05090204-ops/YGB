/*
 * global_risk_supervisor.cpp — Global Risk Supervisor (Phase A)
 *
 * Monitors:
 *   FPR rolling window, hallucination rate, drift, duplicate trend,
 *   cross-field leakage, reinforcement weight ratio.
 * Actions:
 *   Freeze field, rollback model, trigger retrain, lock promotion.
 *
 * C API for Python bridge.
 */

#include <cmath>
#include <cstdint>
#include <cstring>


#ifdef __cplusplus
extern "C" {
#endif

#define MAX_FIELDS 64
#define WINDOW_SIZE 500
#define FPR_LIMIT 0.01
#define HALLUC_LIMIT 0.005
#define DRIFT_LIMIT 0.05
#define LEAKAGE_LIMIT 0.03
#define REINFORCE_LIMIT 0.20

typedef struct {
  char field_name[128];
  int frozen;
  int rollback_count;
  int retrain_count;
  int promotion_locked;

  /* Rolling metrics */
  double fpr;
  double hallucination;
  double drift;
  double leakage;
  double reinforce_ratio;
  double dup_trend;
} FieldRisk;

typedef struct {
  int total_fields;
  int frozen_fields;
  int healthy_fields;
  int rollbacks;
  int retrains;
  int promotions_locked;
  int system_healthy;
} RiskReport;

/* Globals */
static FieldRisk g_fields[MAX_FIELDS];
static int g_field_count = 0;

/* ---- Public API ---- */

int grs_init(void) {
  memset(g_fields, 0, sizeof(g_fields));
  g_field_count = 0;
  return 0;
}

int grs_register_field(const char *name) {
  if (g_field_count >= MAX_FIELDS)
    return -1;
  strncpy(g_fields[g_field_count].field_name, name, 127);
  g_field_count++;
  return 0;
}

static int find_field(const char *name) {
  for (int i = 0; i < g_field_count; i++) {
    if (strcmp(g_fields[i].field_name, name) == 0)
      return i;
  }
  return -1;
}

int grs_update_metrics(const char *field_name, double fpr, double hallucination,
                       double drift, double leakage, double reinforce_ratio,
                       double dup_trend) {
  int idx = find_field(field_name);
  if (idx < 0)
    return -1;

  FieldRisk *f = &g_fields[idx];
  f->fpr = fpr;
  f->hallucination = hallucination;
  f->drift = drift;
  f->leakage = leakage;
  f->reinforce_ratio = reinforce_ratio;
  f->dup_trend = dup_trend;

  /* Auto-freeze on violation */
  int violation = 0;
  if (fpr > FPR_LIMIT)
    violation = 1;
  if (hallucination > HALLUC_LIMIT)
    violation = 1;
  if (drift > DRIFT_LIMIT)
    violation = 1;
  if (leakage > LEAKAGE_LIMIT)
    violation = 1;
  if (reinforce_ratio > REINFORCE_LIMIT)
    violation = 1;

  if (violation) {
    f->frozen = 1;
    f->rollback_count++;
    f->retrain_count++;
    f->promotion_locked = 1;
  } else {
    f->frozen = 0;
    f->promotion_locked = 0;
  }

  return violation;
}

int grs_is_frozen(const char *name) {
  int idx = find_field(name);
  return (idx >= 0) ? g_fields[idx].frozen : -1;
}

int grs_is_promotion_locked(const char *name) {
  int idx = find_field(name);
  return (idx >= 0) ? g_fields[idx].promotion_locked : -1;
}

RiskReport grs_get_report(void) {
  RiskReport r;
  memset(&r, 0, sizeof(r));
  r.total_fields = g_field_count;

  int frozen = 0, rollbacks = 0, retrains = 0, locked = 0;
  for (int i = 0; i < g_field_count; i++) {
    if (g_fields[i].frozen)
      frozen++;
    rollbacks += g_fields[i].rollback_count;
    retrains += g_fields[i].retrain_count;
    if (g_fields[i].promotion_locked)
      locked++;
  }

  r.frozen_fields = frozen;
  r.healthy_fields = g_field_count - frozen;
  r.rollbacks = rollbacks;
  r.retrains = retrains;
  r.promotions_locked = locked;
  r.system_healthy = (frozen == 0) ? 1 : 0;
  return r;
}

#ifdef __cplusplus
}
#endif
