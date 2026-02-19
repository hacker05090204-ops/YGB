/**
 * field_tasklist_engine.cpp — Dynamic 22+ Field Sequential Ladder
 *
 * Master fields (must certify first):
 *   1. Client-Side Application Security
 *   2. API / Business Logic Security
 *
 * Extended ladder (sequential, one at a time):
 *   3. Subdomain Intelligence      → 4.  Authentication Systems
 *   5. Authorization Logic          → 6.  Rate Limiting
 *   7. Token Security               → 8.  Session Management
 *   9. CORS Misconfiguration        → 10. SSRF
 *  11. Request Smuggling            → 12. Template Injection
 *  13. Cache Poisoning              → 14. Cloud Misconfiguration
 *  15. IAM                          → 16. CI/CD Security
 *  17. Container Security           → 18. Kubernetes
 *  19. WAF Bypass                   → 20. CDN Misconfiguration
 *  21. Data Leakage                 → 22. Supply Chain
 *  23. Dependency Confusion
 *
 * Rules:
 *   - Only ONE active field at a time
 *   - No skipping
 *   - 7-day stability before progressing
 *   - No cross-field dataset sharing
 */

#include <cstdint>
#include <cstdio>
#include <cstring>


namespace field_lifecycle {

// =========================================================================
// TASKLIST FIELD
// =========================================================================

struct TaskField {
  uint32_t id;
  char name[64];
  bool is_master;
  bool certified;
  bool active;
  bool locked; // true = cannot start yet
  uint32_t stability_days;
  double precision;
  double fpr;
  double dup_detection;
  double ece;
};

// =========================================================================
// UNLOCK RESULT
// =========================================================================

struct UnlockResult {
  bool allowed;
  uint32_t field_id;
  char reason[256];
};

// =========================================================================
// TASKLIST ENGINE
// =========================================================================

static constexpr uint32_t TOTAL_FIELDS = 23;

class FieldTasklistEngine {
public:
  static constexpr bool ALLOW_SKIP = false;
  static constexpr bool ALLOW_CROSS_FIELD_DATA = false;

  FieldTasklistEngine() : active_id_(0) {
    const char *names[] = {"Client-Side Application Security",
                           "API / Business Logic Security",
                           "Subdomain Intelligence",
                           "Authentication Systems",
                           "Authorization Logic",
                           "Rate Limiting",
                           "Token Security",
                           "Session Management",
                           "CORS Misconfiguration",
                           "SSRF",
                           "Request Smuggling",
                           "Template Injection",
                           "Cache Poisoning",
                           "Cloud Misconfiguration",
                           "IAM",
                           "CI/CD Security",
                           "Container Security",
                           "Kubernetes",
                           "WAF Bypass",
                           "CDN Misconfiguration",
                           "Data Leakage",
                           "Supply Chain",
                           "Dependency Confusion"};

    for (uint32_t i = 0; i < TOTAL_FIELDS; ++i) {
      std::memset(&fields_[i], 0, sizeof(TaskField));
      fields_[i].id = i;
      std::strncpy(fields_[i].name, names[i], 63);
      fields_[i].name[63] = '\0';
      fields_[i].is_master = (i < 2);
      fields_[i].locked = (i > 0); // only field 0 unlocked initially
      fields_[i].certified = false;
      fields_[i].active = false;
    }
    fields_[0].active = true;
    fields_[0].locked = false;
    active_id_ = 0;
  }

  // Try to unlock the next field after current is certified
  UnlockResult try_unlock_next(uint32_t current_id) {
    UnlockResult r;
    std::memset(&r, 0, sizeof(r));

    if (current_id >= TOTAL_FIELDS) {
      r.allowed = false;
      std::snprintf(r.reason, sizeof(r.reason), "INVALID_FIELD_ID");
      return r;
    }

    // Current must be certified
    if (!fields_[current_id].certified) {
      r.allowed = false;
      std::snprintf(r.reason, sizeof(r.reason), "FIELD_NOT_CERTIFIED: '%s'",
                    fields_[current_id].name);
      return r;
    }

    // Stability gate
    if (fields_[current_id].stability_days < 7) {
      r.allowed = false;
      std::snprintf(
          r.reason, sizeof(r.reason), "STABILITY_GATE: %u/7 days for '%s'",
          fields_[current_id].stability_days, fields_[current_id].name);
      return r;
    }

    // Master fields: both must be certified before ladder
    if (current_id == 0 && !fields_[1].certified) {
      // Unlock field 1 (API)
      r.field_id = 1;
    } else if (current_id == 1 && fields_[0].certified) {
      // Both masters certified → unlock first ladder field
      r.field_id = 2;
    } else if (current_id >= 2 && current_id + 1 < TOTAL_FIELDS) {
      // Ladder progression
      r.field_id = current_id + 1;
    } else {
      r.allowed = false;
      std::snprintf(r.reason, sizeof(r.reason),
                    "ALL_FIELDS_COMPLETE or WAITING_FOR_MASTER");
      return r;
    }

    // Unlock next
    fields_[current_id].active = false;
    fields_[r.field_id].locked = false;
    fields_[r.field_id].active = true;
    active_id_ = r.field_id;

    r.allowed = true;
    std::snprintf(r.reason, sizeof(r.reason), "UNLOCKED: '%s' (id=%u)",
                  fields_[r.field_id].name, r.field_id);
    return r;
  }

  // Get current active field
  const TaskField *active_field() const {
    return (active_id_ < TOTAL_FIELDS) ? &fields_[active_id_] : nullptr;
  }

  const TaskField *field(uint32_t id) const {
    return (id < TOTAL_FIELDS) ? &fields_[id] : nullptr;
  }

  uint32_t certified_count() const {
    uint32_t c = 0;
    for (uint32_t i = 0; i < TOTAL_FIELDS; ++i)
      if (fields_[i].certified)
        ++c;
    return c;
  }

  uint32_t total_fields() const { return TOTAL_FIELDS; }

  // Persist entire ladder state
  bool persist(const char *path) const {
    char tmp[512];
    std::snprintf(tmp, sizeof(tmp), "%s.tmp", path);
    FILE *f = std::fopen(tmp, "w");
    if (!f)
      return false;
    std::fprintf(f, "{\"active\":%u,\"certified\":%u,\"total\":%u,\"fields\":[",
                 active_id_, certified_count(), TOTAL_FIELDS);
    for (uint32_t i = 0; i < TOTAL_FIELDS; ++i) {
      const auto &fd = fields_[i];
      std::fprintf(
          f,
          "%s{\"id\":%u,\"name\":\"%s\",\"master\":%s,"
          "\"certified\":%s,\"active\":%s,\"locked\":%s,"
          "\"prec\":%.4f,\"fpr\":%.4f,\"dup\":%.4f,\"ece\":%.4f,"
          "\"stab\":%u}",
          i ? "," : "", fd.id, fd.name, fd.is_master ? "true" : "false",
          fd.certified ? "true" : "false", fd.active ? "true" : "false",
          fd.locked ? "true" : "false", fd.precision, fd.fpr, fd.dup_detection,
          fd.ece, fd.stability_days);
    }
    std::fprintf(f, "]}\n");
    std::fflush(f);
    std::fclose(f);
    std::remove(path);
    return std::rename(tmp, path) == 0;
  }

private:
  TaskField fields_[TOTAL_FIELDS];
  uint32_t active_id_;
};

} // namespace field_lifecycle
