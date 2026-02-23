/*
 * zero_trust_validator.cpp — Zero Trust Validator (Phase 3)
 *
 * Adversarial perturbation
 * Cross-field inference
 * Random stress inputs
 * Reject if stability drop >25%
 *
 * C API for Python bridge.
 */

#include <cmath>
#include <cstdint>
#include <cstring>


#ifdef __cplusplus
extern "C" {
#endif

#define MAX_TESTS 256
#define STABILITY_THRESH 0.25 /* 25% max drop */

typedef struct {
  double baseline_score;
  double perturbed_score;
  double drop;
  int passed;
  int test_type; /* 0=adversarial, 1=cross_field, 2=stress */
} TrustTestResult;

typedef struct {
  int total_tests;
  int passed;
  int failed;
  double avg_drop;
  double max_drop;
  int zero_trust_passed; /* 1 if all passed */
} TrustReport;

/* Globals */
static TrustTestResult g_tests[MAX_TESTS];
static int g_test_count = 0;
static int g_initialized = 0;

/* ---- Public API ---- */

int zt_init(void) {
  memset(g_tests, 0, sizeof(g_tests));
  g_test_count = 0;
  g_initialized = 1;
  return 0;
}

int zt_record_test(double baseline_score, double perturbed_score,
                   int test_type) {
  if (g_test_count >= MAX_TESTS)
    return -1;

  TrustTestResult *t = &g_tests[g_test_count];
  t->baseline_score = baseline_score;
  t->perturbed_score = perturbed_score;
  t->test_type = test_type;

  /* Calculate drop */
  if (baseline_score > 0.0) {
    t->drop = (baseline_score - perturbed_score) / baseline_score;
  } else {
    t->drop = 0.0;
  }
  if (t->drop < 0.0)
    t->drop = 0.0;

  t->passed = (t->drop <= STABILITY_THRESH) ? 1 : 0;
  g_test_count++;
  return 0;
}

TrustReport zt_evaluate(void) {
  TrustReport r;
  memset(&r, 0, sizeof(r));
  r.total_tests = g_test_count;

  if (g_test_count == 0) {
    r.zero_trust_passed = 0;
    return r;
  }

  double sum_drop = 0.0;
  double max_drop = 0.0;
  int passed = 0;

  for (int i = 0; i < g_test_count; i++) {
    sum_drop += g_tests[i].drop;
    if (g_tests[i].drop > max_drop)
      max_drop = g_tests[i].drop;
    if (g_tests[i].passed)
      passed++;
  }

  r.passed = passed;
  r.failed = g_test_count - passed;
  r.avg_drop = sum_drop / g_test_count;
  r.max_drop = max_drop;
  r.zero_trust_passed = (r.failed == 0) ? 1 : 0;

  return r;
}

int zt_get_test_count(void) { return g_test_count; }
double zt_get_max_drop(void) {
  TrustReport r = zt_evaluate();
  return r.max_drop;
}
int zt_is_passed(void) {
  TrustReport r = zt_evaluate();
  return r.zero_trust_passed;
}

#ifdef __cplusplus
}
#endif
