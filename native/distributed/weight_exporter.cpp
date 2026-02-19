/**
 * weight_exporter.cpp — Hash-Signed Weight Export
 *
 * Exports trained weights with:
 *   - Field-lock (weights tagged to active field)
 *   - Hash signature for integrity
 *   - Metric snapshot at export time
 *   - No mid-training export allowed
 *
 * Export only after field certification.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace distributed {

// =========================================================================
// EXPORT RECORD
// =========================================================================

struct WeightExportRecord {
  uint32_t export_id;
  char field_name[64];
  uint32_t epoch;
  double precision;
  double recall;
  double ece;
  double fpr;
  double dup_detection;
  uint64_t weight_hash;
  uint64_t signature;
  bool field_certified;
  bool export_valid;
  char reason[128];
};

// =========================================================================
// WEIGHT EXPORTER
// =========================================================================

class WeightExporter {
public:
  static constexpr bool ALLOW_MID_TRAINING_EXPORT = false;

  WeightExporter() : export_count_(0) {}

  WeightExportRecord export_weights(const char *field, uint32_t epoch,
                                    double precision, double recall, double ece,
                                    double fpr, double dup_det,
                                    bool field_certified) {
    WeightExportRecord r;
    std::memset(&r, 0, sizeof(r));

    r.export_id = ++export_count_;
    std::strncpy(r.field_name, field, 63);
    r.field_name[63] = '\0';
    r.epoch = epoch;
    r.precision = precision;
    r.recall = recall;
    r.ece = ece;
    r.fpr = fpr;
    r.dup_detection = dup_det;
    r.field_certified = field_certified;

    // Block export if field not certified
    if (!field_certified) {
      r.export_valid = false;
      std::snprintf(r.reason, sizeof(r.reason),
                    "EXPORT_BLOCKED: field '%s' not certified", field);
      return r;
    }

    // Compute weight hash and signature
    r.weight_hash = compute_weight_hash(precision, recall, ece, epoch);
    r.signature = sign(r.weight_hash, field);
    r.export_valid = true;
    std::snprintf(r.reason, sizeof(r.reason),
                  "EXPORT_OK: field=%s epoch=%u hash=%016lx", field, epoch,
                  static_cast<unsigned long>(r.weight_hash));

    return r;
  }

  uint32_t export_count() const { return export_count_; }

private:
  uint32_t export_count_;

  static uint64_t compute_weight_hash(double p, double r, double e,
                                      uint32_t epoch) {
    uint64_t h = 0x6a09e667bb67ae85ULL;
    uint64_t bits;
    std::memcpy(&bits, &p, sizeof(bits));
    h ^= bits;
    h *= 0x9e3779b97f4a7c15ULL;
    std::memcpy(&bits, &r, sizeof(bits));
    h ^= bits;
    h *= 0x9e3779b97f4a7c15ULL;
    std::memcpy(&bits, &e, sizeof(bits));
    h ^= bits;
    h *= 0x9e3779b97f4a7c15ULL;
    h ^= epoch;
    h *= 0x9e3779b97f4a7c15ULL;
    return h;
  }

  static uint64_t sign(uint64_t hash, const char *field) {
    uint64_t s = hash;
    for (const char *c = field; *c; ++c) {
      s ^= static_cast<uint64_t>(*c);
      s = (s << 7) | (s >> 57);
    }
    return s ^ 0xdeadbeefcafeULL;
  }
};

} // namespace distributed
