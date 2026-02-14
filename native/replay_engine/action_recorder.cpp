/*
 * action_recorder.cpp — SHA256-Chained Hunting Step Recorder
 *
 * Records every hunting step with SHA256 chain linking.
 * Each entry: timestamp, request, response, payload, endpoint,
 *             parameter, state_delta, screenshot_hash, video_frame_hash
 */

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>


// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int MAX_STEPS = 5000;
static constexpr int MAX_FIELD_LENGTH = 1024;
static constexpr int MAX_HASH_HEX = 65; // 64 hex chars + null
static constexpr int SHA256_DIGEST_LEN = 32;

// =========================================================================
// INLINE SHA256 (from research_hash_chain.cpp pattern)
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

static void sha256_transform(unsigned int state[8],
                             const unsigned char block[64]) {
  unsigned int w[64];
  for (int i = 0; i < 16; i++)
    w[i] = ((unsigned int)block[i * 4] << 24) |
           ((unsigned int)block[i * 4 + 1] << 16) |
           ((unsigned int)block[i * 4 + 2] << 8) |
           ((unsigned int)block[i * 4 + 3]);
  for (int i = 16; i < 64; i++) {
    unsigned int s0 =
        rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
    unsigned int s1 =
        rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  unsigned int a = state[0], b = state[1], c = state[2], d = state[3];
  unsigned int e = state[4], f = state[5], g = state[6], h = state[7];
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
  state[0] += a;
  state[1] += b;
  state[2] += c;
  state[3] += d;
  state[4] += e;
  state[5] += f;
  state[6] += g;
  state[7] += h;
}

static void sha256(const unsigned char *data, size_t len,
                   unsigned char hash[32]) {
  unsigned int state[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                           0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  unsigned char block[64];
  size_t blen = 0;
  for (size_t i = 0; i < len; i++) {
    block[blen++] = data[i];
    if (blen == 64) {
      sha256_transform(state, block);
      blen = 0;
    }
  }
  block[blen++] = 0x80;
  if (blen > 56) {
    while (blen < 64)
      block[blen++] = 0;
    sha256_transform(state, block);
    blen = 0;
  }
  while (blen < 56)
    block[blen++] = 0;
  unsigned long long bits = (unsigned long long)len * 8;
  for (int j = 7; j >= 0; j--)
    block[56 + (7 - j)] = (unsigned char)(bits >> (j * 8));
  sha256_transform(state, block);
  for (int j = 0; j < 8; j++) {
    hash[j * 4] = (unsigned char)(state[j] >> 24);
    hash[j * 4 + 1] = (unsigned char)(state[j] >> 16);
    hash[j * 4 + 2] = (unsigned char)(state[j] >> 8);
    hash[j * 4 + 3] = (unsigned char)(state[j]);
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

struct HuntingStep {
  int sequence;
  time_t timestamp;
  char request[MAX_FIELD_LENGTH];
  char response[MAX_FIELD_LENGTH];
  char dom_change[MAX_FIELD_LENGTH];
  char payload[MAX_FIELD_LENGTH];
  char endpoint[MAX_FIELD_LENGTH];
  char parameter[MAX_FIELD_LENGTH];
  char state_delta[MAX_FIELD_LENGTH];
  char screenshot_hash[MAX_HASH_HEX];
  char video_frame_hash[MAX_HASH_HEX];
  char step_hash[MAX_HASH_HEX];
  char previous_hash[MAX_HASH_HEX];
};

// =========================================================================
// ACTION RECORDER
// =========================================================================

class ActionRecorder {
private:
  HuntingStep steps_[MAX_STEPS];
  int step_count_;
  char last_hash_[MAX_HASH_HEX];

  void compute_step_hash(HuntingStep &step) {
    // Hash = SHA256(all fields + previous_hash)
    char buf[MAX_FIELD_LENGTH * 8];
    int len = std::snprintf(
        buf, sizeof(buf), "%d|%ld|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s", step.sequence,
        (long)step.timestamp, step.request, step.response, step.dom_change,
        step.payload, step.endpoint, step.parameter, step.state_delta,
        step.screenshot_hash, step.video_frame_hash, step.previous_hash);
    unsigned char hash[32];
    sha256((const unsigned char *)buf, len > 0 ? (size_t)len : 0, hash);
    to_hex(hash, step.step_hash);
  }

public:
  ActionRecorder() : step_count_(0) {
    std::memset(steps_, 0, sizeof(steps_));
    std::memset(last_hash_, '0', 64);
    last_hash_[64] = '\0';
  }

  bool record_step(const char *request, const char *response,
                   const char *dom_change, const char *payload,
                   const char *endpoint, const char *parameter,
                   const char *state_delta, const char *screenshot_hash,
                   const char *video_frame_hash) {
    if (step_count_ >= MAX_STEPS)
      return false;

    HuntingStep &s = steps_[step_count_];
    s.sequence = step_count_;
    s.timestamp = std::time(nullptr);

    std::strncpy(s.request, request ? request : "", MAX_FIELD_LENGTH - 1);
    std::strncpy(s.response, response ? response : "", MAX_FIELD_LENGTH - 1);
    std::strncpy(s.dom_change, dom_change ? dom_change : "", MAX_FIELD_LENGTH - 1);
    std::strncpy(s.payload, payload ? payload : "", MAX_FIELD_LENGTH - 1);
    std::strncpy(s.endpoint, endpoint ? endpoint : "", MAX_FIELD_LENGTH - 1);
    std::strncpy(s.parameter, parameter ? parameter : "", MAX_FIELD_LENGTH - 1);
    std::strncpy(s.state_delta, state_delta ? state_delta : "",
            MAX_FIELD_LENGTH - 1);
    std::strncpy(s.screenshot_hash, screenshot_hash ? screenshot_hash : "",
            MAX_HASH_HEX - 1);
    std::strncpy(s.video_frame_hash, video_frame_hash ? video_frame_hash : "",
            MAX_HASH_HEX - 1);
    std::strncpy(s.previous_hash, last_hash_, MAX_HASH_HEX - 1);

    compute_step_hash(s);
    std::strncpy(last_hash_, s.step_hash, MAX_HASH_HEX - 1);

    step_count_++;
    return true;
  }

  int step_count() const { return step_count_; }
  const HuntingStep *get_step(int i) const {
    return (i >= 0 && i < step_count_) ? &steps_[i] : nullptr;
  }
  const char *last_hash() const { return last_hash_; }

  // Verify chain integrity
  bool verify_chain() {
    char expected_prev[MAX_HASH_HEX];
    std::memset(expected_prev, '0', 64);
    expected_prev[64] = '\0';

    for (int i = 0; i < step_count_; i++) {
      if (std::strcmp(steps_[i].previous_hash, expected_prev) != 0)
        return false;
      std::strncpy(expected_prev, steps_[i].step_hash, MAX_HASH_HEX - 1);
    }
    return true;
  }

  // Guards
  static bool can_modify_step() { return false; }
  static bool can_delete_step() { return false; }
  static bool can_reorder_steps() { return false; }
};
