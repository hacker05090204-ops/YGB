// screenshot_engine.cpp
// Phase-49: Native Screenshot Capture Implementation
//
// CRITICAL RULES:
// - Read-only capture only
// - Python governs all capture decisions
// - All outputs hashed and timestamped

#include "screenshot_engine.h"
#include <chrono>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <sstream>

#ifdef __linux__
#include <fcntl.h>
#include <linux/fb.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#endif

// Simple SHA-256 implementation (for standalone use)
// In production, use OpenSSL or similar
namespace {

// SHA-256 constants
const uint32_t K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
    0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};

uint32_t rotr(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }

std::string sha256_hex(const uint8_t *data, size_t len) {
  uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                   0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};

  // Padding
  size_t padded_len = ((len + 8) / 64 + 1) * 64;
  std::vector<uint8_t> padded(padded_len, 0);
  std::memcpy(padded.data(), data, len);
  padded[len] = 0x80;

  uint64_t bit_len = len * 8;
  for (int i = 0; i < 8; i++) {
    padded[padded_len - 1 - i] = (bit_len >> (i * 8)) & 0xff;
  }

  // Process blocks
  for (size_t i = 0; i < padded_len; i += 64) {
    uint32_t w[64];
    for (int j = 0; j < 16; j++) {
      w[j] = (padded[i + j * 4] << 24) | (padded[i + j * 4 + 1] << 16) |
             (padded[i + j * 4 + 2] << 8) | padded[i + j * 4 + 3];
    }
    for (int j = 16; j < 64; j++) {
      uint32_t s0 = rotr(w[j - 15], 7) ^ rotr(w[j - 15], 18) ^ (w[j - 15] >> 3);
      uint32_t s1 = rotr(w[j - 2], 17) ^ rotr(w[j - 2], 19) ^ (w[j - 2] >> 10);
      w[j] = w[j - 16] + s0 + w[j - 7] + s1;
    }

    uint32_t a = h[0], b = h[1], c = h[2], d = h[3];
    uint32_t e = h[4], f = h[5], g = h[6], hh = h[7];

    for (int j = 0; j < 64; j++) {
      uint32_t S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      uint32_t ch = (e & f) ^ (~e & g);
      uint32_t temp1 = hh + S1 + ch + K[j] + w[j];
      uint32_t S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
      uint32_t temp2 = S0 + maj;

      hh = g;
      g = f;
      f = e;
      e = d + temp1;
      d = c;
      c = b;
      b = a;
      a = temp1 + temp2;
    }

    h[0] += a;
    h[1] += b;
    h[2] += c;
    h[3] += d;
    h[4] += e;
    h[5] += f;
    h[6] += g;
    h[7] += hh;
  }

  std::ostringstream oss;
  for (int i = 0; i < 8; i++) {
    oss << std::hex << std::setfill('0') << std::setw(8) << h[i];
  }
  return oss.str();
}

} // namespace

namespace phase49 {

ScreenshotEngine::ScreenshotEngine() : initialized_(false) {}

ScreenshotEngine::~ScreenshotEngine() = default;

bool ScreenshotEngine::initialize() {
  initialized_ = true;
  return true;
}

uint64_t ScreenshotEngine::get_timestamp_ms() {
  auto now = std::chrono::system_clock::now();
  auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                now.time_since_epoch())
                .count();
  return static_cast<uint64_t>(ms);
}

std::string ScreenshotEngine::calculate_sha256(const std::string &filepath) {
  std::ifstream file(filepath, std::ios::binary | std::ios::ate);
  if (!file.is_open()) {
    return "";
  }

  size_t size = file.tellg();
  file.seekg(0);

  std::vector<uint8_t> buffer(size);
  file.read(reinterpret_cast<char *>(buffer.data()), size);

  return sha256_hex(buffer.data(), buffer.size());
}

ScreenshotResult ScreenshotEngine::capture(const ScreenshotRequest &request) {
  ScreenshotResult result;
  result.success = false;
  result.timestamp_ms = get_timestamp_ms();

  // CRITICAL: Check governance approval
  if (!request.governance_approved) {
    result.error_message = "Governance approval required for screenshot";
    return result;
  }

  // Try DevTools protocol first
  result = capture_via_devtools(request);
  if (result.success) {
    return result;
  }

  // Fallback to framebuffer capture
  result = capture_via_framebuffer(request);
  return result;
}

ScreenshotResult
ScreenshotEngine::capture_via_devtools(const ScreenshotRequest &request) {
  ScreenshotResult result;
  result.success = false;
  result.timestamp_ms = get_timestamp_ms();

  // DevTools protocol implementation would go here
  // For now, indicate that DevTools is not available
  result.error_message = "DevTools protocol not connected";
  return result;
}

ScreenshotResult
ScreenshotEngine::capture_via_framebuffer(const ScreenshotRequest &request) {
  ScreenshotResult result;
  result.success = false;
  result.timestamp_ms = get_timestamp_ms();

#ifdef __linux__
  // Linux framebuffer capture
  int fb = open("/dev/fb0", O_RDONLY);
  if (fb < 0) {
    result.error_message = "Cannot open framebuffer /dev/fb0";
    return result;
  }

  struct fb_var_screeninfo vinfo;
  if (ioctl(fb, FBIOGET_VSCREENINFO, &vinfo) != 0) {
    close(fb);
    result.error_message = "Cannot get screen info";
    return result;
  }

  result.width = vinfo.xres;
  result.height = vinfo.yres;
  size_t screen_size = vinfo.xres * vinfo.yres * vinfo.bits_per_pixel / 8;

  void *fb_ptr = mmap(nullptr, screen_size, PROT_READ, MAP_SHARED, fb, 0);
  if (fb_ptr == MAP_FAILED) {
    close(fb);
    result.error_message = "Cannot mmap framebuffer";
    return result;
  }

  // Generate output filename
  std::ostringstream filename;
  filename << request.output_dir << "/screenshot_" << request.request_id << "_"
           << result.timestamp_ms << ".raw";
  result.filepath = filename.str();

  // Write raw data (in production, would encode to PNG)
  std::ofstream out(result.filepath, std::ios::binary);
  if (out.is_open()) {
    out.write(static_cast<const char *>(fb_ptr), screen_size);
    out.close();

    result.success = true;
    result.file_size = screen_size;
    result.sha256_hash = calculate_sha256(result.filepath);
  } else {
    result.error_message = "Cannot write output file";
  }

  munmap(fb_ptr, screen_size);
  close(fb);
#else
  result.error_message = "Framebuffer capture not supported on this platform";
#endif

  return result;
}

// C interface implementations
extern "C" {

void *screenshot_engine_create() { return new ScreenshotEngine(); }

void screenshot_engine_destroy(void *engine) {
  delete static_cast<ScreenshotEngine *>(engine);
}

int screenshot_engine_init(void *engine) {
  if (!engine)
    return -1;
  return static_cast<ScreenshotEngine *>(engine)->initialize() ? 0 : -1;
}

int screenshot_engine_capture(void *engine, const char *request_id,
                              const char *target_url, const char *output_dir,
                              int format, int viewport_width,
                              int viewport_height, int full_page,
                              int governance_approved, char *out_filepath,
                              int filepath_buffer_size, char *out_hash,
                              int hash_buffer_size, uint64_t *out_timestamp,
                              int *out_width, int *out_height,
                              size_t *out_file_size) {
  if (!engine || !request_id || !output_dir)
    return -1;

  ScreenshotRequest request;
  request.request_id = request_id;
  request.target_url = target_url ? target_url : "";
  request.output_dir = output_dir;
  request.format = static_cast<ScreenshotFormat>(format);
  request.viewport_width = viewport_width;
  request.viewport_height = viewport_height;
  request.full_page = full_page != 0;
  request.governance_approved = governance_approved != 0;

  ScreenshotResult result =
      static_cast<ScreenshotEngine *>(engine)->capture(request);

  if (out_filepath && filepath_buffer_size > 0) {
    strncpy(out_filepath, result.filepath.c_str(), filepath_buffer_size - 1);
    out_filepath[filepath_buffer_size - 1] = '\0';
  }
  if (out_hash && hash_buffer_size > 0) {
    strncpy(out_hash, result.sha256_hash.c_str(), hash_buffer_size - 1);
    out_hash[hash_buffer_size - 1] = '\0';
  }
  if (out_timestamp)
    *out_timestamp = result.timestamp_ms;
  if (out_width)
    *out_width = result.width;
  if (out_height)
    *out_height = result.height;
  if (out_file_size)
    *out_file_size = result.file_size;

  return result.success ? 0 : -1;
}

} // extern "C"

} // namespace phase49
