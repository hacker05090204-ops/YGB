/**
 * accuracy_tracker.cpp — Lab Accuracy Report Generator
 *
 * Generates lab_accuracy_report.json from validated lab benchmark results.
 * Tracks: precision, recall, ECE, Brier score, duplicate suppression rate.
 *
 * Atomic write: temp → fsync → rename
 *
 * NO real external data. ALL metrics from synthetic lab runs.
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

namespace lab_training {

// =========================================================================
// ACCURACY SNAPSHOT
// =========================================================================

struct AccuracySnapshot {
  double precision;
  double recall;
  double ece_score;
  double brier_score;
  double dup_suppression_rate;
  double scope_compliance;
  uint32_t epoch;
  uint32_t samples_evaluated;
};

// =========================================================================
// ACCURACY TRACKER
// =========================================================================

static constexpr char REPORT_PATH[] = "reports/lab_accuracy_report.json";
static constexpr char REPORT_TMP[] = "reports/lab_accuracy_report.json.tmp";
static constexpr uint32_t MAX_HISTORY = 100;

class AccuracyTracker {
public:
  AccuracyTracker() : count_(0) {}

  // Record a new accuracy snapshot
  void record(const AccuracySnapshot &snap) {
    if (count_ < MAX_HISTORY) {
      history_[count_] = snap;
    } else {
      // Ring buffer: overwrite oldest
      history_[count_ % MAX_HISTORY] = snap;
    }
    ++count_;
  }

  // Get latest snapshot
  const AccuracySnapshot &latest() const {
    uint32_t idx = (count_ > 0) ? ((count_ - 1) % MAX_HISTORY) : 0;
    return history_[idx];
  }

  // Write report atomically
  bool save_report() const {
    if (count_ == 0)
      return false;

    FILE *f = std::fopen(REPORT_TMP, "w");
    if (!f)
      return false;

    const AccuracySnapshot &s = latest();

    std::fprintf(f, "{\n");
    std::fprintf(f, "  \"version\": 1,\n");
    std::fprintf(f, "  \"precision\": %.6f,\n", s.precision);
    std::fprintf(f, "  \"recall\": %.6f,\n", s.recall);
    std::fprintf(f, "  \"ece_score\": %.6f,\n", s.ece_score);
    std::fprintf(f, "  \"brier_score\": %.6f,\n", s.brier_score);
    std::fprintf(f, "  \"dup_suppression_rate\": %.6f,\n",
                 s.dup_suppression_rate);
    std::fprintf(f, "  \"scope_compliance\": %.6f,\n", s.scope_compliance);
    std::fprintf(f, "  \"epoch\": %u,\n", s.epoch);
    std::fprintf(f, "  \"samples_evaluated\": %u,\n", s.samples_evaluated);
    std::fprintf(f, "  \"total_runs\": %u\n", count_);
    std::fprintf(f, "}\n");

    std::fflush(f);
    int fd = fileno(f);
    if (fd >= 0)
      fsync_fd(fd);
    std::fclose(f);

    std::remove(REPORT_PATH);
    return std::rename(REPORT_TMP, REPORT_PATH) == 0;
  }

  uint32_t count() const { return count_; }

  // Rolling average precision (last N runs)
  double rolling_precision(uint32_t n = 10) const {
    if (count_ == 0)
      return 0.0;
    uint32_t actual = (count_ < n) ? count_ : n;
    double sum = 0.0;
    for (uint32_t i = 0; i < actual; ++i) {
      uint32_t idx = (count_ - 1 - i) % MAX_HISTORY;
      sum += history_[idx].precision;
    }
    return sum / actual;
  }

private:
  AccuracySnapshot history_[MAX_HISTORY];
  uint32_t count_;
};

} // namespace lab_training
