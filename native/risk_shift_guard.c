/**
 * risk_shift_guard.c — Deterministic risk-shift guard implementation.
 *
 * Pure C, no heap allocation, no global state.  Every function is
 * re-entrant and safe for concurrent use.
 */

#include "risk_shift_guard.h"
#include <math.h>

/* ------------------------------------------------------------------ */
/*  Internal helpers                                                   */
/* ------------------------------------------------------------------ */

/** Safe log — returns 0 when x <= 0 to avoid -inf / NaN. */
static double safe_log(double x) { return (x > 0.0) ? log(x) : 0.0; }

/** KL divergence D_KL(p || m) for a single element. */
static double kl_element(double pi, double mi) {
  if (pi <= 0.0)
    return 0.0;
  return pi * safe_log(pi / mi);
}

/* ------------------------------------------------------------------ */
/*  Public API                                                         */
/* ------------------------------------------------------------------ */

double rsg_jensen_shannon_divergence(const double *p, const double *q, int n) {
  if (!p || !q || n <= 0)
    return -1.0;

  double kl_pm = 0.0;
  double kl_qm = 0.0;

  for (int i = 0; i < n; i++) {
    double mi = 0.5 * (p[i] + q[i]);
    kl_pm += kl_element(p[i], mi);
    kl_qm += kl_element(q[i], mi);
  }

  return 0.5 * (kl_pm + kl_qm);
}

double rsg_class_imbalance_ratio(const int *counts, int n_classes) {
  if (!counts || n_classes <= 0)
    return -1.0;

  int min_c = counts[0];
  int max_c = counts[0];
  for (int i = 1; i < n_classes; i++) {
    if (counts[i] < min_c)
      min_c = counts[i];
    if (counts[i] > max_c)
      max_c = counts[i];
  }

  int safe_min = (min_c > 0) ? min_c : 1;
  return (double)max_c / (double)safe_min;
}

double rsg_unknown_token_ratio(int unknown_count, int total_count) {
  if (unknown_count < 0 || total_count < 0)
    return -1.0;

  int safe_total = (total_count > 0) ? total_count : 1;
  return (double)unknown_count / (double)safe_total;
}

double rsg_composite_risk_score(double js_div, double imbalance,
                                double unknown_ratio) {
  /* ln(2) for normalizing JS divergence to [0, 1] */
  static const double LN2 = 0.6931471805599453;

  double norm_js = (LN2 > 0.0) ? (js_div / LN2) : 0.0;
  if (norm_js > 1.0)
    norm_js = 1.0;
  if (norm_js < 0.0)
    norm_js = 0.0;

  double norm_imb = imbalance / 100.0;
  if (norm_imb > 1.0)
    norm_imb = 1.0;
  if (norm_imb < 0.0)
    norm_imb = 0.0;

  double norm_unk = unknown_ratio;
  if (norm_unk > 1.0)
    norm_unk = 1.0;
  if (norm_unk < 0.0)
    norm_unk = 0.0;

  double score = RSG_W_JS_DIV * norm_js + RSG_W_IMBALANCE * norm_imb +
                 RSG_W_UNKNOWN * norm_unk;

  if (score > 1.0)
    score = 1.0;
  if (score < 0.0)
    score = 0.0;

  return score;
}

int rsg_risk_gate(double composite_score, double threshold) {
  if (isnan(composite_score) || isnan(threshold))
    return RSG_FAIL;

  return (composite_score <= threshold) ? RSG_PASS : RSG_FAIL;
}
