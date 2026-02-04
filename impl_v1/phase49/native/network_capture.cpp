// network_capture.cpp
// Phase-49: Network Capture Implementation

#include "network_capture.h"
#include <chrono>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <sstream>

namespace phase49 {

NetworkCaptureEngine::NetworkCaptureEngine()
    : initialized_(false), capturing_(false), start_time_ms_(0) {}

NetworkCaptureEngine::~NetworkCaptureEngine() {
  if (capturing_) {
    stop_capture();
  }
}

bool NetworkCaptureEngine::initialize() {
  initialized_ = true;
  return true;
}

bool NetworkCaptureEngine::start_capture(const std::string &session_id,
                                         const std::string &output_dir,
                                         bool governance_approved) {
  if (capturing_) {
    return false;
  }

  // CRITICAL: Check governance
  if (!governance_approved) {
    return false;
  }

  session_id_ = session_id;
  output_dir_ = output_dir;
  captures_.clear();

  auto now = std::chrono::system_clock::now();
  start_time_ms_ = std::chrono::duration_cast<std::chrono::milliseconds>(
                       now.time_since_epoch())
                       .count();

  capturing_ = true;
  return true;
}

bool NetworkCaptureEngine::add_capture(const NetworkCapture &capture) {
  if (!capturing_) {
    return false;
  }
  captures_.push_back(capture);
  return true;
}

CaptureResult NetworkCaptureEngine::stop_capture() {
  CaptureResult result;
  result.success = false;

  if (!capturing_) {
    result.error_message = "Not capturing";
    return result;
  }

  capturing_ = false;

  // Generate output filename
  std::ostringstream filename;
  filename << output_dir_ << "/network_" << session_id_ << "_" << start_time_ms_
           << ".har";
  result.output_filepath = filename.str();

  // Export to HAR
  std::string har = export_to_har();

  // Write file
  std::ofstream out(result.output_filepath);
  if (out.is_open()) {
    out << har;
    out.close();
    result.success = true;
  } else {
    result.error_message = "Cannot write output file";
  }

  result.captures = captures_;
  return result;
}

std::string NetworkCaptureEngine::export_to_har() const {
  std::ostringstream har;

  har << "{\n";
  har << "  \"log\": {\n";
  har << "    \"version\": \"1.2\",\n";
  har << "    \"creator\": {\n";
  har << "      \"name\": \"Phase49-NetworkCapture\",\n";
  har << "      \"version\": \"1.0\"\n";
  har << "    },\n";
  har << "    \"entries\": [\n";

  for (size_t i = 0; i < captures_.size(); i++) {
    const auto &cap = captures_[i];

    // Method to string
    std::string method_str;
    switch (cap.request.method) {
    case HttpMethod::GET:
      method_str = "GET";
      break;
    case HttpMethod::POST:
      method_str = "POST";
      break;
    case HttpMethod::PUT:
      method_str = "PUT";
      break;
    case HttpMethod::DELETE:
      method_str = "DELETE";
      break;
    case HttpMethod::PATCH:
      method_str = "PATCH";
      break;
    case HttpMethod::HEAD:
      method_str = "HEAD";
      break;
    case HttpMethod::OPTIONS:
      method_str = "OPTIONS";
      break;
    default:
      method_str = "UNKNOWN";
    }

    har << "      {\n";
    har << "        \"startedDateTime\": \"" << cap.request.timestamp_ms
        << "\",\n";
    har << "        \"time\": " << cap.duration_ms << ",\n";
    har << "        \"request\": {\n";
    har << "          \"method\": \"" << method_str << "\",\n";
    har << "          \"url\": \"" << cap.request.url << "\",\n";
    har << "          \"httpVersion\": \"HTTP/1.1\",\n";
    har << "          \"headers\": [],\n";
    har << "          \"queryString\": [],\n";
    har << "          \"bodySize\": " << cap.request.body_size << "\n";
    har << "        },\n";
    har << "        \"response\": {\n";
    har << "          \"status\": " << cap.response.status_code << ",\n";
    har << "          \"statusText\": \"" << cap.response.status_text
        << "\",\n";
    har << "          \"httpVersion\": \"HTTP/1.1\",\n";
    har << "          \"headers\": [],\n";
    har << "          \"content\": {\n";
    har << "            \"size\": " << cap.response.body_size << ",\n";
    har << "            \"mimeType\": \"" << cap.response.content_type
        << "\"\n";
    har << "          },\n";
    har << "          \"bodySize\": " << cap.response.body_size << "\n";
    har << "        },\n";
    har << "        \"cache\": {},\n";
    har << "        \"timings\": {\n";
    har << "          \"send\": 0,\n";
    har << "          \"wait\": " << cap.duration_ms << ",\n";
    har << "          \"receive\": 0\n";
    har << "        }\n";
    har << "      }";

    if (i < captures_.size() - 1) {
      har << ",";
    }
    har << "\n";
  }

  har << "    ]\n";
  har << "  }\n";
  har << "}\n";

  return har.str();
}

// C interface
extern "C" {

void *network_capture_create() { return new NetworkCaptureEngine(); }

void network_capture_destroy(void *engine) {
  delete static_cast<NetworkCaptureEngine *>(engine);
}

int network_capture_init(void *engine) {
  if (!engine)
    return -1;
  return static_cast<NetworkCaptureEngine *>(engine)->initialize() ? 0 : -1;
}

int network_capture_start(void *engine, const char *session_id,
                          const char *output_dir, int governance_approved) {
  if (!engine || !session_id || !output_dir)
    return -1;

  return static_cast<NetworkCaptureEngine *>(engine)->start_capture(
             session_id, output_dir, governance_approved != 0)
             ? 0
             : -1;
}

int network_capture_add(void *engine, const char *request_id, int method,
                        const char *url, int status_code,
                        uint64_t duration_ms) {
  if (!engine || !request_id || !url)
    return -1;

  NetworkCapture cap;
  cap.request.request_id = request_id;
  cap.request.method = static_cast<HttpMethod>(method);
  cap.request.url = url;
  cap.request.timestamp_ms =
      std::chrono::duration_cast<std::chrono::milliseconds>(
          std::chrono::system_clock::now().time_since_epoch())
          .count();
  cap.response.request_id = request_id;
  cap.response.status_code = status_code;
  cap.duration_ms = duration_ms;

  return static_cast<NetworkCaptureEngine *>(engine)->add_capture(cap) ? 0 : -1;
}

int network_capture_stop(void *engine, char *out_filepath, int filepath_size) {
  if (!engine)
    return -1;

  CaptureResult result =
      static_cast<NetworkCaptureEngine *>(engine)->stop_capture();

  if (out_filepath && filepath_size > 0) {
    strncpy(out_filepath, result.output_filepath.c_str(), filepath_size - 1);
    out_filepath[filepath_size - 1] = '\0';
  }

  return result.success ? 0 : -1;
}

int network_capture_export_har(void *engine, char *out_har,
                               int har_buffer_size) {
  if (!engine || !out_har || har_buffer_size <= 0)
    return -1;

  std::string har =
      static_cast<NetworkCaptureEngine *>(engine)->export_to_har();

  if (har.size() >= static_cast<size_t>(har_buffer_size)) {
    return -1; // Buffer too small
  }

  strncpy(out_har, har.c_str(), har_buffer_size - 1);
  out_har[har_buffer_size - 1] = '\0';

  return 0;
}

} // extern "C"

} // namespace phase49
