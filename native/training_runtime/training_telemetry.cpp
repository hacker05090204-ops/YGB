/**
 * training_telemetry.cpp — Authoritative Training Runtime Telemetry
 *
 * Rules:
 *   - Single source of truth for all training metrics
 *   - Atomic persist to reports/runtime_state.json via tmp+rename
 *   - No frontend ever computes values — all originate here
 *   - Determinism flag enforced: training halts if false
 *   - Freeze status tracked: frozen model integrity
 *
 * Exposed fields:
 *   total_epochs, completed_epochs, current_loss,
 *   precision, ece, drift_kl, duplicate_rate,
 *   gpu_util, cpu_util, temperature,
 *   determinism_status, freeze_status
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>

namespace training_runtime {

static constexpr uint32_t MAX_LOSS_HISTORY = 100;

enum class TrainingMode : uint8_t {
  IDLE = 0,
  MODE_A = 1, // Supervised lab training
  MODE_B = 2, // Shadow inference (no live action)
  MODE_C = 3  // Certified hunt
};

struct TelemetryState {
  // Epoch tracking
  uint32_t total_epochs;
  uint32_t completed_epochs;

  // Loss metrics
  double current_loss;
  double best_loss;

  // Quality metrics
  double precision;
  double ece;
  double drift_kl;
  double duplicate_rate;

  // Hardware
  double gpu_util;
  double cpu_util;
  double temperature;

  // Status flags
  bool determinism_status; // MUST be true for training
  bool freeze_status;      // true = frozen model is valid
  TrainingMode mode;

  // Timestamps
  uint64_t last_update_ms;
  uint64_t training_start_ms;

  // Error tracking
  uint32_t total_errors;
  char last_error[256];
};

class TrainingTelemetry {
public:
  TrainingTelemetry() {
    std::memset(&state_, 0, sizeof(state_));
    std::memset(loss_history_, 0, sizeof(loss_history_));
    state_.determinism_status = true;
    state_.freeze_status = true;
    state_.best_loss = 1e9;
    state_.mode = TrainingMode::IDLE;
    loss_head_ = 0;
    loss_count_ = 0;
  }

  // ---- Configuration ----
  void configure(uint32_t total_epochs, TrainingMode mode) {
    state_.total_epochs = total_epochs;
    state_.mode = mode;
    state_.completed_epochs = 0;
    state_.current_loss = 0.0;
    state_.best_loss = 1e9;
    state_.total_errors = 0;
    state_.last_error[0] = '\0';
  }

  // ---- Record epoch completion ----
  void record_epoch(double loss, double precision, double ece, double drift_kl,
                    double dup_rate) {
    state_.completed_epochs++;
    state_.current_loss = loss;
    state_.precision = precision;
    state_.ece = ece;
    state_.drift_kl = drift_kl;
    state_.duplicate_rate = dup_rate;

    // Track best loss
    if (loss < state_.best_loss) {
      state_.best_loss = loss;
    }

    // Record in rolling history
    loss_history_[loss_head_] = loss;
    loss_head_ = (loss_head_ + 1) % MAX_LOSS_HISTORY;
    if (loss_count_ < MAX_LOSS_HISTORY)
      loss_count_++;
  }

  // ---- Update hardware metrics ----
  void update_hardware(double gpu_util, double cpu_util, double temp) {
    state_.gpu_util = gpu_util;
    state_.cpu_util = cpu_util;
    state_.temperature = temp;
  }

  // ---- Update status flags ----
  void set_determinism(bool status) { state_.determinism_status = status; }

  void set_freeze_status(bool valid) { state_.freeze_status = valid; }

  // ---- Update timestamp ----
  void update_timestamp(uint64_t ms) { state_.last_update_ms = ms; }

  void set_training_start(uint64_t ms) { state_.training_start_ms = ms; }

  // ---- Error tracking ----
  void record_error(const char *error) {
    state_.total_errors++;
    std::strncpy(state_.last_error, error, sizeof(state_.last_error) - 1);
    state_.last_error[sizeof(state_.last_error) - 1] = '\0';
  }

  // ---- Compute training progress ----
  double progress_pct() const {
    if (state_.total_epochs == 0)
      return 0.0;
    return (static_cast<double>(state_.completed_epochs) /
            state_.total_epochs) *
           100.0;
  }

  // ---- Compute loss trend (negative = improving) ----
  double loss_trend() const {
    if (loss_count_ < 2)
      return 0.0;
    uint32_t latest = (loss_head_ + MAX_LOSS_HISTORY - 1) % MAX_LOSS_HISTORY;
    uint32_t prev = (loss_head_ + MAX_LOSS_HISTORY - 2) % MAX_LOSS_HISTORY;
    return loss_history_[latest] - loss_history_[prev];
  }

  // ---- Serialize to JSON string ----
  // Returns number of chars written, or 0 on failure
  int to_json(char *buf, size_t buf_size) const {
    return std::snprintf(
        buf, buf_size,
        "{\n"
        "  \"total_epochs\": %u,\n"
        "  \"completed_epochs\": %u,\n"
        "  \"current_loss\": %.6f,\n"
        "  \"best_loss\": %.6f,\n"
        "  \"precision\": %.6f,\n"
        "  \"ece\": %.6f,\n"
        "  \"drift_kl\": %.6f,\n"
        "  \"duplicate_rate\": %.6f,\n"
        "  \"gpu_util\": %.2f,\n"
        "  \"cpu_util\": %.2f,\n"
        "  \"temperature\": %.1f,\n"
        "  \"determinism_status\": %s,\n"
        "  \"freeze_status\": %s,\n"
        "  \"mode\": \"%s\",\n"
        "  \"progress_pct\": %.2f,\n"
        "  \"loss_trend\": %.6f,\n"
        "  \"last_update_ms\": %llu,\n"
        "  \"training_start_ms\": %llu,\n"
        "  \"total_errors\": %u\n"
        "}",
        state_.total_epochs, state_.completed_epochs, state_.current_loss,
        state_.best_loss, state_.precision, state_.ece, state_.drift_kl,
        state_.duplicate_rate, state_.gpu_util, state_.cpu_util,
        state_.temperature, state_.determinism_status ? "true" : "false",
        state_.freeze_status ? "true" : "false", mode_str(state_.mode),
        progress_pct(), loss_trend(), (unsigned long long)state_.last_update_ms,
        (unsigned long long)state_.training_start_ms, state_.total_errors);
  }

  // ---- Persist to file atomically (write tmp, then rename) ----
  bool persist(const char *path) const {
    char json_buf[2048];
    int len = to_json(json_buf, sizeof(json_buf));
    if (len <= 0 || len >= (int)sizeof(json_buf))
      return false;

    // Write to tmp file
    char tmp_path[512];
    std::snprintf(tmp_path, sizeof(tmp_path), "%s.tmp", path);

    FILE *f = std::fopen(tmp_path, "w");
    if (!f)
      return false;

    std::fwrite(json_buf, 1, len, f);
    std::fclose(f);

    // Atomic rename
    std::remove(path);
    return std::rename(tmp_path, path) == 0;
  }

  const TelemetryState &state() const { return state_; }

  // ---- Self-test ----
  static bool run_tests() {
    TrainingTelemetry tel;
    int failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (!cond) {
        std::printf("  FAIL: %s\n", name);
        failed++;
      }
    };

    // Test: Initial state
    test(tel.state().mode == TrainingMode::IDLE, "initial mode = IDLE");
    test(tel.state().determinism_status == true, "determinism initially true");
    test(tel.state().freeze_status == true, "freeze initially valid");
    test(tel.progress_pct() == 0.0, "initial progress = 0");

    // Test: Configure training
    tel.configure(100, TrainingMode::MODE_A);
    test(tel.state().total_epochs == 100, "total epochs set");
    test(tel.state().mode == TrainingMode::MODE_A, "mode A set");

    // Test: Record epochs
    tel.record_epoch(0.50, 0.85, 0.020, 0.05, 0.02);
    test(tel.state().completed_epochs == 1, "1 epoch completed");
    test(tel.state().current_loss == 0.50, "loss recorded");
    test(tel.state().precision == 0.85, "precision recorded");
    test(tel.progress_pct() == 1.0, "1% progress");

    tel.record_epoch(0.40, 0.90, 0.015, 0.03, 0.01);
    test(tel.state().completed_epochs == 2, "2 epochs completed");
    test(tel.state().best_loss == 0.40, "best loss updated");
    test(tel.loss_trend() < 0.0, "loss trending down");

    // Test: Hardware metrics
    tel.update_hardware(85.5, 60.0, 72.3);
    test(tel.state().gpu_util == 85.5, "GPU util recorded");
    test(tel.state().cpu_util == 60.0, "CPU util recorded");
    test(tel.state().temperature == 72.3, "temp recorded");

    // Test: Determinism flag
    tel.set_determinism(false);
    test(tel.state().determinism_status == false, "determinism set to false");

    // Test: Freeze status
    tel.set_freeze_status(false);
    test(tel.state().freeze_status == false, "freeze invalid");

    // Test: Error tracking
    tel.record_error("OOM on GPU 0");
    test(tel.state().total_errors == 1, "error count");

    // Test: JSON serialization
    char buf[2048];
    int len = tel.to_json(buf, sizeof(buf));
    test(len > 0, "JSON serialized");
    test(len < (int)sizeof(buf), "JSON fits in buffer");

    // Verify JSON contains key fields
    test(std::strstr(buf, "\"total_epochs\": 100") != nullptr,
         "JSON has epochs");
    test(std::strstr(buf, "\"determinism_status\": false") != nullptr,
         "JSON has determinism");
    test(std::strstr(buf, "\"mode\": \"MODE_A\"") != nullptr, "JSON has mode");

    // Test: Timestamp
    tel.update_timestamp(1234567890);
    test(tel.state().last_update_ms == 1234567890, "timestamp set");

    return failed == 0;
  }

private:
  static const char *mode_str(TrainingMode m) {
    switch (m) {
    case TrainingMode::IDLE:
      return "IDLE";
    case TrainingMode::MODE_A:
      return "MODE_A";
    case TrainingMode::MODE_B:
      return "MODE_B";
    case TrainingMode::MODE_C:
      return "MODE_C";
    default:
      return "UNKNOWN";
    }
  }

  TelemetryState state_;
  double loss_history_[MAX_LOSS_HISTORY];
  uint32_t loss_head_;
  uint32_t loss_count_;
};

} // namespace training_runtime
