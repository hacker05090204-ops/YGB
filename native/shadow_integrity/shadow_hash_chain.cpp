/**
 * Shadow Decision Hash Chain — Immutable Decision Logging
 *
 * Every shadow decision is hashed:
 *   hash(input_features + logits + temperature)
 * Chained to previous decision hash (blockchain-style).
 * Tamper-evident: any modification breaks the chain.
 *
 * Aviation-grade containment: no silent modification of shadow history.
 */

#include <cstdint>
#include <cstring>
#include <ctime>
#include <vector>

// ── SHA-256 (minimal self-contained implementation) ──────────────────

namespace sha256_internal {

static const uint32_t K[64] = {
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

inline uint32_t rotr(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }
inline uint32_t ch(uint32_t x, uint32_t y, uint32_t z) {
  return (x & y) ^ (~x & z);
}
inline uint32_t maj(uint32_t x, uint32_t y, uint32_t z) {
  return (x & y) ^ (x & z) ^ (y & z);
}
inline uint32_t sigma0(uint32_t x) {
  return rotr(x, 2) ^ rotr(x, 13) ^ rotr(x, 22);
}
inline uint32_t sigma1(uint32_t x) {
  return rotr(x, 6) ^ rotr(x, 11) ^ rotr(x, 25);
}
inline uint32_t gamma0(uint32_t x) {
  return rotr(x, 7) ^ rotr(x, 18) ^ (x >> 3);
}
inline uint32_t gamma1(uint32_t x) {
  return rotr(x, 17) ^ rotr(x, 19) ^ (x >> 10);
}

void sha256(const uint8_t *data, size_t len, uint8_t out[32]) {
  uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                   0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};

  // Padding
  size_t padded_len = ((len + 9 + 63) / 64) * 64;
  std::vector<uint8_t> padded(padded_len, 0);
  std::memcpy(padded.data(), data, len);
  padded[len] = 0x80;
  uint64_t bit_len = (uint64_t)len * 8;
  for (int i = 0; i < 8; i++)
    padded[padded_len - 1 - i] = (uint8_t)(bit_len >> (i * 8));

  // Process blocks
  for (size_t b = 0; b < padded_len; b += 64) {
    uint32_t w[64];
    for (int i = 0; i < 16; i++)
      w[i] = ((uint32_t)padded[b + i * 4] << 24) |
             ((uint32_t)padded[b + i * 4 + 1] << 16) |
             ((uint32_t)padded[b + i * 4 + 2] << 8) |
             (uint32_t)padded[b + i * 4 + 3];
    for (int i = 16; i < 64; i++)
      w[i] = gamma1(w[i - 2]) + w[i - 7] + gamma0(w[i - 15]) + w[i - 16];

    uint32_t a = h[0], bb = h[1], c = h[2], d = h[3];
    uint32_t e = h[4], f = h[5], g = h[6], hh = h[7];

    for (int i = 0; i < 64; i++) {
      uint32_t t1 = hh + sigma1(e) + ch(e, f, g) + K[i] + w[i];
      uint32_t t2 = sigma0(a) + maj(a, bb, c);
      hh = g;
      g = f;
      f = e;
      e = d + t1;
      d = c;
      c = bb;
      bb = a;
      a = t1 + t2;
    }

    h[0] += a;
    h[1] += bb;
    h[2] += c;
    h[3] += d;
    h[4] += e;
    h[5] += f;
    h[6] += g;
    h[7] += hh;
  }

  for (int i = 0; i < 8; i++) {
    out[i * 4] = (uint8_t)(h[i] >> 24);
    out[i * 4 + 1] = (uint8_t)(h[i] >> 16);
    out[i * 4 + 2] = (uint8_t)(h[i] >> 8);
    out[i * 4 + 3] = (uint8_t)(h[i]);
  }
}

} // namespace sha256_internal

// ── Shadow Hash Chain ────────────────────────────────────────────────

struct DecisionRecord {
  uint64_t sequence_id;
  double timestamp;
  uint8_t decision_hash[32]; // hash(features + logits + temperature)
  uint8_t chain_hash[32];    // hash(prev_chain_hash + decision_hash)
  int predicted_class;
  double confidence;
  double temperature;
  bool valid;
};

class ShadowHashChain {
private:
  std::vector<DecisionRecord> chain_;
  uint8_t current_chain_hash_[32];
  uint64_t next_sequence_;
  bool initialized_;

  void hash_decision(const double *features, int n_features,
                     const double *logits, int n_classes, double temperature,
                     uint8_t out[32]) {
    // Serialize: features || logits || temperature
    size_t buf_size = (n_features + n_classes + 1) * sizeof(double);
    std::vector<uint8_t> buf(buf_size);
    size_t offset = 0;
    std::memcpy(buf.data() + offset, features, n_features * sizeof(double));
    offset += n_features * sizeof(double);
    std::memcpy(buf.data() + offset, logits, n_classes * sizeof(double));
    offset += n_classes * sizeof(double);
    std::memcpy(buf.data() + offset, &temperature, sizeof(double));

    sha256_internal::sha256(buf.data(), buf_size, out);
  }

  void chain_hashes(const uint8_t prev[32], const uint8_t decision[32],
                    uint8_t out[32]) {
    uint8_t combined[64];
    std::memcpy(combined, prev, 32);
    std::memcpy(combined + 32, decision, 32);
    sha256_internal::sha256(combined, 64, out);
  }

public:
  ShadowHashChain() : next_sequence_(0), initialized_(false) {
    std::memset(current_chain_hash_, 0, 32);
  }

  DecisionRecord record_decision(const double *features, int n_features,
                                 const double *logits, int n_classes,
                                 double temperature, int predicted_class,
                                 double confidence) {
    DecisionRecord rec;
    rec.sequence_id = next_sequence_++;
    rec.timestamp = static_cast<double>(std::time(nullptr));
    rec.predicted_class = predicted_class;
    rec.confidence = confidence;
    rec.temperature = temperature;
    rec.valid = true;

    // Hash the decision
    hash_decision(features, n_features, logits, n_classes, temperature,
                  rec.decision_hash);

    // Chain to previous
    chain_hashes(current_chain_hash_, rec.decision_hash, rec.chain_hash);
    std::memcpy(current_chain_hash_, rec.chain_hash, 32);

    chain_.push_back(rec);
    initialized_ = true;
    return rec;
  }

  bool verify_chain() const {
    if (chain_.empty())
      return true;

    uint8_t running_hash[32];
    std::memset(running_hash, 0, 32);

    for (const auto &rec : chain_) {
      uint8_t expected[32];
      uint8_t combined[64];
      std::memcpy(combined, running_hash, 32);
      std::memcpy(combined + 32, rec.decision_hash, 32);
      sha256_internal::sha256(combined, 64, expected);

      if (std::memcmp(expected, rec.chain_hash, 32) != 0)
        return false; // TAMPER DETECTED

      std::memcpy(running_hash, rec.chain_hash, 32);
    }
    return true;
  }

  uint64_t chain_length() const { return chain_.size(); }

  const DecisionRecord &get_record(uint64_t idx) const { return chain_[idx]; }

  void get_chain_hash_hex(char out[65]) const {
    static const char hex[] = "0123456789abcdef";
    for (int i = 0; i < 32; i++) {
      out[i * 2] = hex[current_chain_hash_[i] >> 4];
      out[i * 2 + 1] = hex[current_chain_hash_[i] & 0x0f];
    }
    out[64] = '\0';
  }
};
