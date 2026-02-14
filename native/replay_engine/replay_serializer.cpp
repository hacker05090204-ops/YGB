/*
 * replay_serializer.cpp — Replay Chain JSON Exporter
 *
 * Exports the full hunting replay (steps + diffs + HTTP pairs + evidence)
 * into a structured JSON format for review/playback.
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int MAX_JSON_SIZE = 4 * 1024 * 1024; // 4MB max export
static constexpr int MAX_STEPS_EXPORT = 5000;

// =========================================================================
// TYPES
// =========================================================================

enum class ReplayFormat {
  JSON,
  JSON_COMPACT,
  CHAIN_ONLY // Hashes only, no content
};

struct ReplayExportResult {
  bool success;
  int steps_exported;
  int total_bytes;
  char file_path[512];
  char error[256];
  char chain_hash[65]; // Final hash of entire chain
};

struct ReplayStepSummary {
  int sequence;
  long timestamp;
  char endpoint[256];
  char payload_preview[128];
  int http_pairs;
  int dom_diffs;
  char step_hash[65];
};

// =========================================================================
// REPLAY SERIALIZER
// =========================================================================

class ReplaySerializer {
private:
  char buffer_[MAX_JSON_SIZE];
  int buffer_pos_;

  void append(const char *str) {
    int len = (int)std::strlen(str);
    if (buffer_pos_ + len < MAX_JSON_SIZE - 1) {
      std::memcpy(buffer_ + buffer_pos_, str, len);
      buffer_pos_ += len;
    }
  }

  void append_escaped(const char *str) {
    while (*str && buffer_pos_ < MAX_JSON_SIZE - 8) {
      switch (*str) {
      case '"':
        buffer_[buffer_pos_++] = '\\';
        buffer_[buffer_pos_++] = '"';
        break;
      case '\\':
        buffer_[buffer_pos_++] = '\\';
        buffer_[buffer_pos_++] = '\\';
        break;
      case '\n':
        buffer_[buffer_pos_++] = '\\';
        buffer_[buffer_pos_++] = 'n';
        break;
      case '\r':
        buffer_[buffer_pos_++] = '\\';
        buffer_[buffer_pos_++] = 'r';
        break;
      case '\t':
        buffer_[buffer_pos_++] = '\\';
        buffer_[buffer_pos_++] = 't';
        break;
      default:
        buffer_[buffer_pos_++] = *str;
        break;
      }
      str++;
    }
  }

public:
  ReplaySerializer() : buffer_pos_(0) { std::memset(buffer_, 0, sizeof(buffer_)); }

  ReplayExportResult export_steps(const ReplayStepSummary *steps, int count,
                                  const char *target_domain,
                                  const char *session_id) {
    ReplayExportResult result;
    std::memset(&result, 0, sizeof(result));

    if (!steps || count == 0) {
      result.success = false;
      std::snprintf(result.error, sizeof(result.error), "No steps to export");
      return result;
    }

    if (count > MAX_STEPS_EXPORT)
      count = MAX_STEPS_EXPORT;

    buffer_pos_ = 0;

    // Build JSON
    append("{\"replay\":{");
    append("\"version\":\"1.0\",");

    char tmp[512];
    std::snprintf(tmp, sizeof(tmp), "\"target\":\"%s\",", target_domain);
    append(tmp);

    std::snprintf(tmp, sizeof(tmp), "\"session_id\":\"%s\",", session_id);
    append(tmp);

    std::snprintf(tmp, sizeof(tmp), "\"exported_at\":%ld,", (long)std::time(nullptr));
    append(tmp);

    std::snprintf(tmp, sizeof(tmp), "\"step_count\":%d,", count);
    append(tmp);

    append("\"steps\":[");

    for (int i = 0; i < count; i++) {
      if (i > 0)
        append(",");
      append("{");

      std::snprintf(tmp, sizeof(tmp), "\"seq\":%d,", steps[i].sequence);
      append(tmp);

      std::snprintf(tmp, sizeof(tmp), "\"ts\":%ld,", steps[i].timestamp);
      append(tmp);

      append("\"endpoint\":\"");
      append_escaped(steps[i].endpoint);
      append("\",");

      append("\"payload_preview\":\"");
      append_escaped(steps[i].payload_preview);
      append("\",");

      std::snprintf(tmp, sizeof(tmp), "\"http_pairs\":%d,", steps[i].http_pairs);
      append(tmp);

      std::snprintf(tmp, sizeof(tmp), "\"dom_diffs\":%d,", steps[i].dom_diffs);
      append(tmp);

      append("\"hash\":\"");
      append(steps[i].step_hash);
      append("\"}");
    }

    append("]}}");
    buffer_[buffer_pos_] = '\0';

    result.success = true;
    result.steps_exported = count;
    result.total_bytes = buffer_pos_;
    // Chain hash = last step hash
    if (count > 0)
      std::strncpy(result.chain_hash, steps[count - 1].step_hash, 64);

    return result;
  }

  const char *json_output() const { return buffer_; }
  int json_length() const { return buffer_pos_; }

  // Guards
  static bool can_modify_export() { return false; }
  static bool can_alter_hashes() { return false; }
};
