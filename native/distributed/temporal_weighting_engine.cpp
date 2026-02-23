/*
 * temporal_weighting_engine.cpp — Temporal Weighting Engine (Phase 0)
 *
 * Apply time-decay to stale patterns.
 * Recent samples weighted higher.
 * Exponential decay with configurable half-life.
 *
 * C API for Python bridge.
 */

#include <cmath>
#include <cstdint>
#include <cstring>
#include <ctime>


#ifdef __cplusplus
extern "C" {
#endif

#define MAX_ENTRIES 65536
#define DEFAULT_HALFLIFE 604800 /* 7 days in seconds */

typedef struct {
  long timestamp;
  double original_weight;
  double decayed_weight;
  int stale; /* 1 if weight < 0.1 */
} TemporalEntry;

typedef struct {
  int total_entries;
  int active_entries; /* non-stale */
  int stale_entries;
  double avg_weight;
  double min_weight;
  double max_weight;
} TemporalReport;

/* Globals */
static double g_halflife = DEFAULT_HALFLIFE;
static double g_decay_rate;
static int g_count = 0;
static long g_timestamps[MAX_ENTRIES];
static double g_weights[MAX_ENTRIES];

/* ---- Public API ---- */

int tw_init(double halflife_sec) {
  g_halflife = (halflife_sec > 0) ? halflife_sec : DEFAULT_HALFLIFE;
  g_decay_rate = log(2.0) / g_halflife;
  g_count = 0;
  memset(g_timestamps, 0, sizeof(g_timestamps));
  memset(g_weights, 0, sizeof(g_weights));
  return 0;
}

int tw_add_sample(long timestamp, double weight) {
  if (g_count >= MAX_ENTRIES)
    return -1;
  g_timestamps[g_count] = timestamp;
  g_weights[g_count] = weight;
  g_count++;
  return 0;
}

double tw_compute_weight(int idx, long now) {
  if (idx < 0 || idx >= g_count)
    return 0.0;
  double age = (double)(now - g_timestamps[idx]);
  if (age < 0)
    age = 0;
  return g_weights[idx] * exp(-g_decay_rate * age);
}

TemporalReport tw_evaluate(void) {
  TemporalReport r;
  memset(&r, 0, sizeof(r));
  r.total_entries = g_count;

  if (g_count == 0)
    return r;

  long now = (long)time(NULL);
  double sum = 0, mn = 1e9, mx = 0;
  int stale = 0;

  for (int i = 0; i < g_count; i++) {
    double w = tw_compute_weight(i, now);
    sum += w;
    if (w < mn)
      mn = w;
    if (w > mx)
      mx = w;
    if (w < 0.1)
      stale++;
  }

  r.active_entries = g_count - stale;
  r.stale_entries = stale;
  r.avg_weight = sum / g_count;
  r.min_weight = mn;
  r.max_weight = mx;
  return r;
}

int tw_get_count(void) { return g_count; }
double tw_get_halflife(void) { return g_halflife; }

#ifdef __cplusplus
}
#endif
