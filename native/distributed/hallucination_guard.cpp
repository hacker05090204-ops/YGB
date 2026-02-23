/*
 * hallucination_guard.cpp — Hallucination Guard (Phase 2)
 *
 * Evidence binding enforcement
 * Reject ungrounded statements
 * Rolling hallucination window <0.5%
 * Auto rollback on breach
 *
 * C API for Python bridge.
 */

#include <cstdint>
#include <cstring>

#ifdef __cplusplus
extern "C" {
#endif

#define MAX_STATEMENTS 4096
#define WINDOW_SIZE 1000
#define HALLUC_THRESHOLD 0.005 /* 0.5% */
#define HASH_LEN 65

typedef struct {
  int grounded;       /* 1=has evidence binding */
  int evidence_count; /* number of evidence items */
  char evidence_hash[HASH_LEN];
  double claim_confidence;
} StatementCheck;

typedef struct {
  int total_checked;
  int grounded;
  int ungrounded;
  double hallucination_rate;
  int breach; /* 1 if rate > threshold */
  int rollback_triggered;
} HallucinationReport;

/* Globals */
static int g_window[WINDOW_SIZE]; /* 1=grounded, 0=ungrounded */
static int g_window_pos = 0;
static int g_window_count = 0;
static int g_total = 0;
static int g_ungrounded = 0;
static int g_rollbacks = 0;
static int g_initialized = 0;

/* ---- Public API ---- */

int halluc_init(void) {
  memset(g_window, 0, sizeof(g_window));
  g_window_pos = 0;
  g_window_count = 0;
  g_total = 0;
  g_ungrounded = 0;
  g_rollbacks = 0;
  g_initialized = 1;
  return 0;
}

int halluc_check_statement(int has_evidence, int evidence_count,
                           const char *evidence_hash, double claim_confidence) {
  g_total++;

  int grounded = 0;

  /* Grounded if: has evidence AND evidence_count > 0 AND hash non-empty */
  if (has_evidence && evidence_count > 0 && evidence_hash &&
      strlen(evidence_hash) > 0) {
    grounded = 1;
  }

  /* Confidence too high without evidence → ungrounded */
  if (!grounded && claim_confidence > 0.8) {
    grounded = 0;
  }

  /* Update rolling window */
  if (g_window_count >= WINDOW_SIZE) {
    /* Remove oldest entry */
    if (g_window[g_window_pos] == 0) {
      g_ungrounded--; /* was ungrounded, removing */
    }
  } else {
    g_window_count++;
  }

  g_window[g_window_pos] = grounded ? 1 : 0;
  if (!grounded)
    g_ungrounded++;
  g_window_pos = (g_window_pos + 1) % WINDOW_SIZE;

  return grounded ? 1 : 0;
}

double halluc_get_rate(void) {
  if (g_window_count == 0)
    return 0.0;
  return (double)g_ungrounded / g_window_count;
}

int halluc_is_breach(void) {
  return (halluc_get_rate() > HALLUC_THRESHOLD) ? 1 : 0;
}

HallucinationReport halluc_get_report(void) {
  HallucinationReport r;
  memset(&r, 0, sizeof(r));
  r.total_checked = g_total;
  r.grounded = g_window_count - g_ungrounded;
  r.ungrounded = g_ungrounded;
  r.hallucination_rate = halluc_get_rate();
  r.breach = halluc_is_breach();
  r.rollback_triggered = g_rollbacks;

  /* Auto rollback on breach */
  if (r.breach) {
    g_rollbacks++;
    r.rollback_triggered = g_rollbacks;
  }

  return r;
}

int halluc_get_rollback_count(void) { return g_rollbacks; }

#ifdef __cplusplus
}
#endif
