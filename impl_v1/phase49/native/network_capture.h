// network_capture.h
// Phase-49: Network Request/Response Capture
//
// STRICT RULES:
// - Read-only capture
// - No modification of traffic
// - No injection

#ifndef PHASE49_NETWORK_CAPTURE_H
#define PHASE49_NETWORK_CAPTURE_H

#include <cstdint>
#include <string>
#include <vector>

namespace phase49 {

// HTTP methods
enum class HttpMethod { GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS, UNKNOWN };

// Request info
struct NetworkRequest {
  std::string request_id;
  uint64_t timestamp_ms;
  HttpMethod method;
  std::string url;
  std::string host;
  std::string path;
  std::vector<std::pair<std::string, std::string>> headers;
  std::string body;
  size_t body_size;
};

// Response info
struct NetworkResponse {
  std::string request_id;
  uint64_t timestamp_ms;
  int status_code;
  std::string status_text;
  std::vector<std::pair<std::string, std::string>> headers;
  std::string content_type;
  size_t body_size;
  std::string body_hash; // SHA-256 of body
};

// Capture entry
struct NetworkCapture {
  NetworkRequest request;
  NetworkResponse response;
  uint64_t duration_ms;
};

// Capture result
struct CaptureResult {
  bool success;
  std::string error_message;
  std::vector<NetworkCapture> captures;
  std::string output_filepath;
};

// Network capture engine
class NetworkCaptureEngine {
public:
  NetworkCaptureEngine();
  ~NetworkCaptureEngine();

  bool initialize();

  // Start capture session
  bool start_capture(const std::string &session_id,
                     const std::string &output_dir, bool governance_approved);

  // Add captured request/response pair
  bool add_capture(const NetworkCapture &capture);

  // Stop capture and save
  CaptureResult stop_capture();

  // Export captures to HAR format
  std::string export_to_har() const;

  bool is_capturing() const { return capturing_; }

private:
  bool initialized_;
  bool capturing_;
  std::string session_id_;
  std::string output_dir_;
  std::vector<NetworkCapture> captures_;
  uint64_t start_time_ms_;
};

// C interface
extern "C" {
void *network_capture_create();
void network_capture_destroy(void *engine);
int network_capture_init(void *engine);
int network_capture_start(void *engine, const char *session_id,
                          const char *output_dir, int governance_approved);
int network_capture_add(void *engine, const char *request_id, int method,
                        const char *url, int status_code, uint64_t duration_ms);
int network_capture_stop(void *engine, char *out_filepath, int filepath_size);
int network_capture_export_har(void *engine, char *out_har,
                               int har_buffer_size);
}

} // namespace phase49

#endif // PHASE49_NETWORK_CAPTURE_H
