/**
 * risk_shift_guard.h — Deterministic risk-shift guard for real-data rollout.
 *
 * Pure C implementation (no external deps). Functions are stateless
 * and deterministic — same inputs always produce same outputs.
 *
 * USAGE:
 *   #include "risk_shift_guard.h"
 *
 *   double p[] = {0.3, 0.5, 0.2};
 *   double q[] = {0.25, 0.55, 0.2};
 *   double js = rsg_jensen_shannon_divergence(p, q, 3);
 */

#ifndef RISK_SHIFT_GUARD_H
#define RISK_SHIFT_GUARD_H

#ifdef __cplusplus
extern "C" {
#endif

/* ---------- thresholds (compile-time constants) ---------- */

#define RSG_JS_DIVERGENCE_THRESHOLD 0.15
#define RSG_IMBALANCE_THRESHOLD 10.0
#define RSG_UNKNOWN_TOKEN_THRESHOLD 0.05
#define RSG_COMPOSITE_THRESHOLD 0.50

/* weight mix for composite score */
#define RSG_W_JS_DIV 0.40
#define RSG_W_IMBALANCE 0.30
#define RSG_W_UNKNOWN 0.30

/* ---------- result codes ---------- */

#define RSG_PASS 0
#define RSG_FAIL 1

/* ---------- core functions ---------- */

/**
 * Jensen-Shannon divergence between two probability distributions.
 *
 * Both p and q must sum to ~1.0. Length n must be > 0.
 * Returns value in [0, ln(2)] ≈ [0, 0.693].
 * Returns -1.0 on invalid input.
 */
double rsg_jensen_shannon_divergence(const double *p, const double *q, int n);

/**
 * Class imbalance ratio = max(counts) / max(min(counts), 1).
 *
 * counts: array of per-class sample counts.
 * n_classes: number of classes.
 * Returns ratio >= 1.0.  Returns -1.0 on invalid input.
 */
double rsg_class_imbalance_ratio(const int *counts, int n_classes);

/**
 * Unknown-token ratio = unknown_count / max(total_count, 1).
 *
 * Returns value in [0, 1].  Returns -1.0 on invalid input.
 */
double rsg_unknown_token_ratio(int unknown_count, int total_count);

/**
 * Composite risk score (weighted combination, clamped to [0, 1]).
 *
 *   score = W_JS * (js_div / ln2)
 *         + W_IMBALANCE * min(imbalance / 100, 1)
 *         + W_UNKNOWN * unknown_ratio
 */
double rsg_composite_risk_score(double js_div, double imbalance,
                                double unknown_ratio);

/**
 * Pass / fail gate.
 *
 * Returns RSG_PASS (0) if composite_score <= threshold,
 *         RSG_FAIL (1) otherwise, or on invalid input.
 */
int rsg_risk_gate(double composite_score, double threshold);

#ifdef __cplusplus
}
#endif

#endif /* RISK_SHIFT_GUARD_H */
