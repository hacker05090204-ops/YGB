/*
 * evidence_binding_enforcer.cpp — Zero-Hallucination Report Engine (Phase 4)
 *
 * ██████████████████████████████████████████████████████████████████████
 * BOUNTY-READY — EVIDENCE BINDING ENFORCER
 * ██████████████████████████████████████████████████████████████████████
 *
 * Performance-critical (C++):
 *   1. Sentence-evidence linking — every claim must bind to evidence
 *   2. Reject unbound statements — hallucination = unbound claim
 *   3. Evidence hash verification — evidence must be verifiable
 *
 * Compile (Windows):
 *   g++ -shared -O2 -o evidence_binding_enforcer.dll
 * evidence_binding_enforcer.cpp
 */

#include <cstdio>
#include <cstring>

#ifdef _WIN32
#define EBE_EXPORT __declspec(dllexport)
#else
#define EBE_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* ================================================================== */
/*  CONSTANTS                                                         */
/* ================================================================== */

#define MAX_SENTENCES 512
#define MAX_EVIDENCE 256
#define MAX_TEXT_LEN 2048
#define MAX_HASH_LEN 65
#define BINDING_REQUIRED 1.0 /* 100% of claims must be bound */

/* ================================================================== */
/*  STATE                                                             */
/* ================================================================== */

typedef struct {
  char text[MAX_TEXT_LEN];
  char evidence_hash[MAX_HASH_LEN];
  int bound;    /* 1 = bound to evidence, 0 = unbound */
  int is_claim; /* 1 = factual claim, 0 = transition/filler */
} SentenceBinding;

typedef struct {
  char hash[MAX_HASH_LEN];
  char type[64];        /* "response_hash", "screenshot", "log_entry", etc. */
  int referenced_count; /* How many sentences reference this */
} EvidenceItem;

typedef struct {
  int total_sentences;
  int total_claims;
  int bound_claims;
  int unbound_claims;
  int total_evidence;
  double binding_ratio; /* bound_claims / total_claims */
  int passed;
  char violation[256];
} BindingReport;

static SentenceBinding g_sentences[MAX_SENTENCES];
static EvidenceItem g_evidence[MAX_EVIDENCE];
static int g_sentence_count = 0;
static int g_evidence_count = 0;
static BindingReport g_report;

/* ================================================================== */
/*  REGISTRATION API                                                  */
/* ================================================================== */

EBE_EXPORT void ebe_reset(void) {
  g_sentence_count = 0;
  g_evidence_count = 0;
  memset(&g_report, 0, sizeof(g_report));
  memset(g_sentences, 0, sizeof(g_sentences));
  memset(g_evidence, 0, sizeof(g_evidence));
}

/*
 * register_evidence — Register a piece of evidence with its hash.
 * Returns: evidence index, or -1 if full.
 */
EBE_EXPORT int register_evidence(const char *hash, const char *evidence_type) {
  if (g_evidence_count >= MAX_EVIDENCE)
    return -1;
  int idx = g_evidence_count++;
  strncpy(g_evidence[idx].hash, hash, MAX_HASH_LEN - 1);
  strncpy(g_evidence[idx].type, evidence_type, 63);
  g_evidence[idx].referenced_count = 0;
  return idx;
}

/*
 * register_sentence — Register a report sentence.
 * is_claim: 1 if this is a factual claim, 0 if transitional/filler
 * evidence_hash: hash of binding evidence (empty = unbound)
 *
 * Returns: sentence index, or -1 if full.
 */
EBE_EXPORT int register_sentence(const char *text, int is_claim,
                                 const char *evidence_hash) {
  if (g_sentence_count >= MAX_SENTENCES)
    return -1;
  int idx = g_sentence_count++;

  strncpy(g_sentences[idx].text, text, MAX_TEXT_LEN - 1);
  g_sentences[idx].is_claim = is_claim;

  if (evidence_hash && strlen(evidence_hash) > 0) {
    strncpy(g_sentences[idx].evidence_hash, evidence_hash, MAX_HASH_LEN - 1);

    /* Find evidence and increment reference count */
    int found = 0;
    for (int i = 0; i < g_evidence_count; i++) {
      if (strcmp(g_evidence[i].hash, evidence_hash) == 0) {
        g_evidence[i].referenced_count++;
        found = 1;
        break;
      }
    }
    g_sentences[idx].bound = found ? 1 : 0;
  } else {
    g_sentences[idx].bound = 0;
  }

  return idx;
}

/* ================================================================== */
/*  VERIFICATION                                                      */
/* ================================================================== */

/*
 * verify_bindings — Check that all claims are bound to registered evidence.
 * Returns: 1 if all claims bound, 0 if hallucination detected.
 */
EBE_EXPORT int verify_bindings(void) {
  memset(&g_report, 0, sizeof(g_report));
  g_report.total_sentences = g_sentence_count;
  g_report.total_evidence = g_evidence_count;

  int claims = 0, bound = 0;
  for (int i = 0; i < g_sentence_count; i++) {
    if (g_sentences[i].is_claim) {
      claims++;
      if (g_sentences[i].bound) {
        bound++;
      }
    }
  }

  g_report.total_claims = claims;
  g_report.bound_claims = bound;
  g_report.unbound_claims = claims - bound;
  g_report.binding_ratio = claims > 0 ? (double)bound / claims : 1.0;

  if (g_report.unbound_claims > 0) {
    /* Find first unbound claim for violation message */
    for (int i = 0; i < g_sentence_count; i++) {
      if (g_sentences[i].is_claim && !g_sentences[i].bound) {
        snprintf(g_report.violation, sizeof(g_report.violation),
                 "Unbound claim [%d]: %.80s...", i, g_sentences[i].text);
        break;
      }
    }
    g_report.passed = 0;
    return 0;
  }

  g_report.passed = 1;
  return 1;
}

/* ================================================================== */
/*  STATUS QUERIES                                                    */
/* ================================================================== */

EBE_EXPORT int ebe_passed(void) { return g_report.passed; }
EBE_EXPORT int ebe_total_claims(void) { return g_report.total_claims; }
EBE_EXPORT int ebe_bound_claims(void) { return g_report.bound_claims; }
EBE_EXPORT int ebe_unbound_claims(void) { return g_report.unbound_claims; }
EBE_EXPORT int ebe_total_evidence(void) { return g_report.total_evidence; }

EBE_EXPORT double ebe_binding_ratio(void) { return g_report.binding_ratio; }

EBE_EXPORT void ebe_get_violation(char *out, int len) {
  strncpy(out, g_report.violation, len - 1);
  out[len - 1] = '\0';
}

#ifdef __cplusplus
}
#endif
