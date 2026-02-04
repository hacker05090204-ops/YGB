// screenshot_engine.h
// Phase-49: Native Screenshot Capture Engine
//
// STRICT RULES:
// - Read-only capture
// - No modification of page content
// - Python governance controls when/what to capture
// - All outputs hashed and timestamped

#ifndef PHASE49_SCREENSHOT_ENGINE_H
#define PHASE49_SCREENSHOT_ENGINE_H

#include <cstdint>
#include <string>

namespace phase49 {

// Screenshot format
enum class ScreenshotFormat { PNG, JPEG, WEBP };

// Screenshot result
struct ScreenshotResult {
  bool success;
  std::string error_message;
  std::string filepath;
  std::string sha256_hash;
  uint64_t timestamp_ms;
  int width;
  int height;
  size_t file_size;
};

// Screenshot request (from Python governance)
struct ScreenshotRequest {
  std::string request_id;
  std::string target_url;
  std::string output_dir;
  ScreenshotFormat format;
  int viewport_width;
  int viewport_height;
  bool full_page;
  bool governance_approved;
};

// Screenshot engine class
class ScreenshotEngine {
public:
  ScreenshotEngine();
  ~ScreenshotEngine();

  // Initialize engine
  bool initialize();

  // Capture screenshot (requires governance approval)
  ScreenshotResult capture(const ScreenshotRequest &request);

  // Calculate SHA-256 hash of file
  static std::string calculate_sha256(const std::string &filepath);

  // Get current timestamp in milliseconds
  static uint64_t get_timestamp_ms();

private:
  bool initialized_;

  // Capture via DevTools protocol
  ScreenshotResult capture_via_devtools(const ScreenshotRequest &request);

  // Fallback: capture via X11 framebuffer (Linux)
  ScreenshotResult capture_via_framebuffer(const ScreenshotRequest &request);
};

// C interface for Python bindings
extern "C" {
void *screenshot_engine_create();
void screenshot_engine_destroy(void *engine);
int screenshot_engine_init(void *engine);
int screenshot_engine_capture(void *engine, const char *request_id,
                              const char *target_url, const char *output_dir,
                              int format, // 0=PNG, 1=JPEG, 2=WEBP
                              int viewport_width, int viewport_height,
                              int full_page, int governance_approved,
                              char *out_filepath, int filepath_buffer_size,
                              char *out_hash, int hash_buffer_size,
                              uint64_t *out_timestamp, int *out_width,
                              int *out_height, size_t *out_file_size);
}

} // namespace phase49

#endif // PHASE49_SCREENSHOT_ENGINE_H
