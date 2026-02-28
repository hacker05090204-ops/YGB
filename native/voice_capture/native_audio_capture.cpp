/*
 * Native Audio Capture — WASAPI-based audio capture for Windows.
 *
 * Provides real-time PCM audio capture from the default microphone.
 * Exposed via C ABI for Python ctypes bridge.
 *
 * Build: cl /O2 /LD /Fe:native_audio_capture.dll native_audio_capture.cpp
 * ole32.lib
 */

#ifdef _WIN32

#include <audioclient.h>
#include <mmdeviceapi.h>
#include <stdio.h>
#include <string.h>
#include <windows.h>


// Capture state
static IAudioClient *g_audio_client = nullptr;
static IAudioCaptureClient *g_capture_client = nullptr;
static WAVEFORMATEX *g_wave_format = nullptr;
static bool g_initialized = false;
static bool g_capturing = false;

extern "C" {

/*
 * Initialize audio capture device.
 * Returns 0 on success, -1 on failure.
 */
__declspec(dllexport) int audio_capture_init(int sample_rate, int channels,
                                             int bits_per_sample) {
  if (g_initialized)
    return 0;

  HRESULT hr;

  hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
  if (FAILED(hr) && hr != RPC_E_CHANGED_MODE)
    return -1;

  IMMDeviceEnumerator *enumerator = nullptr;
  hr = CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
                        __uuidof(IMMDeviceEnumerator), (void **)&enumerator);
  if (FAILED(hr))
    return -1;

  IMMDevice *device = nullptr;
  hr = enumerator->GetDefaultAudioEndpoint(eCapture, eConsole, &device);
  enumerator->Release();
  if (FAILED(hr))
    return -1;

  hr = device->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr,
                        (void **)&g_audio_client);
  device->Release();
  if (FAILED(hr))
    return -1;

  // Configure format
  WAVEFORMATEX requested_format = {};
  requested_format.wFormatTag = WAVE_FORMAT_PCM;
  requested_format.nChannels = (WORD)channels;
  requested_format.nSamplesPerSec = (DWORD)sample_rate;
  requested_format.wBitsPerSample = (WORD)bits_per_sample;
  requested_format.nBlockAlign =
      requested_format.nChannels * requested_format.wBitsPerSample / 8;
  requested_format.nAvgBytesPerSec =
      requested_format.nSamplesPerSec * requested_format.nBlockAlign;
  requested_format.cbSize = 0;

  // Initialize audio client (100ms buffer)
  REFERENCE_TIME hns_requested_duration = 1000000; // 100ms in 100ns units
  hr = g_audio_client->Initialize(AUDCLNT_SHAREMODE_SHARED, 0,
                                  hns_requested_duration, 0, &requested_format,
                                  nullptr);
  if (FAILED(hr)) {
    // Try with device's native format
    hr = g_audio_client->GetMixFormat(&g_wave_format);
    if (FAILED(hr))
      return -1;

    hr = g_audio_client->Initialize(AUDCLNT_SHAREMODE_SHARED, 0,
                                    hns_requested_duration, 0, g_wave_format,
                                    nullptr);
    if (FAILED(hr))
      return -1;
  } else {
    // Allocate a copy for our format
    g_wave_format = (WAVEFORMATEX *)CoTaskMemAlloc(sizeof(WAVEFORMATEX));
    if (g_wave_format) {
      memcpy(g_wave_format, &requested_format, sizeof(WAVEFORMATEX));
    }
  }

  hr = g_audio_client->GetService(__uuidof(IAudioCaptureClient),
                                  (void **)&g_capture_client);
  if (FAILED(hr))
    return -1;

  hr = g_audio_client->Start();
  if (FAILED(hr))
    return -1;

  g_initialized = true;
  g_capturing = true;

  return 0;
}

/*
 * Read audio data from capture buffer.
 * Returns number of bytes read, or 0 if no data available, or -1 on error.
 */
__declspec(dllexport) int audio_capture_read(char *buffer, int buffer_size) {
  if (!g_initialized || !g_capturing)
    return -1;

  UINT32 packet_length = 0;
  HRESULT hr = g_capture_client->GetNextPacketSize(&packet_length);
  if (FAILED(hr) || packet_length == 0)
    return 0;

  BYTE *data = nullptr;
  UINT32 num_frames = 0;
  DWORD flags = 0;

  hr =
      g_capture_client->GetBuffer(&data, &num_frames, &flags, nullptr, nullptr);
  if (FAILED(hr))
    return -1;

  int bytes_to_copy = 0;
  if (g_wave_format) {
    bytes_to_copy = num_frames * g_wave_format->nBlockAlign;
    if (bytes_to_copy > buffer_size) {
      bytes_to_copy = buffer_size;
    }
  }

  if (flags & AUDCLNT_BUFFERFLAGS_SILENT) {
    memset(buffer, 0, bytes_to_copy);
  } else {
    memcpy(buffer, data, bytes_to_copy);
  }

  g_capture_client->ReleaseBuffer(num_frames);

  return bytes_to_copy;
}

/*
 * Stop audio capture and release resources.
 */
__declspec(dllexport) void audio_capture_stop() {
  g_capturing = false;

  if (g_audio_client) {
    g_audio_client->Stop();
  }
  if (g_capture_client) {
    g_capture_client->Release();
    g_capture_client = nullptr;
  }
  if (g_audio_client) {
    g_audio_client->Release();
    g_audio_client = nullptr;
  }
  if (g_wave_format) {
    CoTaskMemFree(g_wave_format);
    g_wave_format = nullptr;
  }

  g_initialized = false;
}

} // extern "C"

#else
// Non-Windows stub
extern "C" {
int audio_capture_init(int sr, int ch, int bits) { return -1; }
int audio_capture_read(char *buf, int sz) { return -1; }
void audio_capture_stop() {}
}
#endif
