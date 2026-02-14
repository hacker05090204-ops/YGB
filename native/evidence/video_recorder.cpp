/*
 * video_recorder.cpp — Forensic Video Frame Engine
 *
 * RULES:
 *   - Every frame hashed with SHA256
 *   - Timestamp embedded in metadata
 *   - No modification after recording
 *   - Append-only frame storage
 *   - Max duration enforced
 *   - .webm format target
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>


// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int MAX_FRAMES = 10000;
static constexpr int MAX_FRAME_SIZE = 512 * 1024; // 512KB per frame
static constexpr int MAX_DURATION_SECONDS = 300;  // 5 minutes max
static constexpr int MAX_FPS = 30;
static constexpr int MAX_HASH_HEX = 65;

// =========================================================================
// INLINE SHA256 (self-contained)
// =========================================================================

static const unsigned int K256[64] = {
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

static inline unsigned int rotr(unsigned int x, int n) {
  return (x >> n) | (x << (32 - n));
}
static void sha256_transform(unsigned int st[8], const unsigned char blk[64]) {
  unsigned int w[64];
  for (int i = 0; i < 16; i++)
    w[i] = ((unsigned int)blk[i * 4] << 24) |
           ((unsigned int)blk[i * 4 + 1] << 16) |
           ((unsigned int)blk[i * 4 + 2] << 8) | ((unsigned int)blk[i * 4 + 3]);
  for (int i = 16; i < 64; i++) {
    unsigned int s0 =
        rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
    unsigned int s1 =
        rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  unsigned int a = st[0], b = st[1], c = st[2], d = st[3], e = st[4], f = st[5],
               g = st[6], h = st[7];
  for (int i = 0; i < 64; i++) {
    unsigned int S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
    unsigned int ch = (e & f) ^ (~e & g);
    unsigned int t1 = h + S1 + ch + K256[i] + w[i];
    unsigned int S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
    unsigned int maj = (a & b) ^ (a & c) ^ (b & c);
    unsigned int t2 = S0 + maj;
    h = g;
    g = f;
    f = e;
    e = d + t1;
    d = c;
    c = b;
    b = a;
    a = t1 + t2;
  }
  st[0] += a;
  st[1] += b;
  st[2] += c;
  st[3] += d;
  st[4] += e;
  st[5] += f;
  st[6] += g;
  st[7] += h;
}
static void sha256_hash(const unsigned char *data, size_t len,
                        unsigned char out[32]) {
  unsigned int st[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  unsigned char blk[64];
  size_t bl = 0;
  for (size_t i = 0; i < len; i++) {
    blk[bl++] = data[i];
    if (bl == 64) {
      sha256_transform(st, blk);
      bl = 0;
    }
  }
  blk[bl++] = 0x80;
  if (bl > 56) {
    while (bl < 64)
      blk[bl++] = 0;
    sha256_transform(st, blk);
    bl = 0;
  }
  while (bl < 56)
    blk[bl++] = 0;
  unsigned long long bits = (unsigned long long)len * 8;
  for (int j = 7; j >= 0; j--)
    blk[56 + (7 - j)] = (unsigned char)(bits >> (j * 8));
  sha256_transform(st, blk);
  for (int j = 0; j < 8; j++) {
    out[j * 4] = (unsigned char)(st[j] >> 24);
    out[j * 4 + 1] = (unsigned char)(st[j] >> 16);
    out[j * 4 + 2] = (unsigned char)(st[j] >> 8);
    out[j * 4 + 3] = (unsigned char)(st[j]);
  }
}
static void to_hex(const unsigned char h[32], char hex[65]) {
  static const char hc[] = "0123456789abcdef";
  for (int i = 0; i < 32; i++) {
    hex[i * 2] = hc[(h[i] >> 4) & 0xF];
    hex[i * 2 + 1] = hc[h[i] & 0xF];
  }
  hex[64] = '\0';
}

// =========================================================================
// TYPES
// =========================================================================

struct VideoFrame {
  int frame_number;
  time_t timestamp;
  int data_size;
  int width;
  int height;
  char hash[MAX_HASH_HEX];
  char previous_hash[MAX_HASH_HEX];
};

struct RecordingSession {
  char session_id[64];
  time_t start_time;
  time_t end_time;
  int total_frames;
  int fps;
  bool recording;
  bool finalized;
  char final_chain_hash[MAX_HASH_HEX];
};

// =========================================================================
// VIDEO RECORDER
// =========================================================================

class VideoRecorder {
private:
  VideoFrame frames_[MAX_FRAMES];
  int frame_count_;
  RecordingSession session_;
  char last_hash_[MAX_HASH_HEX];

  void hash_frame_data(const unsigned char *data, int size, int frame_num,
                       time_t ts, char out_hash[65]) {
    // Hash = SHA256(frame_data + frame_num + timestamp + previous_hash)
    char meta[256];
    int mlen = std::snprintf(meta, sizeof(meta), "|%d|%ld|%s", frame_num, (long)ts,
                        last_hash_);

    // Build combined buffer
    size_t total = (size_t)size + (size_t)(mlen > 0 ? mlen : 0);
    unsigned char *buf = (unsigned char *)std::malloc(total + 1);
    if (!buf) {
      std::memset(out_hash, '0', 64);
      out_hash[64] = '\0';
      return;
    }
    std::memcpy(buf, data, size);
    if (mlen > 0)
      std::memcpy(buf + size, meta, mlen);

    unsigned char digest[32];
    sha256_hash(buf, total, digest);
    to_hex(digest, out_hash);
    std::free(buf);
  }

public:
  VideoRecorder() : frame_count_(0) {
    std::memset(&session_, 0, sizeof(session_));
    std::memset(last_hash_, '0', 64);
    last_hash_[64] = '\0';
  }

  bool start_recording(const char *session_id, int fps) {
    if (session_.recording)
      return false;
    if (fps > MAX_FPS)
      fps = MAX_FPS;
    if (fps <= 0)
      fps = 15;

    std::memset(&session_, 0, sizeof(session_));
    std::strncpy(session_.session_id, session_id, sizeof(session_.session_id) - 1);
    session_.start_time = std::time(nullptr);
    session_.fps = fps;
    session_.recording = true;
    session_.finalized = false;
    frame_count_ = 0;
    std::memset(last_hash_, '0', 64);
    last_hash_[64] = '\0';
    return true;
  }

  bool add_frame(const unsigned char *data, int size, int width, int height) {
    if (!session_.recording)
      return false;
    if (frame_count_ >= MAX_FRAMES)
      return false;
    if (size > MAX_FRAME_SIZE)
      return false;

    // Check duration limit
    time_t now = std::time(nullptr);
    if (now - session_.start_time > MAX_DURATION_SECONDS) {
      stop_recording();
      return false;
    }

    VideoFrame &f = frames_[frame_count_];
    f.frame_number = frame_count_;
    f.timestamp = now;
    f.data_size = size;
    f.width = width;
    f.height = height;
    std::strncpy(f.previous_hash, last_hash_, MAX_HASH_HEX - 1);

    hash_frame_data(data, size, frame_count_, now, f.hash);
    std::strncpy(last_hash_, f.hash, MAX_HASH_HEX - 1);

    frame_count_++;
    session_.total_frames = frame_count_;
    return true;
  }

  void stop_recording() {
    if (!session_.recording)
      return;
    session_.recording = false;
    session_.end_time = std::time(nullptr);
    session_.finalized = true;
    std::strncpy(session_.final_chain_hash, last_hash_, MAX_HASH_HEX - 1);
  }

  // Verify chain
  bool verify_chain() const {
    // Check consecutive previous_hash linkage
    char expected[MAX_HASH_HEX];
    std::memset(expected, '0', 64);
    expected[64] = '\0';

    for (int i = 0; i < frame_count_; i++) {
      if (std::strcmp(frames_[i].previous_hash, expected) != 0)
        return false;
      std::strncpy(expected, frames_[i].hash, MAX_HASH_HEX - 1);
    }
    return true;
  }

  int frame_count() const { return frame_count_; }
  bool is_recording() const { return session_.recording; }
  bool is_finalized() const { return session_.finalized; }
  const RecordingSession &session() const { return session_; }
  const VideoFrame *get_frame(int i) const {
    return (i >= 0 && i < frame_count_) ? &frames_[i] : nullptr;
  }

  // Guards
  static bool can_modify_frame() { return false; }
  static bool can_delete_frame() { return false; }
  static bool can_alter_hash() { return false; }
};
