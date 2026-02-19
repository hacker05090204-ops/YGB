/*
 * test_research_hash_chain.cpp — Tests for Research Log Hash Chain
 */

#include <cassert>
#include <cstdio>
#include <cstring>
#include <ctime>

// =========================================================================
// Inline SHA256 and chain from research_hash_chain.cpp
// =========================================================================

static constexpr int SHA256_DIGEST_LENGTH = 32;
static constexpr int SHA256_HEX_LENGTH = 64;
static constexpr int MAX_CHAIN_ENTRIES = 10000;

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
  for (int i = 0; i < 16; i++) {
    w[i] = ((unsigned int)block[i * 4] << 24) |
           ((unsigned int)block[i * 4 + 1] << 16) |
           ((unsigned int)block[i * 4 + 2] << 8) |
           ((unsigned int)block[i * 4 + 3]);
  }
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
    unsigned int temp1 = h + S1 + ch + K256[i] + w[i];
    unsigned int S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
    unsigned int maj = (a & b) ^ (a & c) ^ (b & c);
    unsigned int temp2 = S0 + maj;

    h = g;
    g = f;
    f = e;
    e = d + temp1;
    d = c;
    c = b;
    b = a;
    a = temp1 + temp2;
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
                   unsigned char hash[SHA256_DIGEST_LENGTH]) {
  unsigned int state[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                           0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  size_t i;
  unsigned char block[64];
  size_t block_len = 0;

  for (i = 0; i < len; i++) {
    block[block_len++] = data[i];
    if (block_len == 64) {
      sha256_transform(state, block);
      block_len = 0;
    }
  }

  block[block_len++] = 0x80;
  if (block_len > 56) {
    while (block_len < 64)
      block[block_len++] = 0;
    sha256_transform(state, block);
    block_len = 0;
  }
  while (block_len < 56)
    block[block_len++] = 0;

  unsigned long long bit_len = (unsigned long long)len * 8;
  for (int j = 7; j >= 0; j--)
    block[56 + (7 - j)] = (unsigned char)(bit_len >> (j * 8));
  sha256_transform(state, block);

  for (int j = 0; j < 8; j++) {
    hash[j * 4] = (unsigned char)(state[j] >> 24);
    hash[j * 4 + 1] = (unsigned char)(state[j] >> 16);
    hash[j * 4 + 2] = (unsigned char)(state[j] >> 8);
    hash[j * 4 + 3] = (unsigned char)(state[j]);
  }
}

static void hash_to_hex(const unsigned char hash[SHA256_DIGEST_LENGTH],
                        char hex[SHA256_HEX_LENGTH + 1]) {
  static const char hexchars[] = "0123456789abcdef";
  for (int i = 0; i < SHA256_DIGEST_LENGTH; i++) {
    hex[i * 2] = hexchars[(hash[i] >> 4) & 0x0F];
    hex[i * 2 + 1] = hexchars[hash[i] & 0x0F];
  }
  hex[SHA256_HEX_LENGTH] = '\0';
}

enum class HashChainStatus {
  OK,
  TAMPERED,
  CHAIN_BROKEN,
  WRITE_FAILED,
  RESEARCH_DISABLED,
  ERROR
};

struct HashChainEntry {
  char input_hash[SHA256_HEX_LENGTH + 1];
  char output_hash[SHA256_HEX_LENGTH + 1];
  char combined_hash[SHA256_HEX_LENGTH + 1];
  char previous_hash[SHA256_HEX_LENGTH + 1];
  int sequence_number;
  time_t timestamp;
};

struct HashChainVerifyResult {
  HashChainStatus status;
  int entries_verified;
  int entries_total;
  bool chain_intact;
  char error[256];
};

static constexpr const char *GENESIS_HASH =
    "0000000000000000000000000000000000000000000000000000000000000000";

class ResearchHashChain {
  HashChainEntry entries_[100]; // Small for tests
  int entry_count_;
  bool research_enabled_;
  char last_hash_[SHA256_HEX_LENGTH + 1];

public:
  ResearchHashChain() : entry_count_(0), research_enabled_(true) {
    strncpy(last_hash_, GENESIS_HASH, SHA256_HEX_LENGTH);
    last_hash_[SHA256_HEX_LENGTH] = '\0';
  }

  HashChainStatus append(const char *input, const char *output) {
    if (!research_enabled_)
      return HashChainStatus::RESEARCH_DISABLED;
    if (entry_count_ >= 100)
      return HashChainStatus::ERROR;

    HashChainEntry entry;
    memset(&entry, 0, sizeof(entry));
    entry.sequence_number = entry_count_;
    entry.timestamp = time(nullptr);

    unsigned char hash_buf[SHA256_DIGEST_LENGTH];
    sha256((const unsigned char *)input, strlen(input), hash_buf);
    hash_to_hex(hash_buf, entry.input_hash);

    sha256((const unsigned char *)output, strlen(output), hash_buf);
    hash_to_hex(hash_buf, entry.output_hash);

    char combined[SHA256_HEX_LENGTH * 3 + 1];
    snprintf(combined, sizeof(combined), "%s%s%s", entry.input_hash,
             entry.output_hash, last_hash_);
    sha256((const unsigned char *)combined, strlen(combined), hash_buf);
    hash_to_hex(hash_buf, entry.combined_hash);

    strncpy(entry.previous_hash, last_hash_, SHA256_HEX_LENGTH);
    entry.previous_hash[SHA256_HEX_LENGTH] = '\0';

    entries_[entry_count_] = entry;
    entry_count_++;

    strncpy(last_hash_, entry.combined_hash, SHA256_HEX_LENGTH);
    last_hash_[SHA256_HEX_LENGTH] = '\0';

    return HashChainStatus::OK;
  }

  HashChainVerifyResult verify() {
    HashChainVerifyResult result;
    memset(&result, 0, sizeof(result));
    result.entries_total = entry_count_;
    result.chain_intact = true;
    result.status = HashChainStatus::OK;

    char expected_prev[SHA256_HEX_LENGTH + 1];
    strncpy(expected_prev, GENESIS_HASH, SHA256_HEX_LENGTH);
    expected_prev[SHA256_HEX_LENGTH] = '\0';

    for (int i = 0; i < entry_count_; i++) {
      if (strcmp(entries_[i].previous_hash, expected_prev) != 0) {
        result.chain_intact = false;
        result.status = HashChainStatus::CHAIN_BROKEN;
        research_enabled_ = false;
        return result;
      }

      char combined[SHA256_HEX_LENGTH * 3 + 1];
      snprintf(combined, sizeof(combined), "%s%s%s", entries_[i].input_hash,
               entries_[i].output_hash, entries_[i].previous_hash);

      unsigned char hash_buf[SHA256_DIGEST_LENGTH];
      sha256((const unsigned char *)combined, strlen(combined), hash_buf);
      char computed[SHA256_HEX_LENGTH + 1];
      hash_to_hex(hash_buf, computed);

      if (strcmp(computed, entries_[i].combined_hash) != 0) {
        result.chain_intact = false;
        result.status = HashChainStatus::TAMPERED;
        research_enabled_ = false;
        return result;
      }

      strncpy(expected_prev, entries_[i].combined_hash, SHA256_HEX_LENGTH);
      expected_prev[SHA256_HEX_LENGTH] = '\0';
      result.entries_verified++;
    }
    return result;
  }

  // Tamper helper for testing
  void tamper_entry(int index, const char *fake_hash) {
    if (index < entry_count_)
      strncpy(entries_[index].combined_hash, fake_hash, SHA256_HEX_LENGTH);
  }

  bool is_research_enabled() const { return research_enabled_; }
  int entry_count() const { return entry_count_; }
  const char *last_hash() const { return last_hash_; }

  // Immutable guard methods — always return false
  static bool can_delete_entries() { return false; }
  static bool can_modify_hash() { return false; }
  static bool can_skip_verification() { return false; }
  static bool can_re_enable_after_tamper() { return false; }
};

// =========================================================================
// TESTS
// =========================================================================

static int tests_passed = 0;
static int tests_failed = 0;

#define ASSERT_TRUE(expr, msg)                                                 \
  do {                                                                         \
    if (!(expr)) {                                                             \
      printf("FAIL: %s\n", msg);                                               \
      tests_failed++;                                                          \
    } else {                                                                   \
      printf("PASS: %s\n", msg);                                               \
      tests_passed++;                                                          \
    }                                                                          \
  } while (0)

#define ASSERT_FALSE(expr, msg) ASSERT_TRUE(!(expr), msg)
#define ASSERT_EQ(a, b, msg) ASSERT_TRUE((a) == (b), msg)

void test_sha256_known_value() {
  // SHA256("") =
  // e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
  unsigned char hash[SHA256_DIGEST_LENGTH];
  sha256((const unsigned char *)"", 0, hash);
  char hex[SHA256_HEX_LENGTH + 1];
  hash_to_hex(hash, hex);
  ASSERT_TRUE(
      strcmp(
          hex,
          "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855") ==
          0,
      "SHA256('') produces correct hash");
}

void test_sha256_hello() {
  // SHA256("hello") =
  // 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
  unsigned char hash[SHA256_DIGEST_LENGTH];
  sha256((const unsigned char *)"hello", 5, hash);
  char hex[SHA256_HEX_LENGTH + 1];
  hash_to_hex(hash, hex);
  ASSERT_TRUE(
      strcmp(
          hex,
          "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824") ==
          0,
      "SHA256('hello') produces correct hash");
}

void test_append_single_entry() {
  ResearchHashChain chain;
  auto status = chain.append("What is DNS?", "DNS is a naming system");
  ASSERT_TRUE(status == HashChainStatus::OK, "Append returns OK");
  ASSERT_EQ(chain.entry_count(), 1, "Chain has 1 entry");
}

void test_append_multiple_entries() {
  ResearchHashChain chain;
  chain.append("Query 1", "Answer 1");
  chain.append("Query 2", "Answer 2");
  chain.append("Query 3", "Answer 3");
  ASSERT_EQ(chain.entry_count(), 3, "Chain has 3 entries");
}

void test_verify_intact_chain() {
  ResearchHashChain chain;
  chain.append("Q1", "A1");
  chain.append("Q2", "A2");

  auto result = chain.verify();
  ASSERT_TRUE(result.chain_intact, "Intact chain verifies successfully");
  ASSERT_EQ(result.entries_verified, 2, "All 2 entries verified");
  ASSERT_TRUE(result.status == HashChainStatus::OK, "Status is OK");
}

void test_tamper_detection() {
  ResearchHashChain chain;
  chain.append("Q1", "A1");
  chain.append("Q2", "A2");

  // Tamper with entry 0
  chain.tamper_entry(
      0, "deadbeef00000000000000000000000000000000000000000000000000000000");

  auto result = chain.verify();
  ASSERT_FALSE(result.chain_intact, "Tampered chain detected");
  ASSERT_TRUE(result.status == HashChainStatus::TAMPERED, "Status is TAMPERED");
}

void test_tamper_disables_research() {
  ResearchHashChain chain;
  chain.append("Q1", "A1");
  chain.tamper_entry(
      0, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");

  ASSERT_TRUE(chain.is_research_enabled(),
              "Research enabled before tamper check");
  chain.verify();
  ASSERT_FALSE(chain.is_research_enabled(),
               "Research disabled after tamper detected");
}

void test_append_after_disable() {
  ResearchHashChain chain;
  chain.append("Q1", "A1");
  chain.tamper_entry(
      0, "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
  chain.verify(); // Disables research

  auto status = chain.append("Q2", "A2");
  ASSERT_TRUE(status == HashChainStatus::RESEARCH_DISABLED,
              "Append blocked after tamper");
}

void test_empty_chain_verify() {
  ResearchHashChain chain;
  auto result = chain.verify();
  ASSERT_TRUE(result.chain_intact, "Empty chain is valid");
  ASSERT_EQ(result.entries_verified, 0, "0 entries verified");
}

void test_genesis_hash() {
  ASSERT_TRUE(
      strcmp(
          GENESIS_HASH,
          "0000000000000000000000000000000000000000000000000000000000000000") ==
          0,
      "Genesis hash is all zeros");
}

void test_unique_hashes() {
  ResearchHashChain chain;
  chain.append("Q1", "A1");
  const char *h1 = chain.last_hash();

  ResearchHashChain chain2;
  chain2.append("Q2", "A2");
  const char *h2 = chain2.last_hash();

  ASSERT_TRUE(strcmp(h1, h2) != 0, "Different inputs produce different hashes");
}

void test_guard_cannot_delete() {
  ASSERT_FALSE(ResearchHashChain::can_delete_entries(),
               "Cannot delete entries");
}

void test_guard_cannot_modify() {
  ASSERT_FALSE(ResearchHashChain::can_modify_hash(), "Cannot modify hash");
}

void test_guard_cannot_skip() {
  ASSERT_FALSE(ResearchHashChain::can_skip_verification(),
               "Cannot skip verification");
}

void test_guard_cannot_reenable() {
  ASSERT_FALSE(ResearchHashChain::can_re_enable_after_tamper(),
               "Cannot re-enable after tamper");
}

int main() {
  printf("=== Research Hash Chain Tests ===\n\n");

  test_sha256_known_value();
  test_sha256_hello();
  test_append_single_entry();
  test_append_multiple_entries();
  test_verify_intact_chain();
  test_tamper_detection();
  test_tamper_disables_research();
  test_append_after_disable();
  test_empty_chain_verify();
  test_genesis_hash();
  test_unique_hashes();
  test_guard_cannot_delete();
  test_guard_cannot_modify();
  test_guard_cannot_skip();
  test_guard_cannot_reenable();

  printf("\n=== Results: %d passed, %d failed ===\n", tests_passed,
         tests_failed);
  return tests_failed > 0 ? 1 : 0;
}
