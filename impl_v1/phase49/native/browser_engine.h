// browser_engine.h
// Phase-49: C++ Browser Engine Header
//
// STRICT RULES:
// - Python ALWAYS governs browser launch
// - NO exploit logic
// - NO auto-submit
// - Human approval required before any launch

#ifndef PHASE49_BROWSER_ENGINE_H
#define PHASE49_BROWSER_ENGINE_H

#include <string>
#include <vector>

namespace phase49 {

// Browser types
enum class BrowserType {
  UNGOOGLED_CHROMIUM, // Default, headed
  EDGE_HEADLESS       // Last resort fallback
};

// Launch modes
enum class LaunchMode {
  HEADED,  // User can see browser
  HEADLESS // Background (requires explicit approval)
};

// Launch result
enum class LaunchResult {
  SUCCESS,
  FAILED_GOVERNANCE_CHECK,
  FAILED_BROWSER_NOT_FOUND,
  FAILED_PERMISSION_DENIED,
  FAILED_ALREADY_RUNNING,
  FAILED_UNKNOWN
};

// Browser launch request (from Python governance layer)
struct BrowserLaunchRequest {
  std::string request_id;
  BrowserType browser_type;
  LaunchMode mode;
  std::string target_url;
  bool governance_approved;
  bool human_approved;
};

// Browser launch response
struct BrowserLaunchResponse {
  std::string request_id;
  LaunchResult result;
  std::string error_message;
  int process_id;
  bool fallback_used;
  std::string fallback_reason;
};

// Browser engine interface
class BrowserEngine {
public:
  BrowserEngine();
  ~BrowserEngine();

  // Initialize engine
  bool initialize();

  // Launch browser (requires governance approval)
  BrowserLaunchResponse launch(const BrowserLaunchRequest &request);

  // Stop browser
  bool stop(int process_id);

  // Check if browser is running
  bool is_running(int process_id) const;

  // Get Chromium path
  std::string get_chromium_path() const;

  // Get Edge path
  std::string get_edge_path() const;

private:
  bool initialized_;
  std::vector<int> running_processes_;

  // Internal launch methods
  BrowserLaunchResponse launch_chromium(const BrowserLaunchRequest &request);
  BrowserLaunchResponse
  launch_edge_headless(const BrowserLaunchRequest &request);
};

// C interface for Python bindings (ctypes compatible)
extern "C" {
// Create engine instance
void *browser_engine_create();

// Destroy engine instance
void browser_engine_destroy(void *engine);

// Initialize engine
int browser_engine_init(void *engine);

// Launch browser
// Returns: 0 = success, non-zero = error code
int browser_engine_launch(void *engine, const char *request_id,
                          int browser_type, // 0 = Chromium, 1 = Edge
                          int mode,         // 0 = Headed, 1 = Headless
                          const char *target_url, int governance_approved,
                          int human_approved, int *out_process_id,
                          char *out_error, int error_buffer_size);

// Stop browser
int browser_engine_stop(void *engine, int process_id);

// Check if running
int browser_engine_is_running(void *engine, int process_id);
}

} // namespace phase49

#endif // PHASE49_BROWSER_ENGINE_H
