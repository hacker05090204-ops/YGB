/**
 * state_persistence.cpp — Runtime State Persistence
 *
 * Persists and restores runtime monitor state:
 * - Rolling precision window baseline
 * - KL baseline (EMA)
 * - Entropy baseline
 * - Duplicate cluster baseline
 *
 * Write atomically: temp → fsync → rename.
 * Load at startup; if missing → initialize baseline mode.
 *
 * NO mock data. NO fabricated metrics.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>


#ifdef _WIN32
#include <io.h>
#define fsync_fd(fd) _commit(fd)
#else
#include <unistd.h>
#define fsync_fd(fd) fsync(fd)
#endif

namespace runtime_monitor {

static constexpr int STATE_VERSION = 1;
static constexpr char STATE_PATH[] = "reports/runtime_state.json";
static constexpr char STATE_TMP_PATH[] = "reports/runtime_state.json.tmp";

struct PersistedState {
  int version;

  // Precision monitor baselines
  double rolling_precision;
  uint32_t precision_window_size;
  uint32_t true_positives;
  uint32_t false_positives;
  uint32_t true_negatives;
  uint32_t false_negatives;

  // Drift monitor baselines
  double kl_baseline_ema;
  double entropy_baseline;
  double confidence_baseline;
  double duplicate_cluster_baseline;

  // Adaptive state
  double confidence_threshold_adj;
  double abstention_band_adj;

  // Validity flag
  bool valid;
};

// --- Write integer field ---
static void write_field(FILE *f, const char *key, int val, bool comma) {
  std::fprintf(f, "  \"%s\": %d%s\n", key, val, comma ? "," : "");
}

// --- Write double field ---
static void write_double(FILE *f, const char *key, double val, bool comma) {
  std::fprintf(f, "  \"%s\": %.8f%s\n", key, val, comma ? "," : "");
}

// --- Save state atomically ---
static bool save_state(const PersistedState &state) {
  FILE *f = std::fopen(STATE_TMP_PATH, "w");
  if (!f)
    return false;

  std::fprintf(f, "{\n");
  write_field(f, "version", state.version, true);
  write_double(f, "rolling_precision", state.rolling_precision, true);
  write_field(f, "precision_window_size", state.precision_window_size, true);
  write_field(f, "true_positives", state.true_positives, true);
  write_field(f, "false_positives", state.false_positives, true);
  write_field(f, "true_negatives", state.true_negatives, true);
  write_field(f, "false_negatives", state.false_negatives, true);
  write_double(f, "kl_baseline_ema", state.kl_baseline_ema, true);
  write_double(f, "entropy_baseline", state.entropy_baseline, true);
  write_double(f, "confidence_baseline", state.confidence_baseline, true);
  write_double(f, "duplicate_cluster_baseline",
               state.duplicate_cluster_baseline, true);
  write_double(f, "confidence_threshold_adj", state.confidence_threshold_adj,
               true);
  write_double(f, "abstention_band_adj", state.abstention_band_adj, false);
  std::fprintf(f, "}\n");

  // Flush + fsync
  std::fflush(f);
  int fd = fileno(f);
  if (fd >= 0) {
    fsync_fd(fd);
  }
  std::fclose(f);

  // Atomic rename
  std::remove(STATE_PATH);
  if (std::rename(STATE_TMP_PATH, STATE_PATH) != 0) {
    return false;
  }

  return true;
}

// --- Simple JSON double parser (no external deps) ---
static double parse_double_after(const char *buf, const char *key) {
  const char *pos = std::strstr(buf, key);
  if (!pos)
    return 0.0;
  // Skip past key and colon
  pos += std::strlen(key);
  while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
    ++pos;
  double val = 0.0;
  std::sscanf(pos, "%lf", &val);
  return val;
}

// --- Simple JSON int parser ---
static int parse_int_after(const char *buf, const char *key) {
  const char *pos = std::strstr(buf, key);
  if (!pos)
    return 0;
  pos += std::strlen(key);
  while (*pos && (*pos == '"' || *pos == ':' || *pos == ' '))
    ++pos;
  int val = 0;
  std::sscanf(pos, "%d", &val);
  return val;
}

// --- Load state ---
static PersistedState load_state() {
  PersistedState state;
  std::memset(&state, 0, sizeof(state));
  state.valid = false;

  FILE *f = std::fopen(STATE_PATH, "r");
  if (!f) {
    return state; // Missing file → baseline mode
  }

  // Read entire file (max 4KB)
  char buf[4096];
  std::memset(buf, 0, sizeof(buf));
  size_t n = std::fread(buf, 1, sizeof(buf) - 1, f);
  std::fclose(f);

  if (n == 0)
    return state;

  // Parse version
  state.version = parse_int_after(buf, "version");
  if (state.version != STATE_VERSION)
    return state; // Version mismatch → re-baseline

  state.rolling_precision = parse_double_after(buf, "rolling_precision");
  state.precision_window_size =
      static_cast<uint32_t>(parse_int_after(buf, "precision_window_size"));
  state.true_positives =
      static_cast<uint32_t>(parse_int_after(buf, "true_positives"));
  state.false_positives =
      static_cast<uint32_t>(parse_int_after(buf, "false_positives"));
  state.true_negatives =
      static_cast<uint32_t>(parse_int_after(buf, "true_negatives"));
  state.false_negatives =
      static_cast<uint32_t>(parse_int_after(buf, "false_negatives"));
  state.kl_baseline_ema = parse_double_after(buf, "kl_baseline_ema");
  state.entropy_baseline = parse_double_after(buf, "entropy_baseline");
  state.confidence_baseline = parse_double_after(buf, "confidence_baseline");
  state.duplicate_cluster_baseline =
      parse_double_after(buf, "duplicate_cluster_baseline");
  state.confidence_threshold_adj =
      parse_double_after(buf, "confidence_threshold_adj");
  state.abstention_band_adj = parse_double_after(buf, "abstention_band_adj");

  state.valid = true;
  return state;
}

// --- Self-test ---
static bool run_tests() {
  int passed = 0, failed = 0;

  auto test = [&](bool cond, const char *name) {
    if (cond)
      ++passed;
    else
      ++failed;
  };

  // Test 1: Save and load round-trip
  PersistedState original;
  std::memset(&original, 0, sizeof(original));
  original.version = STATE_VERSION;
  original.rolling_precision = 0.9723;
  original.precision_window_size = 500;
  original.true_positives = 480;
  original.false_positives = 10;
  original.true_negatives = 5;
  original.false_negatives = 5;
  original.kl_baseline_ema = 0.1234;
  original.entropy_baseline = 2.15;
  original.confidence_baseline = 0.87;
  original.duplicate_cluster_baseline = 0.05;
  original.confidence_threshold_adj = 0.02;
  original.abstention_band_adj = 0.03;

  bool saved = save_state(original);
  test(saved, "Save state should succeed");

  PersistedState loaded = load_state();
  test(loaded.valid, "Loaded state should be valid");
  test(loaded.version == STATE_VERSION, "Version match");
  test(std::fabs(loaded.rolling_precision - 0.9723) < 0.001,
       "Rolling precision preserved");
  test(loaded.true_positives == 480, "TP count preserved");
  test(std::fabs(loaded.kl_baseline_ema - 0.1234) < 0.001,
       "KL baseline EMA preserved");
  test(std::fabs(loaded.entropy_baseline - 2.15) < 0.01,
       "Entropy baseline preserved");

  // Test 2: Missing file → invalid state
  std::remove(STATE_PATH);
  PersistedState missing = load_state();
  test(!missing.valid, "Missing file → invalid state");

  // Cleanup
  std::remove(STATE_PATH);
  std::remove(STATE_TMP_PATH);

  return failed == 0;
}

} // namespace runtime_monitor
