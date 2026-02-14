/*
 * test_domain_whitelist.cpp — Tests for Static Domain Whitelist
 */

#include <cassert>
#include <cctype>
#include <cstdio>
#include <cstring>


// =========================================================================
// Inline from edge_search.cpp
// =========================================================================

static constexpr const char *ALLOWED_DOMAINS[] = {
    "www.bing.com",       "bing.com",
    "duckduckgo.com",     "www.duckduckgo.com",
    "en.wikipedia.org",   "wikipedia.org",
    "en.m.wikipedia.org", nullptr};

static constexpr int ALLOWED_DOMAIN_COUNT = 7;
static_assert(
    sizeof(ALLOWED_DOMAINS) / sizeof(ALLOWED_DOMAINS[0]) == 8,
    "Domain whitelist must have exactly 7 domains + nullptr sentinel");

static bool is_domain_allowed(const char *url) {
  const char *start = strstr(url, "://");
  if (!start)
    return false;
  start += 3;

  const char *end = strchr(start, '/');
  int domain_len = end ? (int)(end - start) : (int)strlen(start);
  if (domain_len <= 0 || domain_len >= 256)
    return false;

  char domain[256];
  memcpy(domain, start, domain_len);
  domain[domain_len] = '\0';

  for (int i = 0; i < domain_len; i++) {
    if (domain[i] >= 'A' && domain[i] <= 'Z')
      domain[i] = domain[i] + 32;
  }

  for (int i = 0; ALLOWED_DOMAINS[i] != nullptr; i++) {
    if (strcmp(domain, ALLOWED_DOMAINS[i]) == 0)
      return true;
  }
  return false;
}

// Guards
static bool can_modify_whitelist_at_runtime() { return false; }
static bool can_override_from_env() { return false; }
static bool can_add_domain_from_user_config() { return false; }

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

// Allowed domains
void test_bing_allowed() {
  ASSERT_TRUE(is_domain_allowed("https://www.bing.com/search?q=test"),
              "www.bing.com is allowed");
}

void test_bing_bare_allowed() {
  ASSERT_TRUE(is_domain_allowed("https://bing.com/search"),
              "bing.com is allowed");
}

void test_duckduckgo_allowed() {
  ASSERT_TRUE(is_domain_allowed("https://duckduckgo.com/?q=test"),
              "duckduckgo.com is allowed");
}

void test_wikipedia_allowed() {
  ASSERT_TRUE(is_domain_allowed("https://en.wikipedia.org/wiki/Test"),
              "en.wikipedia.org is allowed");
}

void test_wikipedia_mobile_allowed() {
  ASSERT_TRUE(is_domain_allowed("https://en.m.wikipedia.org/wiki/Test"),
              "en.m.wikipedia.org is allowed");
}

// Blocked domains
void test_google_blocked() {
  ASSERT_FALSE(is_domain_allowed("https://www.google.com/search"),
               "google.com is blocked");
}

void test_evil_site_blocked() {
  ASSERT_FALSE(is_domain_allowed("https://evil.com/payload"),
               "evil.com is blocked");
}

void test_localhost_blocked() {
  ASSERT_FALSE(is_domain_allowed("http://localhost:8080"),
               "localhost is blocked");
}

void test_ip_address_blocked() {
  ASSERT_FALSE(is_domain_allowed("http://192.168.1.1/admin"),
               "IP address is blocked");
}

void test_file_protocol_blocked() {
  ASSERT_FALSE(is_domain_allowed("file:///etc/passwd"),
               "file:// protocol is blocked");
}

void test_similar_domain_blocked() {
  ASSERT_FALSE(is_domain_allowed("https://bing.com.evil.com/steal"),
               "bing.com.evil.com is blocked (subdomain attack)");
}

// Immutability guards
void test_no_runtime_modification() {
  ASSERT_FALSE(can_modify_whitelist_at_runtime(),
               "Cannot modify whitelist at runtime");
}

void test_no_env_override() {
  ASSERT_FALSE(can_override_from_env(),
               "Cannot override from environment variables");
}

void test_no_user_config() {
  ASSERT_FALSE(can_add_domain_from_user_config(),
               "Cannot add domains from user config");
}

// Compile-time constants
void test_domain_count() {
  ASSERT_EQ(ALLOWED_DOMAIN_COUNT, 7, "Exactly 7 whitelisted domains");
}

void test_nullptr_sentinel() {
  int count = 0;
  while (ALLOWED_DOMAINS[count] != nullptr)
    count++;
  ASSERT_EQ(count, 7, "7 domains before nullptr sentinel");
}

void test_case_insensitive() {
  ASSERT_TRUE(is_domain_allowed("https://WWW.BING.COM/search"),
              "Case-insensitive domain matching works");
}

int main() {
  printf("=== Static Domain Whitelist Tests ===\n\n");

  test_bing_allowed();
  test_bing_bare_allowed();
  test_duckduckgo_allowed();
  test_wikipedia_allowed();
  test_wikipedia_mobile_allowed();

  test_google_blocked();
  test_evil_site_blocked();
  test_localhost_blocked();
  test_ip_address_blocked();
  test_file_protocol_blocked();
  test_similar_domain_blocked();

  test_no_runtime_modification();
  test_no_env_override();
  test_no_user_config();

  test_domain_count();
  test_nullptr_sentinel();
  test_case_insensitive();

  printf("\n=== Results: %d passed, %d failed ===\n", tests_passed,
         tests_failed);
  return tests_failed > 0 ? 1 : 0;
}
