/**
 * gpu_stability_monitor.cpp — Long-Run GPU Memory & Stability Monitor
 *
 * Rules:
 *   - Track GPU memory usage per batch
 *   - If >85% sustained for SUSTAINED_THRESHOLD batches → soft-restart
 *   - Call cache-clear every CACHE_CLEAR_INTERVAL batches
 *   - Weekly scheduled controlled restart after RESTART_INTERVAL_HOURS
 *   - Log every restart reason immutably
 *   - No silent OOM — always save checkpoint before restart
 *
 * NO auto-submit.
 * NO authority unlock.
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace gpu_stability {

// ---------- Configuration ----------
static constexpr double MEMORY_THRESHOLD_PERCENT = 85.0;
static constexpr uint32_t SUSTAINED_THRESHOLD = 50;   // batches above threshold
static constexpr uint32_t CACHE_CLEAR_INTERVAL = 100; // batches between clears
static constexpr uint64_t RESTART_INTERVAL_HOURS = 168; // 7 days
static constexpr uint32_t MAX_RESTART_LOG = 64;

// ---------- Enums ----------
enum class RestartReason : uint8_t {
  NONE = 0,
  MEMORY_PRESSURE = 1,
  SCHEDULED_WEEKLY = 2,
  MANUAL = 3,
  OOM_PREVENTION = 4,
};

enum class Action : uint8_t {
  CONTINUE = 0,
  CLEAR_CACHE = 1,
  SOFT_RESTART = 2,
  SAVE_CHECKPOINT = 3,
};

// ---------- Structs ----------
struct GPUSnapshot {
  double memory_used_mb;
  double memory_total_mb;
  double utilization_percent;
  uint64_t timestamp_ms;
  uint32_t batch_number;
};

struct RestartEntry {
  RestartReason reason;
  uint64_t timestamp_ms;
  uint32_t batch_number;
  double memory_percent;
  char detail[256];
};

struct StabilityState {
  uint32_t total_batches;
  uint32_t batches_above_threshold;
  uint32_t cache_clears;
  uint32_t soft_restarts;
  uint32_t checkpoints_saved;
  bool checkpoint_needed;
  bool restart_needed;
  RestartReason pending_reason;
  double current_memory_percent;
  double peak_memory_percent;
  uint64_t start_time_ms;
  uint64_t last_cache_clear_batch;
  RestartEntry restart_log[MAX_RESTART_LOG];
  uint32_t restart_log_count;
  char last_action[128];
};

// ---------- Monitor ----------
class GPUStabilityMonitor {
public:
  GPUStabilityMonitor() {
    std::memset(&state_, 0, sizeof(state_));
    state_.pending_reason = RestartReason::NONE;
  }

  void set_start_time(uint64_t start_ms) { state_.start_time_ms = start_ms; }

  // ---- Record a GPU snapshot and determine action ----
  Action record(const GPUSnapshot &snap) {
    state_.total_batches = snap.batch_number;

    // Compute memory percentage
    double mem_pct = 0.0;
    if (snap.memory_total_mb > 0) {
      mem_pct = (snap.memory_used_mb / snap.memory_total_mb) * 100.0;
    }
    state_.current_memory_percent = mem_pct;
    if (mem_pct > state_.peak_memory_percent) {
      state_.peak_memory_percent = mem_pct;
    }

    // 1. Check sustained memory pressure
    if (mem_pct > MEMORY_THRESHOLD_PERCENT) {
      state_.batches_above_threshold++;
    } else {
      state_.batches_above_threshold = 0;
    }

    // 2. Check weekly restart
    if (state_.start_time_ms > 0 && snap.timestamp_ms > 0) {
      uint64_t elapsed_hours =
          (snap.timestamp_ms - state_.start_time_ms) / (3600ULL * 1000ULL);
      if (elapsed_hours >= RESTART_INTERVAL_HOURS) {
        state_.restart_needed = true;
        state_.checkpoint_needed = true;
        state_.pending_reason = RestartReason::SCHEDULED_WEEKLY;
        log_restart(RestartReason::SCHEDULED_WEEKLY, snap.timestamp_ms,
                    snap.batch_number, mem_pct,
                    "SCHEDULED_WEEKLY: 7-day restart interval reached");
        std::snprintf(state_.last_action, sizeof(state_.last_action),
                      "SAVE_CHECKPOINT: weekly restart at batch %u",
                      snap.batch_number);
        return Action::SAVE_CHECKPOINT;
      }
    }

    // 3. Sustained memory pressure → soft restart
    if (state_.batches_above_threshold >= SUSTAINED_THRESHOLD) {
      state_.restart_needed = true;
      state_.checkpoint_needed = true;
      state_.pending_reason = RestartReason::MEMORY_PRESSURE;
      log_restart(RestartReason::MEMORY_PRESSURE, snap.timestamp_ms,
                  snap.batch_number, mem_pct,
                  "MEMORY_PRESSURE: >85% for 50+ batches");
      std::snprintf(state_.last_action, sizeof(state_.last_action),
                    "SOFT_RESTART: memory=%.1f%% at batch %u", mem_pct,
                    snap.batch_number);
      state_.batches_above_threshold = 0;
      state_.soft_restarts++;
      return Action::SOFT_RESTART;
    }

    // 4. Periodic cache clear
    if (snap.batch_number > 0 &&
        (snap.batch_number - state_.last_cache_clear_batch) >=
            CACHE_CLEAR_INTERVAL) {
      state_.last_cache_clear_batch = snap.batch_number;
      state_.cache_clears++;
      std::snprintf(state_.last_action, sizeof(state_.last_action),
                    "CLEAR_CACHE: batch %u (interval=%u)", snap.batch_number,
                    CACHE_CLEAR_INTERVAL);
      return Action::CLEAR_CACHE;
    }

    std::snprintf(state_.last_action, sizeof(state_.last_action),
                  "CONTINUE: batch %u mem=%.1f%%", snap.batch_number, mem_pct);
    return Action::CONTINUE;
  }

  const StabilityState &state() const { return state_; }

  void reset() {
    std::memset(&state_, 0, sizeof(state_));
    state_.pending_reason = RestartReason::NONE;
  }

  // ---- Self-test ----
  static bool run_tests() {
    GPUStabilityMonitor mon;
    int failed = 0;

    auto test = [&](bool cond, const char *name) {
      if (!cond) {
        std::printf("  FAIL: %s\n", name);
        failed++;
      }
    };

    // Test 1: Normal operation — no restart
    GPUSnapshot snap = {6000.0, 10000.0, 70.0, 1000, 1};
    Action act = mon.record(snap);
    test(act == Action::CONTINUE, "normal mem → CONTINUE");
    test(mon.state().batches_above_threshold == 0, "no threshold batches");

    // Test 2: High memory but not sustained
    mon.reset();
    for (uint32_t i = 1; i <= 10; i++) {
      GPUSnapshot h = {9000.0, 10000.0, 95.0, 1000 + i, i};
      mon.record(h);
    }
    test(mon.state().batches_above_threshold == 10, "10 batches above");
    test(mon.state().soft_restarts == 0, "no restart yet (under 50)");

    // Test 3: Sustained memory → soft restart
    mon.reset();
    Action last = Action::CONTINUE;
    for (uint32_t i = 1; i <= 55; i++) {
      GPUSnapshot h = {9000.0, 10000.0, 95.0, 1000 + i, i};
      last = mon.record(h);
    }
    test(last == Action::SOFT_RESTART, "sustained 50+ → SOFT_RESTART");
    test(mon.state().soft_restarts == 1, "one restart logged");
    test(mon.state().restart_log_count == 1, "restart log has entry");

    // Test 4: Cache clear at interval
    mon.reset();
    snap = {5000.0, 10000.0, 50.0, 2000, CACHE_CLEAR_INTERVAL};
    act = mon.record(snap);
    test(act == Action::CLEAR_CACHE, "cache clear at interval");
    test(mon.state().cache_clears == 1, "one cache clear");

    // Test 5: Weekly restart
    mon.reset();
    mon.set_start_time(0);
    GPUSnapshot weekly = {5000.0, 10000.0, 50.0,
                          RESTART_INTERVAL_HOURS * 3600ULL * 1000ULL +
                              1, // past 7 days
                          500};
    act = mon.record(weekly);
    test(act == Action::SAVE_CHECKPOINT, "weekly → SAVE_CHECKPOINT");
    test(mon.state().restart_needed == true, "restart flag set");
    test(mon.state().pending_reason == RestartReason::SCHEDULED_WEEKLY,
         "reason is SCHEDULED_WEEKLY");

    // Test 6: Peak memory tracking
    mon.reset();
    GPUSnapshot low = {2000.0, 10000.0, 20.0, 100, 1};
    GPUSnapshot high = {9500.0, 10000.0, 95.0, 200, 2};
    GPUSnapshot mid = {5000.0, 10000.0, 50.0, 300, 3};
    mon.record(low);
    mon.record(high);
    mon.record(mid);
    test(mon.state().peak_memory_percent > 94.0, "peak tracks highest");

    // Test 7: Memory below threshold resets counter
    mon.reset();
    for (uint32_t i = 1; i <= 30; i++) {
      GPUSnapshot h = {9000.0, 10000.0, 95.0, 1000 + i, i};
      mon.record(h);
    }
    test(mon.state().batches_above_threshold == 30, "30 above");
    // Now drop below
    GPUSnapshot ok = {5000.0, 10000.0, 50.0, 2000, 31};
    mon.record(ok);
    test(mon.state().batches_above_threshold == 0,
         "reset after below threshold");

    return failed == 0;
  }

private:
  void log_restart(RestartReason reason, uint64_t ts, uint32_t batch,
                   double mem_pct, const char *detail) {
    if (state_.restart_log_count < MAX_RESTART_LOG) {
      RestartEntry &e = state_.restart_log[state_.restart_log_count++];
      e.reason = reason;
      e.timestamp_ms = ts;
      e.batch_number = batch;
      e.memory_percent = mem_pct;
      std::strncpy(e.detail, detail, sizeof(e.detail) - 1);
      e.detail[sizeof(e.detail) - 1] = '\0';
    }
  }

  StabilityState state_;
};

} // namespace gpu_stability
