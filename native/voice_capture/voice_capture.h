/*
 * voice_capture.h — Native Microphone Capture API
 *
 * Provides device-level mic access with:
 *   - Voice Activity Detection (VAD)
 *   - Noise gate / suppression
 *   - PCM16 audio buffer output
 *
 * Platform: Windows (WASAPI)
 * Build: cl /LD voice_capture.cpp /Fe:voice_capture.dll
 */

#ifndef VOICE_CAPTURE_H
#define VOICE_CAPTURE_H

#ifdef _WIN32
#ifdef VOICE_CAPTURE_EXPORTS
#define VC_API __declspec(dllexport)
#else
#define VC_API __declspec(dllimport)
#endif
#else
#define VC_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* ========================================================================= */
/* VAD States                                                                 */
/* ========================================================================= */

#define VAD_SILENT 0
#define VAD_SPEAKING 1
#define VAD_NOISE 2

/* ========================================================================= */
/* Capture Configuration                                                      */
/* ========================================================================= */

typedef struct {
  int sample_rate;     /* Default: 16000 Hz (STT optimal) */
  int channels;        /* Default: 1 (mono) */
  int bits_per_sample; /* Default: 16 (PCM16) */
  float vad_threshold; /* Energy threshold for VAD, 0.0-1.0 */
  float noise_gate_db; /* Noise gate in dB, default -40.0 */
  int chunk_ms;        /* Audio chunk size in ms, default 100 */
} VoiceCaptureConfig;

/* ========================================================================= */
/* Core API                                                                   */
/* ========================================================================= */

/**
 * Initialize capture with config. Returns 0 on success, -1 on error.
 * If config is NULL, uses defaults (16kHz, mono, PCM16).
 */
VC_API int capture_init(const VoiceCaptureConfig *config);

/**
 * Start capturing from default mic. Returns 0 on success.
 */
VC_API int capture_start(void);

/**
 * Stop capturing. Returns 0 on success.
 */
VC_API int capture_stop(void);

/**
 * Shutdown and release all resources.
 */
VC_API void capture_shutdown(void);

/**
 * Get current VAD state: VAD_SILENT, VAD_SPEAKING, or VAD_NOISE.
 */
VC_API int capture_get_vad_state(void);

/**
 * Get latest audio chunk. Writes PCM16 data to buffer.
 * Returns number of bytes written, or -1 if no data available.
 *
 * @param buffer   Output buffer (caller-allocated)
 * @param max_len  Max bytes to write
 */
VC_API int capture_get_audio_chunk(char *buffer, int max_len);

/**
 * Get current noise level in dB (negative values, -60 = quiet).
 */
VC_API float capture_get_noise_level(void);

/**
 * Check if capture is currently active.
 * Returns 1 if active, 0 if stopped.
 */
VC_API int capture_is_active(void);

/**
 * Get capture mode string: "REAL" if WASAPI available, "DEGRADED" otherwise.
 * Writes into buffer, returns bytes written.
 */
VC_API int capture_get_mode(char *buffer, int max_len);

#ifdef __cplusplus
}
#endif

#endif /* VOICE_CAPTURE_H */
