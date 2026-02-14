/*
 * hash_chain.cpp — Evidence-Specific Hash Chain
 *
 * Generic append-only hash chain for evidence artifacts.
 * Each entry: data hash + previous chain hash + timestamp.
 * No modification, no deletion, tamper detection.
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

// =========================================================================
// CONSTANTS
// =========================================================================

static constexpr int MAX_CHAIN_ENTRIES = 50000;
static constexpr int MAX_HASH_HEX = 65;
static constexpr int MAX_LABEL = 128;

// =========================================================================
// SHA256 (inline)
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
static void sha256_hash(const unsigned char *d, size_t len,
                        unsigned char out[32]) {
  unsigned int st[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  unsigned char blk[64];
  size_t bl = 0;
  for (size_t i = 0; i < len; i++) {
    blk[bl++] = d[i];
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

enum class EvidenceType {
  VIDEO_FRAME,
  SCREENSHOT,
  HTTP_CAPTURE,
  DOM_SNAPSHOT,
  REPLAY_STEP,
  REPORT_DRAFT,
  MANIFEST
};

struct ChainEntry {
  int sequence;
  time_t timestamp;
  EvidenceType type;
  char data_hash[MAX_HASH_HEX];  // Hash of the artifact itself
  char chain_hash[MAX_HASH_HEX]; // SHA256(data_hash + previous_chain_hash +
                                 // timestamp)
  char prev_chain_hash[MAX_HASH_HEX];
  char label[MAX_LABEL];
};

// =========================================================================
// EVIDENCE HASH CHAIN
// =========================================================================

class EvidenceHashChain {
private:
  ChainEntry entries_[MAX_CHAIN_ENTRIES];
  int entry_count_;
  char last_chain_hash_[MAX_HASH_HEX];
  bool tampered_;

public:
  EvidenceHashChain() : entry_count_(0), tampered_(false) {
    std::memset(entries_, 0, sizeof(entries_));
    std::memset(last_chain_hash_, '0', 64);
    last_chain_hash_[64] = '\0';
  }

  bool append(EvidenceType type, const char *data_hash, const char *label) {
    if (tampered_)
      return false;
    if (entry_count_ >= MAX_CHAIN_ENTRIES)
      return false;

    ChainEntry &e = entries_[entry_count_];
    e.sequence = entry_count_;
    e.timestamp = std::time(nullptr);
    e.type = type;
    std::strncpy(e.data_hash, data_hash, MAX_HASH_HEX - 1);
    std::strncpy(e.prev_chain_hash, last_chain_hash_, MAX_HASH_HEX - 1);
    std::strncpy(e.label, label ? label : "", MAX_LABEL - 1);

    // chain_hash = SHA256(data_hash + prev_chain_hash + timestamp)
    char buf[256];
    int len = std::snprintf(buf, sizeof(buf), "%s|%s|%ld", data_hash,
                       last_chain_hash_, (long)e.timestamp);
    unsigned char digest[32];
    sha256_hash((const unsigned char *)buf, len > 0 ? (size_t)len : 0, digest);
    to_hex(digest, e.chain_hash);

    std::strncpy(last_chain_hash_, e.chain_hash, MAX_HASH_HEX - 1);
    entry_count_++;
    return true;
  }

  bool verify() {
    char expected[MAX_HASH_HEX];
    std::memset(expected, '0', 64);
    expected[64] = '\0';

    for (int i = 0; i < entry_count_; i++) {
      if (std::strcmp(entries_[i].prev_chain_hash, expected) != 0) {
        tampered_ = true;
        return false;
      }

      // Recompute chain hash
      char buf[256];
      int len = std::snprintf(buf, sizeof(buf), "%s|%s|%ld", entries_[i].data_hash,
                         expected, (long)entries_[i].timestamp);
      unsigned char digest[32];
      sha256_hash((const unsigned char *)buf, len > 0 ? (size_t)len : 0,
                  digest);
      char recomputed[MAX_HASH_HEX];
      to_hex(digest, recomputed);

      if (std::strcmp(entries_[i].chain_hash, recomputed) != 0) {
        tampered_ = true;
        return false;
      }
      std::strncpy(expected, entries_[i].chain_hash, MAX_HASH_HEX - 1);
    }
    return true;
  }

  int entry_count() const { return entry_count_; }
  bool is_tampered() const { return tampered_; }
  const char *last_hash() const { return last_chain_hash_; }
  const ChainEntry *get_entry(int i) const {
    return (i >= 0 && i < entry_count_) ? &entries_[i] : nullptr;
  }

  // Guards
  static bool can_modify_entry() { return false; }
  static bool can_delete_entry() { return false; }
  static bool can_reset_chain() { return false; }
};
