/**
 * Log Integrity Monitor — Rolling Hash Chain & Tamper Detection
 *
 * Monitors:
 *   1) Rolling FNV-1a hash chain over log entries
 *   2) Tamper detection: re-hashes and compares to stored chain
 *   3) Gap detection: checks for missing sequence numbers
 *   4) Corruption flag if chain breaks
 *
 * Every log entry is chained. Silent modification = instant detection.
 * No authority granted. Read-only integrity verification only.
 */

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <ctime>
#include <string>
#include <vector>

// ============================================================================
// Log Entry
// ============================================================================

struct LogEntry {
  uint64_t sequence;
  double timestamp;
  char source[64];
  char message[512];
  uint8_t chain_hash[32]; // Hash chained with previous entry
};

// ============================================================================
// Log Integrity Stats
// ============================================================================

struct LogIntegrityStats {
  int total_entries;
  int verified_entries;
  int failed_entries;
  int gap_count;       // Missing sequence numbers
  bool chain_valid;    // Entire chain verified OK
  bool has_gaps;       // Any sequence gaps
  bool has_corruption; // Any hash mismatches
  double log_score;    // 0–100 integrity score
};

// ============================================================================
// Log Integrity Monitor
// ============================================================================

class LogIntegrityMonitor {
private:
  std::vector<LogEntry> entries_;
  uint64_t expected_sequence_;
  uint8_t current_chain_hash_[32];
  int gap_count_;
  int corruption_count_;

  // -------------------------------------------------------------------

  static void compute_fnv1a(const uint8_t *data, int len, uint8_t *out32) {
    // FNV-1a for first 4 bytes, then extend to 32 bytes
    uint32_t hash = 0x811c9dc5;
    for (int i = 0; i < len; i++) {
      hash ^= data[i];
      hash *= 0x01000193;
    }

    // Extend 4-byte hash to 32 bytes via mixing
    for (int i = 0; i < 8; i++) {
      uint32_t word = hash;
      word ^= (word >> 3) ^ (word << 7);
      word *= 0x01000193;
      word += static_cast<uint32_t>(i * 0x9e3779b9);
      std::memcpy(out32 + i * 4, &word, 4);
      hash = word;
    }
  }

  void compute_entry_hash(const LogEntry &entry, const uint8_t *prev_hash,
                          uint8_t *out32) const {
    // Hash: sequence + timestamp + source + message + prev_hash
    uint8_t buffer[1024];
    std::memset(buffer, 0, sizeof(buffer));
    int offset = 0;

    std::memcpy(buffer + offset, &entry.sequence, 8);
    offset += 8;
    std::memcpy(buffer + offset, &entry.timestamp, 8);
    offset += 8;
    std::memcpy(buffer + offset, entry.source, 64);
    offset += 64;
    std::memcpy(buffer + offset, entry.message, 512);
    offset += 512;
    std::memcpy(buffer + offset, prev_hash, 32);
    offset += 32;

    compute_fnv1a(buffer, offset, out32);
  }

public:
  LogIntegrityMonitor()
      : expected_sequence_(0), gap_count_(0), corruption_count_(0) {
    std::memset(current_chain_hash_, 0, 32);
  }

  // -------------------------------------------------------------------
  // Append a log entry and chain its hash
  // -------------------------------------------------------------------

  void append_entry(const char *source, const char *message) {
    LogEntry entry;
    entry.sequence = expected_sequence_;
    entry.timestamp = static_cast<double>(std::time(nullptr));
    std::strncpy(entry.source, source, 63);
    entry.source[63] = '\0';
    std::strncpy(entry.message, message, 511);
    entry.message[511] = '\0';

    // Chain hash
    compute_entry_hash(entry, current_chain_hash_, entry.chain_hash);
    std::memcpy(current_chain_hash_, entry.chain_hash, 32);

    entries_.push_back(entry);
    expected_sequence_++;
  }

  // -------------------------------------------------------------------
  // Record an external log entry (to verify sequence and integrity)
  // -------------------------------------------------------------------

  void record_external_entry(uint64_t sequence, double timestamp,
                             const char *source, const char *message) {
    // Gap detection
    if (sequence != expected_sequence_) {
      if (sequence > expected_sequence_) {
        gap_count_ += static_cast<int>(sequence - expected_sequence_);
      }
      expected_sequence_ = sequence;
    }

    LogEntry entry;
    entry.sequence = sequence;
    entry.timestamp = timestamp;
    std::strncpy(entry.source, source, 63);
    entry.source[63] = '\0';
    std::strncpy(entry.message, message, 511);
    entry.message[511] = '\0';

    // Chain hash
    compute_entry_hash(entry, current_chain_hash_, entry.chain_hash);
    std::memcpy(current_chain_hash_, entry.chain_hash, 32);

    entries_.push_back(entry);
    expected_sequence_ = sequence + 1;
  }

  // -------------------------------------------------------------------
  // Verify entire chain integrity
  // -------------------------------------------------------------------

  bool verify_chain() {
    if (entries_.empty())
      return true;

    corruption_count_ = 0;
    uint8_t prev_hash[32];
    std::memset(prev_hash, 0, 32);

    for (size_t i = 0; i < entries_.size(); i++) {
      uint8_t expected_hash[32];
      compute_entry_hash(entries_[i], prev_hash, expected_hash);

      if (std::memcmp(expected_hash, entries_[i].chain_hash, 32) != 0) {
        corruption_count_++;
      }

      std::memcpy(prev_hash, entries_[i].chain_hash, 32);
    }

    return (corruption_count_ == 0);
  }

  // -------------------------------------------------------------------
  // Stats & Score
  // -------------------------------------------------------------------

  LogIntegrityStats get_stats() {
    LogIntegrityStats stats;
    stats.total_entries = static_cast<int>(entries_.size());
    stats.gap_count = gap_count_;
    stats.has_gaps = (gap_count_ > 0);

    // Verify chain
    stats.chain_valid = verify_chain();
    stats.has_corruption = (corruption_count_ > 0);
    stats.failed_entries = corruption_count_;
    stats.verified_entries = stats.total_entries - stats.failed_entries;

    // Score computation
    double score = 100.0;

    // Gap penalty: -5 per gap, up to 40 points
    if (gap_count_ > 0) {
      score -= std::min(40.0, gap_count_ * 5.0);
    }

    // Corruption penalty: -20 per corruption, up to 60 points
    if (corruption_count_ > 0) {
      score -= std::min(60.0, corruption_count_ * 20.0);
    }

    stats.log_score = std::max(0.0, std::min(100.0, score));
    return stats;
  }

  // -------------------------------------------------------------------
  // Accessors
  // -------------------------------------------------------------------

  int entry_count() const { return static_cast<int>(entries_.size()); }
  uint64_t expected_sequence() const { return expected_sequence_; }
  int gap_count() const { return gap_count_; }

  const uint8_t *current_chain_hash() const { return current_chain_hash_; }

  void reset() {
    entries_.clear();
    expected_sequence_ = 0;
    gap_count_ = 0;
    corruption_count_ = 0;
    std::memset(current_chain_hash_, 0, 32);
  }
};
