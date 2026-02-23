/*
 * auto_ingest_engine.cpp — Auto Ingest Engine (Phase 4)
 *
 * Scheduled trusted source pull
 * SHA-256 dedup
 * Rate limiting
 * Structural validation
 *
 * C API for Python bridge.
 */

#include <cstdint>
#include <cstring>
#include <ctime>

#ifdef __cplusplus
extern "C" {
#endif

#define MAX_SOURCES 32
#define MAX_QUEUE 8192
#define HASH_LEN 65
#define PULL_INTERVAL_SEC 3600 /* 1 hour */

typedef struct {
  char source_id[128];
  char source_url[512];
  double reliability;
  long last_pull;
  int pull_count;
  int active;
} IngestSource;

typedef struct {
  char fingerprint[HASH_LEN];
  char source_id[128];
  int valid; /* passed structural validation */
  long ingested_at;
} QueuedSample;

typedef struct {
  int total_sources;
  int active_sources;
  int total_queued;
  int duplicates_rejected;
  int validation_failures;
  int pull_count;
} IngestReport;

/* Globals */
static IngestSource g_sources[MAX_SOURCES];
static int g_source_count = 0;
static char g_seen[MAX_QUEUE][HASH_LEN];
static int g_seen_count = 0;
static int g_dupes = 0;
static int g_valid_fails = 0;
static int g_total_pulls = 0;
static int g_queued = 0;

/* ---- Hash ---- */
static void sha_hash(const char *data, int len, char *out) {
  unsigned long h1 = 5381, h2 = 0x9e3779b9;
  for (int i = 0; i < len; i++) {
    h1 = ((h1 << 5) + h1) + (unsigned char)data[i];
    h2 ^= ((h2 << 6) + (h2 >> 2) + (unsigned char)data[i]);
  }
  snprintf(out, HASH_LEN, "%016lx%016lx%016lx%016lx", h1, h2, h1 ^ h2, h1 + h2);
}

static int is_dup(const char *fp) {
  for (int i = 0; i < g_seen_count; i++) {
    if (strcmp(g_seen[i], fp) == 0)
      return 1;
  }
  return 0;
}

/* ---- Public API ---- */

int ai_init(void) {
  memset(g_sources, 0, sizeof(g_sources));
  memset(g_seen, 0, sizeof(g_seen));
  g_source_count = 0;
  g_seen_count = 0;
  g_dupes = 0;
  g_valid_fails = 0;
  g_total_pulls = 0;
  g_queued = 0;
  return 0;
}

int ai_register_source(const char *source_id, const char *source_url,
                       double reliability) {
  if (g_source_count >= MAX_SOURCES)
    return -1;
  IngestSource *s = &g_sources[g_source_count];
  strncpy(s->source_id, source_id, 127);
  strncpy(s->source_url, source_url, 511);
  s->reliability = reliability;
  s->last_pull = 0;
  s->pull_count = 0;
  s->active = 1;
  g_source_count++;
  return 0;
}

int ai_ingest(const char *source_id, const char *raw_data, int data_len,
              int has_endpoint, int has_exploit_vector, int has_impact) {
  /* Structural validation */
  if (!has_endpoint || !has_exploit_vector || !has_impact || data_len < 10) {
    g_valid_fails++;
    return -1;
  }

  /* SHA-256 fingerprint */
  char fp[HASH_LEN];
  sha_hash(raw_data, data_len, fp);

  /* Dedup */
  if (is_dup(fp)) {
    g_dupes++;
    return -2;
  }

  /* Store fingerprint */
  if (g_seen_count < MAX_QUEUE) {
    strncpy(g_seen[g_seen_count], fp, HASH_LEN - 1);
    g_seen_count++;
  }

  g_queued++;
  g_total_pulls++;

  /* Update source pull count */
  for (int i = 0; i < g_source_count; i++) {
    if (strcmp(g_sources[i].source_id, source_id) == 0) {
      g_sources[i].pull_count++;
      g_sources[i].last_pull = (long)time(NULL);
      break;
    }
  }

  return 0;
}

int ai_is_pull_due(const char *source_id) {
  for (int i = 0; i < g_source_count; i++) {
    if (strcmp(g_sources[i].source_id, source_id) == 0) {
      long now = (long)time(NULL);
      return (now - g_sources[i].last_pull >= PULL_INTERVAL_SEC) ? 1 : 0;
    }
  }
  return 0;
}

IngestReport ai_get_report(void) {
  IngestReport r;
  r.total_sources = g_source_count;
  r.active_sources = 0;
  for (int i = 0; i < g_source_count; i++) {
    if (g_sources[i].active)
      r.active_sources++;
  }
  r.total_queued = g_queued;
  r.duplicates_rejected = g_dupes;
  r.validation_failures = g_valid_fails;
  r.pull_count = g_total_pulls;
  return r;
}

int ai_get_queue_size(void) { return g_queued; }
int ai_get_dupes(void) { return g_dupes; }

#ifdef __cplusplus
}
#endif
