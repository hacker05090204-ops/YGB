/*
 * live_shadow_inference_engine.cpp — Live Shadow Inference (Phase B)
 *
 * Before active exploit:
 *   100 passive scans
 *   Distribution divergence score
 *   Entropy shift detection
 *   Cross-env stability test
 *
 * Block field promotion if unstable.
 *
 * C API for Python bridge.
 */

#include <cmath>
#include <cstdint>
#include <cstring>


#ifdef __cplusplus
extern "C" {
#endif

#define MAX_SCANS 500
#define MIN_PASSIVE 100
#define DIVERGENCE_LIMIT 0.10
#define ENTROPY_LIMIT 0.15

typedef struct {
  double prediction;
  double confidence;
  int label;
} ScanResult;

typedef struct {
  int total_scans;
  int passive_count;
  double mean_confidence;
  double std_confidence;
  double divergence; /* lab vs shadow distribution */
  double entropy_shift;
  int stable; /* 1 if within limits */
  int promotion_blocked;
} ShadowReport;

/* Globals */
static ScanResult g_scans[MAX_SCANS];
static int g_scan_count = 0;
static double g_lab_mean = 0.0;
static double g_lab_std = 0.0;

/* ---- Public API ---- */

int lsie_init(double lab_mean, double lab_std) {
  memset(g_scans, 0, sizeof(g_scans));
  g_scan_count = 0;
  g_lab_mean = lab_mean;
  g_lab_std = (lab_std > 0) ? lab_std : 0.01;
  return 0;
}

int lsie_record_scan(double prediction, double confidence, int label) {
  if (g_scan_count >= MAX_SCANS)
    return -1;
  ScanResult *s = &g_scans[g_scan_count];
  s->prediction = prediction;
  s->confidence = confidence;
  s->label = label;
  g_scan_count++;
  return 0;
}

ShadowReport lsie_evaluate(void) {
  ShadowReport r;
  memset(&r, 0, sizeof(r));
  r.total_scans = g_scan_count;
  r.passive_count = g_scan_count;

  if (g_scan_count < 2) {
    r.stable = 0;
    r.promotion_blocked = 1;
    return r;
  }

  /* Compute shadow mean and std */
  double sum = 0, sum2 = 0;
  for (int i = 0; i < g_scan_count; i++) {
    sum += g_scans[i].confidence;
    sum2 += g_scans[i].confidence * g_scans[i].confidence;
  }
  double mean = sum / g_scan_count;
  double var = (sum2 / g_scan_count) - (mean * mean);
  if (var < 0)
    var = 0;
  double std = sqrt(var);

  r.mean_confidence = mean;
  r.std_confidence = std;

  /* Divergence: |shadow_mean - lab_mean| / lab_std */
  r.divergence = fabs(mean - g_lab_mean) / g_lab_std;

  /* Entropy shift: |shadow_std - lab_std| / lab_std */
  r.entropy_shift = fabs(std - g_lab_std) / g_lab_std;

  r.stable = (r.divergence <= DIVERGENCE_LIMIT &&
              r.entropy_shift <= ENTROPY_LIMIT && g_scan_count >= MIN_PASSIVE)
                 ? 1
                 : 0;

  r.promotion_blocked = r.stable ? 0 : 1;
  return r;
}

int lsie_get_scan_count(void) { return g_scan_count; }
int lsie_is_stable(void) { return lsie_evaluate().stable; }
int lsie_is_promotion_blocked(void) {
  return lsie_evaluate().promotion_blocked;
}

#ifdef __cplusplus
}
#endif
