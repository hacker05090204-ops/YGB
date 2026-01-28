// browser_engine.cpp
// Phase-49: C++ Browser Engine Implementation
//
// CRITICAL RULES:
// - Python ALWAYS governs browser launch
// - NO exploit logic
// - NO auto-submit
// - Human approval required before any launch

#include "browser_engine.h"
#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>

#ifdef _WIN32
#include <windows.h>
#else
#include <signal.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#endif

namespace phase49 {

BrowserEngine::BrowserEngine() : initialized_(false) {}

BrowserEngine::~BrowserEngine() {
  // Stop all running processes on destruction
  for (int pid : running_processes_) {
    stop(pid);
  }
}

bool BrowserEngine::initialize() {
  // Check for browser availability
  std::string chromium = get_chromium_path();
  if (chromium.empty()) {
    std::cerr << "Warning: Chromium not found" << std::endl;
  }

  initialized_ = true;
  return true;
}

std::string BrowserEngine::get_chromium_path() const {
#ifdef _WIN32
  // Windows paths
  const char *paths[] = {
      "C:\\Program Files\\Chromium\\Application\\chrome.exe",
      "C:\\Program Files (x86)\\Chromium\\Application\\chrome.exe", nullptr};
#elif __APPLE__
  // macOS paths
  const char *paths[] = {"/Applications/Chromium.app/Contents/MacOS/Chromium",
                         "/usr/local/bin/chromium", nullptr};
#else
  // Linux paths
  const char *paths[] = {"/usr/bin/chromium", "/usr/bin/chromium-browser",
                         "/snap/bin/chromium", "/usr/local/bin/chromium",
                         nullptr};
#endif

  for (int i = 0; paths[i] != nullptr; i++) {
    std::ifstream f(paths[i]);
    if (f.good()) {
      return std::string(paths[i]);
    }
  }

  return "";
}

std::string BrowserEngine::get_edge_path() const {
#ifdef _WIN32
  return "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
#elif __APPLE__
  return "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge";
#else
  return "/usr/bin/microsoft-edge";
#endif
}

BrowserLaunchResponse
BrowserEngine::launch(const BrowserLaunchRequest &request) {
  BrowserLaunchResponse response;
  response.request_id = request.request_id;
  response.process_id = -1;
  response.fallback_used = false;

  // CRITICAL: Check governance approval
  if (!request.governance_approved) {
    response.result = LaunchResult::FAILED_GOVERNANCE_CHECK;
    response.error_message = "Governance approval required";
    return response;
  }

  // CRITICAL: Check human approval
  if (!request.human_approved) {
    response.result = LaunchResult::FAILED_PERMISSION_DENIED;
    response.error_message = "Human approval required";
    return response;
  }

  // Try primary browser
  if (request.browser_type == BrowserType::UNGOOGLED_CHROMIUM) {
    response = launch_chromium(request);

    // Fallback to Edge if Chromium fails
    if (response.result != LaunchResult::SUCCESS) {
      BrowserLaunchRequest fallback_request = request;
      fallback_request.browser_type = BrowserType::EDGE_HEADLESS;

      BrowserLaunchResponse fallback = launch_edge_headless(fallback_request);
      if (fallback.result == LaunchResult::SUCCESS) {
        fallback.fallback_used = true;
        fallback.fallback_reason = "Chromium not available";
        return fallback;
      }
    }
  } else {
    response = launch_edge_headless(request);
  }

  return response;
}

BrowserLaunchResponse
BrowserEngine::launch_chromium(const BrowserLaunchRequest &request) {
  BrowserLaunchResponse response;
  response.request_id = request.request_id;
  response.fallback_used = false;

  std::string path = get_chromium_path();
  if (path.empty()) {
    response.result = LaunchResult::FAILED_BROWSER_NOT_FOUND;
    response.error_message = "Chromium not found";
    response.process_id = -1;
    return response;
  }

  // MOCK: In real implementation, would fork/exec browser
  // For governance testing, we just validate and return mock PID
  response.result = LaunchResult::SUCCESS;
  response.error_message = "";
  response.process_id = 1000 + (rand() % 9000); // Mock PID

  running_processes_.push_back(response.process_id);

  return response;
}

BrowserLaunchResponse
BrowserEngine::launch_edge_headless(const BrowserLaunchRequest &request) {
  BrowserLaunchResponse response;
  response.request_id = request.request_id;
  response.fallback_used = false;

  std::string path = get_edge_path();
  if (path.empty()) {
    response.result = LaunchResult::FAILED_BROWSER_NOT_FOUND;
    response.error_message = "Edge not found";
    response.process_id = -1;
    return response;
  }

  // MOCK: Same as above
  response.result = LaunchResult::SUCCESS;
  response.error_message = "";
  response.process_id = 2000 + (rand() % 9000); // Mock PID

  running_processes_.push_back(response.process_id);

  return response;
}

bool BrowserEngine::stop(int process_id) {
  auto it = std::find(running_processes_.begin(), running_processes_.end(),
                      process_id);
  if (it == running_processes_.end()) {
    return false;
  }

  // MOCK: In real implementation, would kill process
  running_processes_.erase(it);
  return true;
}

bool BrowserEngine::is_running(int process_id) const {
  return std::find(running_processes_.begin(), running_processes_.end(),
                   process_id) != running_processes_.end();
}

// C interface implementations
extern "C" {

void *browser_engine_create() { return new BrowserEngine(); }

void browser_engine_destroy(void *engine) {
  delete static_cast<BrowserEngine *>(engine);
}

int browser_engine_init(void *engine) {
  if (!engine)
    return -1;
  return static_cast<BrowserEngine *>(engine)->initialize() ? 0 : -1;
}

int browser_engine_launch(void *engine, const char *request_id,
                          int browser_type, int mode, const char *target_url,
                          int governance_approved, int human_approved,
                          int *out_process_id, char *out_error,
                          int error_buffer_size) {
  if (!engine || !request_id || !target_url)
    return -1;

  BrowserLaunchRequest request;
  request.request_id = request_id;
  request.browser_type = browser_type == 0 ? BrowserType::UNGOOGLED_CHROMIUM
                                           : BrowserType::EDGE_HEADLESS;
  request.mode = mode == 0 ? LaunchMode::HEADED : LaunchMode::HEADLESS;
  request.target_url = target_url;
  request.governance_approved = governance_approved != 0;
  request.human_approved = human_approved != 0;

  BrowserLaunchResponse response =
      static_cast<BrowserEngine *>(engine)->launch(request);

  if (out_process_id) {
    *out_process_id = response.process_id;
  }

  if (out_error && error_buffer_size > 0) {
    strncpy(out_error, response.error_message.c_str(), error_buffer_size - 1);
    out_error[error_buffer_size - 1] = '\0';
  }

  return static_cast<int>(response.result);
}

int browser_engine_stop(void *engine, int process_id) {
  if (!engine)
    return -1;
  return static_cast<BrowserEngine *>(engine)->stop(process_id) ? 0 : -1;
}

int browser_engine_is_running(void *engine, int process_id) {
  if (!engine)
    return -1;
  return static_cast<BrowserEngine *>(engine)->is_running(process_id) ? 1 : 0;
}

} // extern "C"

} // namespace phase49
