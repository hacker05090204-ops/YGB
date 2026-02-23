/*
 * independent_validation_split.cpp — Independent Validation Split (Phase 0)
 *
 * Separate base dataset and reinforcement dataset.
 * Cap reinforcement data at 20%.
 * No cross-contamination between reinforcement and base.
 *
 * C API for Python bridge.
 */

#include <cstdint>
#include <cstring>

#ifdef __cplusplus
extern "C" {
#endif

#define MAX_SAMPLES 131072
#define REINFORCE_CAP 0.20 /* 20% max */
#define HASH_LEN 65

typedef struct {
  int total_samples;
  int base_count;
  int reinforce_count;
  double reinforce_ratio;
  int cap_enforced;       /* 1 if cap was hit */
  int contamination_free; /* 1 if no overlap detected */
} SplitReport;

/* Globals */
static char g_base_hashes[MAX_SAMPLES][HASH_LEN];
static char g_reinforce_hashes[MAX_SAMPLES][HASH_LEN];
static int g_base_count = 0;
static int g_reinforce_count = 0;
static int g_cap_hits = 0;
static int g_contaminations = 0;

/* Hash */
static void compute_fp(const char *data, int len, char *out) {
  unsigned long h1 = 5381, h2 = 0x9e3779b9;
  for (int i = 0; i < len; i++) {
    h1 = ((h1 << 5) + h1) + (unsigned char)data[i];
    h2 ^= ((h2 << 6) + (h2 >> 2) + (unsigned char)data[i]);
  }
  snprintf(out, HASH_LEN, "%016lx%016lx%016lx%016lx", h1, h2, h1 ^ h2, h1 + h2);
}

static int exists_in(const char hashes[][HASH_LEN], int count, const char *fp) {
  for (int i = 0; i < count; i++) {
    if (strcmp(hashes[i], fp) == 0)
      return 1;
  }
  return 0;
}

/* ---- Public API ---- */

int split_init(void) {
  g_base_count = 0;
  g_reinforce_count = 0;
  g_cap_hits = 0;
  g_contaminations = 0;
  memset(g_base_hashes, 0, sizeof(g_base_hashes));
  memset(g_reinforce_hashes, 0, sizeof(g_reinforce_hashes));
  return 0;
}

int split_add_base(const char *data, int len) {
  if (g_base_count >= MAX_SAMPLES)
    return -1;
  char fp[HASH_LEN];
  compute_fp(data, len, fp);

  /* Check no contamination from reinforcement pool */
  if (exists_in(g_reinforce_hashes, g_reinforce_count, fp)) {
    g_contaminations++;
    return -2;
  }

  strncpy(g_base_hashes[g_base_count], fp, HASH_LEN - 1);
  g_base_count++;
  return 0;
}

int split_add_reinforcement(const char *data, int len) {
  if (g_reinforce_count >= MAX_SAMPLES)
    return -1;

  /* Enforce 20% cap */
  int total = g_base_count + g_reinforce_count + 1;
  double ratio = (double)(g_reinforce_count + 1) / total;
  if (ratio > REINFORCE_CAP) {
    g_cap_hits++;
    return -3;
  }

  char fp[HASH_LEN];
  compute_fp(data, len, fp);

  /* No contamination from base pool */
  if (exists_in(g_base_hashes, g_base_count, fp)) {
    g_contaminations++;
    return -2;
  }

  strncpy(g_reinforce_hashes[g_reinforce_count], fp, HASH_LEN - 1);
  g_reinforce_count++;
  return 0;
}

SplitReport split_get_report(void) {
  SplitReport r;
  r.total_samples = g_base_count + g_reinforce_count;
  r.base_count = g_base_count;
  r.reinforce_count = g_reinforce_count;
  r.reinforce_ratio =
      (r.total_samples > 0) ? (double)g_reinforce_count / r.total_samples : 0.0;
  r.cap_enforced = g_cap_hits;
  r.contamination_free = (g_contaminations == 0) ? 1 : 0;
  return r;
}

int split_get_base_count(void) { return g_base_count; }
int split_get_reinforce_count(void) { return g_reinforce_count; }
int split_is_clean(void) { return (g_contaminations == 0) ? 1 : 0; }

#ifdef __cplusplus
}
#endif
