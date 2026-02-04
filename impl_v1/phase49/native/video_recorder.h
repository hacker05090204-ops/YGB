// video_recorder.h
// Phase-49: Native Video Recording Engine
//
// STRICT RULES:
// - Read-only recording
// - Python governance controls recording
// - Frame hash chain for integrity

#ifndef PHASE49_VIDEO_RECORDER_H
#define PHASE49_VIDEO_RECORDER_H

#include <cstdint>
#include <string>
#include <vector>

namespace phase49 {

// Recording state
enum class RecordingState { IDLE, RECORDING, PAUSED, STOPPED };

// Frame info
struct FrameInfo {
  uint64_t frame_number;
  uint64_t timestamp_ms;
  std::string sha256_hash;
};

// Recording result
struct RecordingResult {
  bool success;
  std::string error_message;
  std::string filepath;
  uint64_t total_frames;
  uint64_t duration_ms;
  std::string final_hash; // Hash of entire video file
  std::vector<FrameInfo> frame_chain;
};

// Recording request
struct RecordingRequest {
  std::string request_id;
  std::string output_dir;
  int fps;
  int width;
  int height;
  bool governance_approved;
};

// Video recorder class
class VideoRecorder {
public:
  VideoRecorder();
  ~VideoRecorder();

  bool initialize();

  // Start recording (requires governance approval)
  bool start_recording(const RecordingRequest &request);

  // Capture frame
  bool capture_frame();

  // Stop recording and finalize
  RecordingResult stop_recording();

  // Get current state
  RecordingState get_state() const { return state_; }

  // Pause/resume
  bool pause();
  bool resume();

private:
  RecordingState state_;
  bool initialized_;
  RecordingRequest current_request_;
  std::vector<FrameInfo> frame_chain_;
  uint64_t start_time_ms_;
  uint64_t frame_count_;
  std::string temp_dir_;

  std::string calculate_frame_hash(uint64_t frame_num);
};

// C interface
extern "C" {
void *video_recorder_create();
void video_recorder_destroy(void *recorder);
int video_recorder_init(void *recorder);
int video_recorder_start(void *recorder, const char *request_id,
                         const char *output_dir, int fps, int width, int height,
                         int governance_approved);
int video_recorder_capture_frame(void *recorder);
int video_recorder_stop(void *recorder, char *out_filepath, int filepath_size,
                        uint64_t *out_frames, uint64_t *out_duration_ms);
int video_recorder_get_state(void *recorder);
}

} // namespace phase49

#endif // PHASE49_VIDEO_RECORDER_H
