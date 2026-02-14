/*
 * template_registry.cpp — Deterministic Report Template Registry
 *
 * RULES:
 *   - No generative AI text
 *   - Only structured deterministic templates
 *   - 20+ English + Hindi templates
 *   - Randomized selection from bounded safe vocabulary
 *   - Severity labels user-assigned only
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>


// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int MAX_TEMPLATES = 30;
static constexpr int MAX_TEMPLATE_TEXT = 2048;
static constexpr int MAX_SECTION = 512;
static constexpr int MAX_SECTIONS = 12;

// =========================================================================
// TYPES
// =========================================================================

enum class ReportLanguage { ENGLISH, HINDI };

enum class TemplateSection {
  TITLE,
  SUMMARY,
  AFFECTED_ENDPOINT,
  PARAMETER,
  REPRODUCTION_STEPS,
  TECHNICAL_EXPLANATION,
  IMPACT,
  SCOPE_CONFIRMATION,
  EVIDENCE_LIST,
  REMEDIATION
};

struct ReportTemplate {
  int id;
  ReportLanguage language;
  TemplateSection section;
  char pattern[MAX_TEMPLATE_TEXT];
  int variation_count; // Number of word variations
};

// =========================================================================
// ENGLISH TEMPLATES
// =========================================================================

static const ReportTemplate ENGLISH_TITLE_TEMPLATES[] = {
    {0, ReportLanguage::ENGLISH, TemplateSection::TITLE,
     "%s Vulnerability in %s via %s Parameter", 0},
    {1, ReportLanguage::ENGLISH, TemplateSection::TITLE,
     "%s Weakness Identified at %s Endpoint (%s)", 0},
    {2, ReportLanguage::ENGLISH, TemplateSection::TITLE,
     "Security Issue: %s in %s — %s Input", 0},
};

static const ReportTemplate ENGLISH_SUMMARY_TEMPLATES[] = {
    {0, ReportLanguage::ENGLISH, TemplateSection::SUMMARY,
     "A %s vulnerability was identified in the %s endpoint. The %s parameter "
     "accepts unsanitized input which allows an attacker to %s. This was "
     "confirmed through manual testing and evidence is attached.",
     0},
    {1, ReportLanguage::ENGLISH, TemplateSection::SUMMARY,
     "During testing of the %s endpoint, a %s issue was discovered in the "
     "%s parameter. The application does not properly validate input, "
     "enabling %s. Reproduction steps and evidence are provided below.",
     0},
    {2, ReportLanguage::ENGLISH, TemplateSection::SUMMARY,
     "The %s endpoint contains a %s weakness via the %s parameter. "
     "Insufficient input validation permits %s. "
     "This finding was verified through controlled testing.",
     0},
};

static const ReportTemplate ENGLISH_REPRODUCTION_TEMPLATES[] = {
    {0, ReportLanguage::ENGLISH, TemplateSection::REPRODUCTION_STEPS,
     "1. Navigate to %s\n"
     "2. Locate the %s parameter in the request\n"
     "3. Inject the following payload: %s\n"
     "4. Observe the response indicating %s\n"
     "5. Confirm the behavior is reproducible",
     0},
    {1, ReportLanguage::ENGLISH, TemplateSection::REPRODUCTION_STEPS,
     "1. Send a request to %s\n"
     "2. Modify the %s parameter with: %s\n"
     "3. Submit the request\n"
     "4. The server responds with %s\n"
     "5. This confirms the vulnerability",
     0},
};

static const ReportTemplate ENGLISH_IMPACT_TEMPLATES[] = {
    {0, ReportLanguage::ENGLISH, TemplateSection::IMPACT,
     "An attacker could exploit this vulnerability to %s. "
     "Based on the observed behavior, the impact is limited to %s. "
     "No data exfiltration was confirmed during testing.",
     0},
    {1, ReportLanguage::ENGLISH, TemplateSection::IMPACT,
     "This vulnerability could allow %s. "
     "The observed impact during testing was %s. "
     "The actual impact may vary depending on application context.",
     0},
};

static const ReportTemplate ENGLISH_REMEDIATION_TEMPLATES[] = {
    {0, ReportLanguage::ENGLISH, TemplateSection::REMEDIATION,
     "It is recommended to:\n"
     "- Validate and sanitize all user input for the %s parameter\n"
     "- Implement proper encoding at the output layer\n"
     "- Consider adding a Content Security Policy header\n"
     "- Review similar endpoints for the same pattern",
     0},
    {1, ReportLanguage::ENGLISH, TemplateSection::REMEDIATION,
     "Suggested remediation:\n"
     "- Apply input validation to the %s parameter\n"
     "- Use parameterized queries or appropriate encoding\n"
     "- Implement a Web Application Firewall rule\n"
     "- Conduct a broader review of input handling",
     0},
};

// =========================================================================
// HINDI TEMPLATES
// =========================================================================

static const ReportTemplate HINDI_TITLE_TEMPLATES[] = {
    {0, ReportLanguage::HINDI, TemplateSection::TITLE,
     "%s — %s Endpoint mein %s Parameter ke through Suraksha Kamzori", 0},
    {1, ReportLanguage::HINDI, TemplateSection::TITLE,
     "Suraksha Samasya: %s (%s Endpoint — %s Input)", 0},
};

static const ReportTemplate HINDI_SUMMARY_TEMPLATES[] = {
    {0, ReportLanguage::HINDI, TemplateSection::SUMMARY,
     "%s endpoint mein ek %s kamzori payi gayi. %s parameter mein "
     "ashuddh input diya ja sakta hai, jisse %s ho sakta hai. "
     "Yeh manual testing se confirm kiya gaya hai.",
     0},
    {1, ReportLanguage::HINDI, TemplateSection::SUMMARY,
     "%s endpoint ki jaanch ke dauraan, %s parameter mein ek %s "
     "samasya mili. Application sahee tarike se input validate nahi "
     "karta, jisse %s sambhav hai.",
     0},
};

static const ReportTemplate HINDI_REPRODUCTION_TEMPLATES[] = {
    {0, ReportLanguage::HINDI, TemplateSection::REPRODUCTION_STEPS,
     "1. %s par navigate karein\n"
     "2. Request mein %s parameter dhundhein\n"
     "3. Yeh payload inject karein: %s\n"
     "4. Response mein %s dekhein\n"
     "5. Vyavhaar dobaara confirm karein",
     0},
};

// =========================================================================
// TEMPLATE REGISTRY
// =========================================================================

class TemplateRegistry {
private:
  unsigned int seed_;

  int select_index(int max) {
    // Simple deterministic PRNG (bounded safe)
    seed_ = seed_ * 1103515245 + 12345;
    return (int)((seed_ >> 16) % (unsigned int)max);
  }

public:
  TemplateRegistry() : seed_((unsigned int)std::time(nullptr)) {}

  explicit TemplateRegistry(unsigned int seed) : seed_(seed) {}

  const char *get_title_template(ReportLanguage lang) {
    if (lang == ReportLanguage::HINDI) {
      int idx = select_index(2);
      return HINDI_TITLE_TEMPLATES[idx].pattern;
    }
    int idx = select_index(3);
    return ENGLISH_TITLE_TEMPLATES[idx].pattern;
  }

  const char *get_summary_template(ReportLanguage lang) {
    if (lang == ReportLanguage::HINDI) {
      int idx = select_index(2);
      return HINDI_SUMMARY_TEMPLATES[idx].pattern;
    }
    int idx = select_index(3);
    return ENGLISH_SUMMARY_TEMPLATES[idx].pattern;
  }

  const char *get_reproduction_template(ReportLanguage lang) {
    if (lang == ReportLanguage::HINDI) {
      return HINDI_REPRODUCTION_TEMPLATES[0].pattern;
    }
    int idx = select_index(2);
    return ENGLISH_REPRODUCTION_TEMPLATES[idx].pattern;
  }

  const char *get_impact_template(ReportLanguage lang) {
    (void)lang; // Hindi impact uses English for now
    int idx = select_index(2);
    return ENGLISH_IMPACT_TEMPLATES[idx].pattern;
  }

  const char *get_remediation_template(ReportLanguage lang) {
    (void)lang;
    int idx = select_index(2);
    return ENGLISH_REMEDIATION_TEMPLATES[idx].pattern;
  }

  // Guards
  static bool can_add_ai_generated_text() { return false; }
  static bool can_modify_templates_at_runtime() { return false; }
  static bool can_unlock_generative_mode() { return false; }
};
