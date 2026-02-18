/**
 * stress_simulator.cpp — Synthetic Stress Injection for Lab Training
 *
 * Generates synthetic perturbations to test system resilience:
 *   - Drift injection (KL divergence spikes)
 *   - Duplicate flooding
 *   - Thermal simulation
 *   - IO latency injection
 *   - Confidence inflation attack
 *
 * ALL data is synthetic. NO real external access.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


namespace lab_training {

// =========================================================================
// STRESS TYPES
// =========================================================================

enum class StressType : uint8_t {
  DRIFT_SPIKE = 0,
  DUPLICATE_FLOOD = 1,
  THERMAL_RAMP = 2,
  IO_LATENCY = 3,
  CONFIDENCE_INFLATION = 4,
  SCOPE_MUTATION = 5
};

static const char *stress_type_name(StressType t) {
  switch (t) {
  case StressType::DRIFT_SPIKE:
    return "DRIFT_SPIKE";
  case StressType::DUPLICATE_FLOOD:
    return "DUPLICATE_FLOOD";
  case StressType::THERMAL_RAMP:
    return "THERMAL_RAMP";
  case StressType::IO_LATENCY:
    return "IO_LATENCY";
  case StressType::CONFIDENCE_INFLATION:
    return "CONFIDENCE_INFLATION";
  case StressType::SCOPE_MUTATION:
    return "SCOPE_MUTATION";
  default:
    return "UNKNOWN";
  }
}

// =========================================================================
// STRESS RESULT
// =========================================================================

struct StressResult {
  StressType type;
  double intensity;       // 0.0 – 1.0
  double system_response; // measured degradation
  bool contained;         // did system auto-contain?
  bool recovered;         // did system recover?
  uint32_t samples_injected;
  char summary[256];
};

// =========================================================================
// STRESS SIMULATOR
// =========================================================================

class StressSimulator {
public:
  static constexpr bool ALLOW_EXTERNAL_ACCESS = false;

  // --- Inject synthetic drift spike ---
  StressResult inject_drift(double intensity, uint32_t seed) {
    StressResult r;
    std::memset(&r, 0, sizeof(r));
    r.type = StressType::DRIFT_SPIKE;
    r.intensity = clamp01(intensity);
    r.samples_injected = static_cast<uint32_t>(100 * r.intensity);

    // Simulate: system should contain if KL > threshold
    double kl = 0.2 + r.intensity * 0.5;
    r.system_response = kl;
    r.contained = (kl > 0.45);
    r.recovered = r.contained;

    std::snprintf(r.summary, sizeof(r.summary), "Drift spike KL=%.3f, %s", kl,
                  r.contained ? "CONTAINED" : "WITHIN_TOLERANCE");
    return r;
  }

  // --- Inject duplicate flood ---
  StressResult inject_duplicates(double rate, uint32_t count) {
    StressResult r;
    std::memset(&r, 0, sizeof(r));
    r.type = StressType::DUPLICATE_FLOOD;
    r.intensity = clamp01(rate);
    r.samples_injected = count;

    // Simulate: system should suppress high dup rates
    r.system_response = rate;
    r.contained = (rate > 0.20);
    r.recovered = true;

    std::snprintf(r.summary, sizeof(r.summary),
                  "Dup flood rate=%.2f, %u samples, %s", rate, count,
                  r.contained ? "SUPPRESSED" : "BELOW_THRESHOLD");
    return r;
  }

  // --- Inject thermal ramp ---
  StressResult inject_thermal(double peak_temp_c) {
    StressResult r;
    std::memset(&r, 0, sizeof(r));
    r.type = StressType::THERMAL_RAMP;
    r.intensity = peak_temp_c / 100.0;
    r.samples_injected = 1;

    r.system_response = peak_temp_c;
    r.contained = (peak_temp_c > 83.0);
    r.recovered = r.contained;

    std::snprintf(r.summary, sizeof(r.summary), "Thermal ramp peak=%.1fC, %s",
                  peak_temp_c, r.contained ? "AUTO_PAUSED" : "WITHIN_LIMIT");
    return r;
  }

  // --- Inject confidence inflation ---
  StressResult inject_confidence_inflation(double inflation_factor) {
    StressResult r;
    std::memset(&r, 0, sizeof(r));
    r.type = StressType::CONFIDENCE_INFLATION;
    r.intensity = clamp01(inflation_factor);
    r.samples_injected = 50;

    r.system_response = inflation_factor;
    r.contained = (inflation_factor > 0.15);
    r.recovered = r.contained;

    std::snprintf(r.summary, sizeof(r.summary), "Confidence inflation=%.2f, %s",
                  inflation_factor,
                  r.contained ? "DEFLATED_TO_BASELINE" : "WITHIN_BAND");
    return r;
  }

private:
  static double clamp01(double v) {
    if (v < 0.0)
      return 0.0;
    if (v > 1.0)
      return 1.0;
    return v;
  }
};

} // namespace lab_training
