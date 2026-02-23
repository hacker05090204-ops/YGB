/*
 * duplicate_likelihood_estimator.cpp — Duplicate Likelihood Estimator (Phase C)
 *
 * Compute:
 *   Program popularity score
 *   Bug class saturation
 *   Public report density
 *   CVE frequency
 *
 * Adjust:
 *   Confidence threshold
 *   Exploit strictness
 *
 * C API for Python bridge.
 */

#include <cstdint>
#include <cstring>

#ifdef __cplusplus
extern "C" {
#endif

#define MAX_PROGRAMS 128
#define FIELD_LEN 128

typedef struct {
  char program_id[FIELD_LEN];
  double popularity;     /* 0-1 higher = more popular */
  double saturation;     /* 0-1 higher = more saturated */
  double report_density; /* reports per month */
  double cve_frequency;  /* CVEs per year */
} ProgramProfile;

typedef struct {
  double dup_likelihood; /* 0-1 probability of duplicate */
  double adjusted_confidence_threshold;
  double adjusted_exploit_strictness;
  int high_risk; /* 1 if dup_likelihood > 0.5 */
} DupEstimate;

/* Globals */
static ProgramProfile g_programs[MAX_PROGRAMS];
static int g_program_count = 0;

/* ---- Public API ---- */

int dle_init(void) {
  memset(g_programs, 0, sizeof(g_programs));
  g_program_count = 0;
  return 0;
}

int dle_register_program(const char *program_id, double popularity,
                         double saturation, double report_density,
                         double cve_frequency) {
  if (g_program_count >= MAX_PROGRAMS)
    return -1;
  ProgramProfile *p = &g_programs[g_program_count];
  strncpy(p->program_id, program_id, FIELD_LEN - 1);
  p->popularity = popularity;
  p->saturation = saturation;
  p->report_density = report_density;
  p->cve_frequency = cve_frequency;
  g_program_count++;
  return 0;
}

DupEstimate dle_estimate(const char *program_id) {
  DupEstimate e;
  memset(&e, 0, sizeof(e));

  int idx = -1;
  for (int i = 0; i < g_program_count; i++) {
    if (strcmp(g_programs[i].program_id, program_id) == 0) {
      idx = i;
      break;
    }
  }

  if (idx < 0) {
    e.dup_likelihood = 0.1; /* Unknown program = low risk */
    e.adjusted_confidence_threshold = 0.90;
    e.adjusted_exploit_strictness = 1.0;
    return e;
  }

  ProgramProfile *p = &g_programs[idx];

  /* Dup likelihood: weighted combination */
  e.dup_likelihood = 0.30 * p->popularity + 0.35 * p->saturation +
                     0.20 * (p->report_density / 100.0) +
                     0.15 * (p->cve_frequency / 50.0);

  if (e.dup_likelihood > 1.0)
    e.dup_likelihood = 1.0;

  /* Adjust thresholds based on dup risk */
  e.adjusted_confidence_threshold =
      0.90 + (e.dup_likelihood * 0.09); /* up to 0.99 */
  if (e.adjusted_confidence_threshold > 0.99)
    e.adjusted_confidence_threshold = 0.99;

  e.adjusted_exploit_strictness =
      1.0 + (e.dup_likelihood * 0.5); /* up to 1.5x */
  e.high_risk = (e.dup_likelihood > 0.5) ? 1 : 0;

  return e;
}

int dle_get_program_count(void) { return g_program_count; }
double dle_get_likelihood(const char *prog) {
  return dle_estimate(prog).dup_likelihood;
}

#ifdef __cplusplus
}
#endif
