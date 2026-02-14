/*
 * narrative_builder.cpp — Structured Narrative Builder
 *
 * Builds professional report narratives from recorded state.
 * NO AI generation — purely template + recorded data.
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int MAX_REPORT_SIZE = 16384;
static constexpr int MAX_EVIDENCE_REFS = 50;

// =========================================================================
// TYPES
// =========================================================================

struct VulnerabilityData {
  char vuln_type[64];  // e.g., "XSS", "SQLi", "SSRF"
  char endpoint[512];  // e.g., "/api/v1/search"
  char parameter[128]; // e.g., "q"
  char payload[1024];  // e.g., "<script>alert(1)</script>"
  char observed_response[1024];
  char impact_description[512];
  char root_cause[512];
  char severity_label[16]; // User-assigned only
  char scope_domain[256];
};

struct EvidenceRef {
  char hash[65];
  char type[32];
  char path[512];
};

struct ReportOutput {
  char title[256];
  char summary[2048];
  char affected_endpoint[512];
  char parameter[128];
  char reproduction_steps[4096];
  char technical_explanation[2048];
  char impact[1024];
  char scope_confirmation[512];
  char evidence_list[2048];
  char remediation[1024];
  int total_length;
  bool valid;
};

// =========================================================================
// NARRATIVE BUILDER
// =========================================================================

class NarrativeBuilder {
private:
  EvidenceRef evidence_[MAX_EVIDENCE_REFS];
  int evidence_count_;

public:
  NarrativeBuilder() : evidence_count_(0) {
    std::memset(evidence_, 0, sizeof(evidence_));
  }

  void add_evidence(const char *hash, const char *type, const char *path) {
    if (evidence_count_ >= MAX_EVIDENCE_REFS)
      return;
    EvidenceRef &e = evidence_[evidence_count_];
    std::strncpy(e.hash, hash, 64);
    std::strncpy(e.type, type, 31);
    std::strncpy(e.path, path, 511);
    evidence_count_++;
  }

  ReportOutput build(const VulnerabilityData &vuln, const char *title_template,
                     const char *summary_template, const char *repro_template,
                     const char *impact_template,
                     const char *remediation_template) {
    ReportOutput out;
    std::memset(&out, 0, sizeof(out));

    // Title
    std::snprintf(out.title, sizeof(out.title), title_template, vuln.vuln_type,
             vuln.endpoint, vuln.parameter);

    // Summary
    std::snprintf(out.summary, sizeof(out.summary), summary_template, vuln.endpoint,
             vuln.vuln_type, vuln.parameter, vuln.impact_description);

    // Affected endpoint
    std::snprintf(out.affected_endpoint, sizeof(out.affected_endpoint), "%s",
             vuln.endpoint);

    // Parameter
    std::snprintf(out.parameter, sizeof(out.parameter), "%s", vuln.parameter);

    // Reproduction steps
    std::snprintf(out.reproduction_steps, sizeof(out.reproduction_steps),
             repro_template, vuln.endpoint, vuln.parameter, vuln.payload,
             vuln.observed_response);

    // Technical explanation (from recorded root cause)
    std::snprintf(
        out.technical_explanation, sizeof(out.technical_explanation),
        "Root Cause Analysis:\n%s\n\n"
        "The %s parameter at %s does not implement proper input "
        "validation or output encoding. The injected payload (%s) was "
        "reflected/executed in the response, confirming the vulnerability.",
        vuln.root_cause, vuln.parameter, vuln.endpoint, vuln.payload);

    // Impact (observable only)
    std::snprintf(out.impact, sizeof(out.impact), impact_template,
             vuln.impact_description, vuln.observed_response);

    // Scope confirmation
    std::snprintf(out.scope_confirmation, sizeof(out.scope_confirmation),
             "This finding is within the approved scope: %s. "
             "The affected endpoint %s is part of the target application.",
             vuln.scope_domain, vuln.endpoint);

    // Evidence list
    int pos = 0;
    pos += std::snprintf(out.evidence_list + pos, sizeof(out.evidence_list) - pos,
                    "Attached Evidence:\n");
    for (int i = 0;
         i < evidence_count_ && pos < (int)sizeof(out.evidence_list) - 128;
         i++) {
      pos += std::snprintf(out.evidence_list + pos, sizeof(out.evidence_list) - pos,
                      "  %d. [%s] %s (hash: %.16s...)\n", i + 1,
                      evidence_[i].type, evidence_[i].path, evidence_[i].hash);
    }

    // Remediation
    std::snprintf(out.remediation, sizeof(out.remediation), remediation_template,
             vuln.parameter);

    out.total_length = (int)(std::strlen(out.title) + std::strlen(out.summary) +
                             std::strlen(out.reproduction_steps) +
                             std::strlen(out.technical_explanation) +
                             std::strlen(out.impact) + std::strlen(out.remediation));
    out.valid = (out.total_length > 100);
    return out;
  }

  int evidence_count() const { return evidence_count_; }

  // Guards
  static bool can_add_ai_text() { return false; }
  static bool can_modify_after_build() { return false; }
};
