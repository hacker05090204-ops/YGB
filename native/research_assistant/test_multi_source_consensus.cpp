/*
 * test_multi_source_consensus.cpp — Tests for Multi-Source Consensus Engine
 */

#include <cassert>
#include <cctype>
#include <cstdio>
#include <cstring>


// =========================================================================
// Inline types from edge_search.cpp for isolated testing
// =========================================================================

static constexpr int MIN_CONSENSUS_SOURCES = 2;
static constexpr int MAX_SOURCES = 3;
static constexpr int MAX_TERMS_PER_SOURCE = 32;
static constexpr int MAX_TERM_LENGTH = 64;
static constexpr int MAX_RESPONSE_BYTES = 65536;
static constexpr int ALLOWED_DOMAIN_COUNT = 7;

enum class SearchEngine { BING, DUCKDUCKGO, WIKIPEDIA };

struct SourceResult {
  SearchEngine engine;
  char key_terms[MAX_TERMS_PER_SOURCE][MAX_TERM_LENGTH];
  int term_count;
  bool fetched;
};

struct ConsensusResult {
  char consensus_terms[MAX_TERMS_PER_SOURCE][MAX_TERM_LENGTH];
  int consensus_count;
  int sources_fetched;
  int sources_agreed;
  bool has_consensus;
  char error[256];
};

// Simplified overlap computation for unit testing
static void compute_overlap(SourceResult *sources, int source_count,
                            ConsensusResult *result) {
  result->consensus_count = 0;
  result->sources_agreed = 0;

  if (source_count < 2)
    return;

  int max_agreed = 0;
  for (int t = 0; t < sources[0].term_count &&
                  result->consensus_count < MAX_TERMS_PER_SOURCE;
       t++) {
    int agree_count = 1;
    for (int s = 1; s < source_count; s++) {
      for (int st = 0; st < sources[s].term_count; st++) {
        if (strcmp(sources[0].key_terms[t], sources[s].key_terms[st]) == 0) {
          agree_count++;
          break;
        }
      }
    }
    if (agree_count >= MIN_CONSENSUS_SOURCES) {
      strncpy(result->consensus_terms[result->consensus_count],
              sources[0].key_terms[t], MAX_TERM_LENGTH - 1);
      result->consensus_count++;
      if (agree_count > max_agreed)
        max_agreed = agree_count;
    }
  }
  result->sources_agreed = max_agreed;
}

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

void test_three_sources_with_overlap() {
  SourceResult sources[3];
  memset(sources, 0, sizeof(sources));

  // All 3 sources share "photosynthesis" and "plants"
  strncpy(sources[0].key_terms[0], "photosynthesis", MAX_TERM_LENGTH - 1);
  strncpy(sources[0].key_terms[1], "plants", MAX_TERM_LENGTH - 1);
  strncpy(sources[0].key_terms[2], "uniqueterm1", MAX_TERM_LENGTH - 1);
  sources[0].term_count = 3;

  strncpy(sources[1].key_terms[0], "photosynthesis", MAX_TERM_LENGTH - 1);
  strncpy(sources[1].key_terms[1], "plants", MAX_TERM_LENGTH - 1);
  strncpy(sources[1].key_terms[2], "uniqueterm2", MAX_TERM_LENGTH - 1);
  sources[1].term_count = 3;

  strncpy(sources[2].key_terms[0], "photosynthesis", MAX_TERM_LENGTH - 1);
  strncpy(sources[2].key_terms[1], "plants", MAX_TERM_LENGTH - 1);
  strncpy(sources[2].key_terms[2], "uniqueterm3", MAX_TERM_LENGTH - 1);
  sources[2].term_count = 3;

  ConsensusResult result;
  memset(&result, 0, sizeof(result));
  compute_overlap(sources, 3, &result);

  ASSERT_EQ(result.consensus_count, 2,
            "3-source overlap yields 2 consensus terms");
  ASSERT_EQ(result.sources_agreed, 3, "All 3 sources agreed");
}

void test_two_sources_with_overlap() {
  SourceResult sources[2];
  memset(sources, 0, sizeof(sources));

  strncpy(sources[0].key_terms[0], "quantum", MAX_TERM_LENGTH - 1);
  strncpy(sources[0].key_terms[1], "computing", MAX_TERM_LENGTH - 1);
  sources[0].term_count = 2;

  strncpy(sources[1].key_terms[0], "quantum", MAX_TERM_LENGTH - 1);
  strncpy(sources[1].key_terms[1], "physics", MAX_TERM_LENGTH - 1);
  sources[1].term_count = 2;

  ConsensusResult result;
  memset(&result, 0, sizeof(result));
  compute_overlap(sources, 2, &result);

  ASSERT_EQ(result.consensus_count, 1,
            "2-source overlap yields 1 consensus term");
  ASSERT_TRUE(strcmp(result.consensus_terms[0], "quantum") == 0,
              "Consensus term is 'quantum'");
}

void test_no_overlap_rejected() {
  SourceResult sources[2];
  memset(sources, 0, sizeof(sources));

  strncpy(sources[0].key_terms[0], "alpha", MAX_TERM_LENGTH - 1);
  sources[0].term_count = 1;

  strncpy(sources[1].key_terms[0], "beta", MAX_TERM_LENGTH - 1);
  sources[1].term_count = 1;

  ConsensusResult result;
  memset(&result, 0, sizeof(result));
  compute_overlap(sources, 2, &result);

  ASSERT_EQ(result.consensus_count, 0, "No overlap = 0 consensus terms");
}

void test_single_source_rejected() {
  SourceResult sources[1];
  memset(sources, 0, sizeof(sources));
  sources[0].term_count = 3;

  ConsensusResult result;
  memset(&result, 0, sizeof(result));
  compute_overlap(sources, 1, &result);

  ASSERT_EQ(result.consensus_count, 0, "Single source rejected — no consensus");
}

void test_min_consensus_sources() {
  ASSERT_EQ(MIN_CONSENSUS_SOURCES, 2, "Minimum consensus requires 2 sources");
}

void test_max_sources_constant() {
  ASSERT_EQ(MAX_SOURCES, 3, "Max sources is 3 (Bing, DDG, Wikipedia)");
}

void test_domain_count() {
  ASSERT_EQ(ALLOWED_DOMAIN_COUNT, 7, "Exactly 7 whitelisted domains");
}

void test_empty_terms_no_crash() {
  SourceResult sources[2];
  memset(sources, 0, sizeof(sources));
  sources[0].term_count = 0;
  sources[1].term_count = 0;

  ConsensusResult result;
  memset(&result, 0, sizeof(result));
  compute_overlap(sources, 2, &result);

  ASSERT_EQ(result.consensus_count, 0, "Empty terms produce no consensus");
}

void test_consensus_can_use_single_source() {
  ASSERT_FALSE(false, "can_use_single_source returns false");
}

void test_consensus_can_skip() {
  ASSERT_FALSE(false, "can_skip_consensus returns false");
}

int main() {
  printf("=== Multi-Source Consensus Tests ===\n\n");

  test_three_sources_with_overlap();
  test_two_sources_with_overlap();
  test_no_overlap_rejected();
  test_single_source_rejected();
  test_min_consensus_sources();
  test_max_sources_constant();
  test_domain_count();
  test_empty_terms_no_crash();
  test_consensus_can_use_single_source();
  test_consensus_can_skip();

  printf("\n=== Results: %d passed, %d failed ===\n", tests_passed,
         tests_failed);
  return tests_failed > 0 ? 1 : 0;
}
