/*
 * ingestion_bridge.cpp — C++ → Python Bridge for Ingestion Engine
 *
 * Wraps ingestion_engine.cpp with bridge-specific exports for ctypes:
 *   bridge_init()                    — Initialize engine
 *   bridge_get_count()               — Total ingested count
 *   bridge_get_verified_count()      — Verified-only count
 *   bridge_fetch_verified_sample()   — Get one verified sample by index
 *   bridge_get_sample_field()        — Get a string field from sample
 *   bridge_get_sample_reliability()  — Get reliability score
 *   bridge_get_dataset_manifest_hash() — SHA-256 of all ingested data
 *
 * Compile (Windows):
 *   cl /LD /EHsc ingestion_bridge.cpp ingestion_engine.cpp
 * /Fe:ingestion_bridge.dll
 *
 * Compile (Linux):
 *   g++ -shared -fPIC -o libingestion_bridge.so ingestion_bridge.cpp
 * ingestion_engine.cpp
 */

#include <cstdio>
#include <cstring>

/* Include ingestion_engine types + API */
#include <cstdlib>
#include <ctime>

/* Forward-declare ingestion_engine API (defined in ingestion_engine.cpp) */
#ifdef __cplusplus
extern "C" {
#endif

#define MAX_FIELD_LEN 512
#define SHA256_HEX_LEN 65
#define MAX_INGESTED 300000

typedef struct {
  char endpoint[MAX_FIELD_LEN];
  char parameters[MAX_FIELD_LEN];
  char exploit_vector[MAX_FIELD_LEN];
  char impact[MAX_FIELD_LEN];
  char source_tag[MAX_FIELD_LEN];
  char fingerprint[SHA256_HEX_LEN];
  double reliability_score;
  int verified;
  long ingested_at;
} IngestedSample;

typedef struct {
  int total_ingested;
  int duplicates_rejected;
  int integrity_failures;
  int rate_limited;
  double samples_per_sec;
} IngestionStats;

/* From ingestion_engine.cpp */
extern int ingestion_init(void);
extern int ingest_sample(const char *endpoint, const char *parameters,
                         const char *exploit_vector, const char *impact,
                         const char *source_tag, double reliability);
extern int ingestion_get_count(void);
extern int ingestion_get_dupes(void);
extern void ingestion_get_stats(IngestionStats *out);
extern const IngestedSample *ingestion_get_sample(int idx);

#ifdef __cplusplus
}
#endif

/* ================================================================== */
/*  BRIDGE API — Exported for Python ctypes                           */
/* ================================================================== */

#ifdef _WIN32
#define BRIDGE_EXPORT __declspec(dllexport)
#else
#define BRIDGE_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* ---- Init ---- */
BRIDGE_EXPORT int bridge_init(void) { return ingestion_init(); }

/* ---- Counts ---- */
BRIDGE_EXPORT int bridge_get_count(void) { return ingestion_get_count(); }

BRIDGE_EXPORT int bridge_get_verified_count(void) {
  int total = ingestion_get_count();
  int verified = 0;
  for (int i = 0; i < total; i++) {
    const IngestedSample *s = ingestion_get_sample(i);
    if (s && s->verified) {
      verified++;
    }
  }
  return verified;
}

/* ---- Fetch verified sample by verified-index ---- */
BRIDGE_EXPORT int bridge_fetch_verified_sample(
    int verified_idx, char *out_endpoint, int ep_len, char *out_parameters,
    int param_len, char *out_exploit_vector, int ev_len, char *out_impact,
    int imp_len, char *out_source_tag, int st_len, char *out_fingerprint,
    int fp_len, double *out_reliability, long *out_ingested_at) {
  int total = ingestion_get_count();
  int v_count = 0;

  for (int i = 0; i < total; i++) {
    const IngestedSample *s = ingestion_get_sample(i);
    if (!s || !s->verified)
      continue;

    if (v_count == verified_idx) {
      /* Copy fields */
      strncpy(out_endpoint, s->endpoint, ep_len - 1);
      out_endpoint[ep_len - 1] = '\0';

      strncpy(out_parameters, s->parameters, param_len - 1);
      out_parameters[param_len - 1] = '\0';

      strncpy(out_exploit_vector, s->exploit_vector, ev_len - 1);
      out_exploit_vector[ev_len - 1] = '\0';

      strncpy(out_impact, s->impact, imp_len - 1);
      out_impact[imp_len - 1] = '\0';

      strncpy(out_source_tag, s->source_tag, st_len - 1);
      out_source_tag[st_len - 1] = '\0';

      strncpy(out_fingerprint, s->fingerprint, fp_len - 1);
      out_fingerprint[fp_len - 1] = '\0';

      *out_reliability = s->reliability_score;
      *out_ingested_at = s->ingested_at;

      return 0; /* success */
    }
    v_count++;
  }

  return -1; /* verified_idx out of range */
}

/* ---- Get sample batch (verified only) ---- */
BRIDGE_EXPORT int
bridge_get_sample_batch(int start, int count,
                        char *out_endpoints, /* count * MAX_FIELD_LEN buffer */
                        char *out_vectors,   /* count * MAX_FIELD_LEN buffer */
                        char *out_impacts,   /* count * MAX_FIELD_LEN buffer */
                        double *out_reliabilities, int *out_actual_count) {
  int total = ingestion_get_count();
  int v_idx = 0;
  int written = 0;

  for (int i = 0; i < total && written < count; i++) {
    const IngestedSample *s = ingestion_get_sample(i);
    if (!s || !s->verified)
      continue;

    if (v_idx >= start) {
      int offset = written * MAX_FIELD_LEN;
      strncpy(out_endpoints + offset, s->endpoint, MAX_FIELD_LEN - 1);
      strncpy(out_vectors + offset, s->exploit_vector, MAX_FIELD_LEN - 1);
      strncpy(out_impacts + offset, s->impact, MAX_FIELD_LEN - 1);
      out_reliabilities[written] = s->reliability_score;
      written++;
    }
    v_idx++;
  }

  *out_actual_count = written;
  return 0;
}

/* ---- Dataset manifest hash ---- */
BRIDGE_EXPORT void bridge_get_dataset_manifest_hash(char *out_hash,
                                                    int hash_len) {
  /*
   * Compute a composite hash of ALL ingested verified samples.
   * Uses djb2 double-hash (same as ingestion_engine fingerprint).
   */
  unsigned long h1 = 5381, h2 = 0x9e3779b9;
  int total = ingestion_get_count();
  int verified_count = 0;

  for (int i = 0; i < total; i++) {
    const IngestedSample *s = ingestion_get_sample(i);
    if (!s || !s->verified)
      continue;

    /* Hash the fingerprint of each verified sample */
    const char *fp = s->fingerprint;
    int fp_len = (int)strlen(fp);
    for (int j = 0; j < fp_len; j++) {
      h1 = ((h1 << 5) + h1) + (unsigned char)fp[j];
      h2 ^= ((h2 << 6) + (h2 >> 2) + (unsigned char)fp[j]);
    }
    verified_count++;
  }

  /* Include verified count in hash */
  unsigned char vc_bytes[4];
  vc_bytes[0] = (verified_count >> 24) & 0xFF;
  vc_bytes[1] = (verified_count >> 16) & 0xFF;
  vc_bytes[2] = (verified_count >> 8) & 0xFF;
  vc_bytes[3] = verified_count & 0xFF;
  for (int i = 0; i < 4; i++) {
    h1 = ((h1 << 5) + h1) + vc_bytes[i];
    h2 ^= ((h2 << 6) + (h2 >> 2) + vc_bytes[i]);
  }

  snprintf(out_hash, hash_len, "%016lx%016lx%016lx%016lx", h1, h2, h1 ^ h2,
           h1 + h2);
}

/* ---- Stats ---- */
BRIDGE_EXPORT void bridge_get_stats(int *total_ingested, int *verified_count,
                                    int *duplicates_rejected,
                                    int *integrity_failures) {
  IngestionStats stats;
  ingestion_get_stats(&stats);

  *total_ingested = stats.total_ingested;
  *verified_count = bridge_get_verified_count();
  *duplicates_rejected = stats.duplicates_rejected;
  *integrity_failures = stats.integrity_failures;
}

/* ---- Ingest (for feeding data from Python) ---- */
BRIDGE_EXPORT int
bridge_ingest_sample(const char *endpoint, const char *parameters,
                     const char *exploit_vector, const char *impact,
                     const char *source_tag, double reliability) {
  return ingest_sample(endpoint, parameters, exploit_vector, impact, source_tag,
                       reliability);
}

/* ================================================================== */
/*  ANTI-TAMPER — Self-hash verification (Phase 7)                    */
/* ================================================================== */

/*
 * Minimal SHA-256 for self-hash (same as module_integrity_guard.cpp).
 * Inlined here so the bridge is self-contained.
 */
static const unsigned int _K256[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
    0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
};

#define _RR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))
#define _CH(x, y, z) (((x) & (y)) ^ ((~(x)) & (z)))
#define _MAJ(x, y, z) (((x) & (y)) ^ ((x) & (z)) ^ ((y) & (z)))
#define _S0(x) (_RR(x, 2) ^ _RR(x, 13) ^ _RR(x, 22))
#define _S1(x) (_RR(x, 6) ^ _RR(x, 11) ^ _RR(x, 25))
#define _s0(x) (_RR(x, 7) ^ _RR(x, 18) ^ ((x) >> 3))
#define _s1(x) (_RR(x, 17) ^ _RR(x, 19) ^ ((x) >> 10))

typedef struct {
  unsigned int h[8];
  unsigned char buf[64];
  unsigned long long total;
} _SHA256;

static void _sha256_init(_SHA256 *c) {
  c->h[0] = 0x6a09e667;
  c->h[1] = 0xbb67ae85;
  c->h[2] = 0x3c6ef372;
  c->h[3] = 0xa54ff53a;
  c->h[4] = 0x510e527f;
  c->h[5] = 0x9b05688c;
  c->h[6] = 0x1f83d9ab;
  c->h[7] = 0x5be0cd19;
  c->total = 0;
}

static void _sha256_transform(_SHA256 *c, const unsigned char *b) {
  unsigned int w[64], a, bb, cc, d, e, f, g, hh, t1, t2;
  int i;
  for (i = 0; i < 16; i++)
    w[i] = (b[i * 4] << 24) | (b[i * 4 + 1] << 16) | (b[i * 4 + 2] << 8) |
           b[i * 4 + 3];
  for (i = 16; i < 64; i++)
    w[i] = _s1(w[i - 2]) + w[i - 7] + _s0(w[i - 15]) + w[i - 16];
  a = c->h[0];
  bb = c->h[1];
  cc = c->h[2];
  d = c->h[3];
  e = c->h[4];
  f = c->h[5];
  g = c->h[6];
  hh = c->h[7];
  for (i = 0; i < 64; i++) {
    t1 = hh + _S1(e) + _CH(e, f, g) + _K256[i] + w[i];
    t2 = _S0(a) + _MAJ(a, bb, cc);
    hh = g;
    g = f;
    f = e;
    e = d + t1;
    d = cc;
    cc = bb;
    bb = a;
    a = t1 + t2;
  }
  c->h[0] += a;
  c->h[1] += bb;
  c->h[2] += cc;
  c->h[3] += d;
  c->h[4] += e;
  c->h[5] += f;
  c->h[6] += g;
  c->h[7] += hh;
}

static void _sha256_update(_SHA256 *c, const unsigned char *d,
                           unsigned long l) {
  unsigned long i;
  unsigned int idx = (unsigned int)(c->total & 63);
  c->total += l;
  for (i = 0; i < l; i++) {
    c->buf[idx++] = d[i];
    if (idx == 64) {
      _sha256_transform(c, c->buf);
      idx = 0;
    }
  }
}

static void _sha256_final(_SHA256 *c, unsigned char out[32]) {
  unsigned long long bits = c->total * 8;
  unsigned int idx = (unsigned int)(c->total & 63);
  int i;
  c->buf[idx++] = 0x80;
  if (idx > 56) {
    while (idx < 64)
      c->buf[idx++] = 0;
    _sha256_transform(c, c->buf);
    idx = 0;
  }
  while (idx < 56)
    c->buf[idx++] = 0;
  for (i = 7; i >= 0; i--)
    c->buf[56 + (7 - i)] = (unsigned char)(bits >> (i * 8));
  _sha256_transform(c, c->buf);
  for (i = 0; i < 8; i++) {
    out[i * 4] = (unsigned char)(c->h[i] >> 24);
    out[i * 4 + 1] = (unsigned char)(c->h[i] >> 16);
    out[i * 4 + 2] = (unsigned char)(c->h[i] >> 8);
    out[i * 4 + 3] = (unsigned char)(c->h[i]);
  }
}

static char g_self_hash[65] = {0};
static int g_self_verified = 0;

/*
 * bridge_self_verify — Anti-tamper self-hash verification.
 *
 * Computes SHA-256 of the bridge DLL file itself.
 * Returns 1 if hash is computed successfully, 0 on failure.
 * The hash is stored for the module_integrity_guard to cross-check.
 */
BRIDGE_EXPORT int bridge_self_verify(const char *dll_path) {
  FILE *fp = fopen(dll_path, "rb");
  if (!fp) {
    g_self_verified = 0;
    return 0;
  }

  _SHA256 ctx;
  _sha256_init(&ctx);
  unsigned char buf[4096];
  size_t n;
  while ((n = fread(buf, 1, sizeof(buf), fp)) > 0) {
    _sha256_update(&ctx, buf, (unsigned long)n);
  }
  fclose(fp);

  unsigned char hash[32];
  _sha256_final(&ctx, hash);

  const char hex[] = "0123456789abcdef";
  for (int i = 0; i < 32; i++) {
    g_self_hash[i * 2] = hex[(hash[i] >> 4) & 0xf];
    g_self_hash[i * 2 + 1] = hex[hash[i] & 0xf];
  }
  g_self_hash[64] = '\0';
  g_self_verified = 1;

  return 1;
}

/* Get the computed self-hash */
BRIDGE_EXPORT void bridge_get_self_hash(char *out, int len) {
  strncpy(out, g_self_hash, len - 1);
  out[len - 1] = '\0';
}

BRIDGE_EXPORT int bridge_is_self_verified(void) { return g_self_verified; }

#ifdef __cplusplus
}
#endif
