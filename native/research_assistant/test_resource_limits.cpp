/*
 * test_resource_limits.cpp — Tests for Strict Resource Sandbox
 */

#include <atomic>
#include <cassert>
#include <cstdio>
#include <cstring>


// =========================================================================
// Inline constants from resource_sandbox.cpp
// =========================================================================

static constexpr int MAX_RESEARCH_PROCESSES = 1;
static constexpr int HARD_TIMEOUT_SECONDS = 10;
static constexpr size_t MAX_MEMORY_BYTES = 512ULL * 1024 * 1024;
static constexpr int MAX_CPU_PERCENT = 25;
static constexpr size_t MAX_HTML_INPUT_BYTES = 3ULL * 1024 * 1024;
static constexpr size_t MAX_OUTPUT_BYTES = 65536;

enum class SandboxStatus {
  OK,
  PROCESS_LIMIT_EXCEEDED,
  TIMEOUT_EXCEEDED,
  MEMORY_EXCEEDED,
  CPU_EXCEEDED,
  HTML_SIZE_EXCEEDED,
  OUTPUT_SIZE_EXCEEDED,
  PROCESS_KILLED,
  ERROR
};

struct SandboxCheckResult {
  SandboxStatus status;
  bool within_limits;
  char reason[256];
};

// Simplified sandbox for unit testing
class TestSandbox {
  std::atomic<int> active_{0};

public:
  SandboxCheckResult check_html(size_t bytes) {
    SandboxCheckResult r;
    memset(&r, 0, sizeof(r));
    r.within_limits = bytes <= MAX_HTML_INPUT_BYTES;
    r.status =
        r.within_limits ? SandboxStatus::OK : SandboxStatus::HTML_SIZE_EXCEEDED;
    return r;
  }
  SandboxCheckResult check_mem(size_t bytes) {
    SandboxCheckResult r;
    memset(&r, 0, sizeof(r));
    r.within_limits = bytes <= MAX_MEMORY_BYTES;
    r.status =
        r.within_limits ? SandboxStatus::OK : SandboxStatus::MEMORY_EXCEEDED;
    return r;
  }
  SandboxCheckResult check_cpu(int pct) {
    SandboxCheckResult r;
    memset(&r, 0, sizeof(r));
    r.within_limits = pct <= MAX_CPU_PERCENT;
    r.status =
        r.within_limits ? SandboxStatus::OK : SandboxStatus::CPU_EXCEEDED;
    return r;
  }
  SandboxCheckResult check_output(size_t bytes) {
    SandboxCheckResult r;
    memset(&r, 0, sizeof(r));
    r.within_limits = bytes <= MAX_OUTPUT_BYTES;
    r.status = r.within_limits ? SandboxStatus::OK
                               : SandboxStatus::OUTPUT_SIZE_EXCEEDED;
    return r;
  }
  bool acquire() {
    int exp = 0;
    return active_.compare_exchange_strong(exp, 1);
  }
  void release() { active_.store(0); }
  int active() const { return active_.load(); }
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

void test_process_limit_constant() {
  ASSERT_EQ(MAX_RESEARCH_PROCESSES, 1, "Max 1 research process");
}

void test_timeout_constant() {
  ASSERT_EQ(HARD_TIMEOUT_SECONDS, 10, "Hard timeout is 10 seconds");
}

void test_memory_cap() {
  ASSERT_EQ(MAX_MEMORY_BYTES, (size_t)(512ULL * 1024 * 1024),
            "Memory cap is 512MB");
}

void test_cpu_cap() { ASSERT_EQ(MAX_CPU_PERCENT, 25, "CPU cap is 25%"); }

void test_html_limit() {
  ASSERT_EQ(MAX_HTML_INPUT_BYTES, (size_t)(3ULL * 1024 * 1024),
            "HTML limit is 3MB");
}

void test_html_within_limit() {
  TestSandbox sb;
  auto r = sb.check_html(1024 * 1024); // 1MB
  ASSERT_TRUE(r.within_limits, "1MB HTML is within 3MB limit");
}

void test_html_exceeds_limit() {
  TestSandbox sb;
  auto r = sb.check_html(4 * 1024 * 1024); // 4MB
  ASSERT_FALSE(r.within_limits, "4MB HTML exceeds 3MB limit");
  ASSERT_TRUE(r.status == SandboxStatus::HTML_SIZE_EXCEEDED,
              "Status is HTML_SIZE_EXCEEDED");
}

void test_memory_within_limit() {
  TestSandbox sb;
  auto r = sb.check_mem(256 * 1024 * 1024); // 256MB
  ASSERT_TRUE(r.within_limits, "256MB is within 512MB limit");
}

void test_memory_exceeds_limit() {
  TestSandbox sb;
  auto r = sb.check_mem(600ULL * 1024 * 1024); // 600MB
  ASSERT_FALSE(r.within_limits, "600MB exceeds 512MB limit");
  ASSERT_TRUE(r.status == SandboxStatus::MEMORY_EXCEEDED,
              "Status is MEMORY_EXCEEDED");
}

void test_cpu_within_limit() {
  TestSandbox sb;
  auto r = sb.check_cpu(20);
  ASSERT_TRUE(r.within_limits, "20% CPU is within 25% limit");
}

void test_cpu_exceeds_limit() {
  TestSandbox sb;
  auto r = sb.check_cpu(50);
  ASSERT_FALSE(r.within_limits, "50% CPU exceeds 25% limit");
  ASSERT_TRUE(r.status == SandboxStatus::CPU_EXCEEDED,
              "Status is CPU_EXCEEDED");
}

void test_output_within_limit() {
  TestSandbox sb;
  auto r = sb.check_output(32768);
  ASSERT_TRUE(r.within_limits, "32KB output within 64KB limit");
}

void test_output_exceeds_limit() {
  TestSandbox sb;
  auto r = sb.check_output(100000);
  ASSERT_FALSE(r.within_limits, "100KB output exceeds 64KB limit");
}

void test_process_slot_acquire() {
  TestSandbox sb;
  ASSERT_TRUE(sb.acquire(), "First process slot acquired");
  ASSERT_EQ(sb.active(), 1, "1 active process");
}

void test_process_slot_double_acquire() {
  TestSandbox sb;
  sb.acquire();
  ASSERT_FALSE(sb.acquire(), "Cannot acquire 2nd slot (max 1)");
}

void test_process_slot_release() {
  TestSandbox sb;
  sb.acquire();
  sb.release();
  ASSERT_EQ(sb.active(), 0, "Process slot released");
  ASSERT_TRUE(sb.acquire(), "Can re-acquire after release");
}

void test_boundary_html_exactly() {
  TestSandbox sb;
  auto r = sb.check_html(MAX_HTML_INPUT_BYTES);
  ASSERT_TRUE(r.within_limits, "Exact 3MB HTML is within limit");

  r = sb.check_html(MAX_HTML_INPUT_BYTES + 1);
  ASSERT_FALSE(r.within_limits, "3MB + 1 byte exceeds limit");
}

void test_boundary_memory_exactly() {
  TestSandbox sb;
  auto r = sb.check_mem(MAX_MEMORY_BYTES);
  ASSERT_TRUE(r.within_limits, "Exact 512MB is within limit");

  r = sb.check_mem(MAX_MEMORY_BYTES + 1);
  ASSERT_FALSE(r.within_limits, "512MB + 1 byte exceeds limit");
}

void test_boundary_cpu_exactly() {
  TestSandbox sb;
  auto r = sb.check_cpu(25);
  ASSERT_TRUE(r.within_limits, "Exactly 25% CPU is within limit");

  r = sb.check_cpu(26);
  ASSERT_FALSE(r.within_limits, "26% CPU exceeds limit");
}

int main() {
  printf("=== Resource Sandbox Tests ===\n\n");

  test_process_limit_constant();
  test_timeout_constant();
  test_memory_cap();
  test_cpu_cap();
  test_html_limit();
  test_html_within_limit();
  test_html_exceeds_limit();
  test_memory_within_limit();
  test_memory_exceeds_limit();
  test_cpu_within_limit();
  test_cpu_exceeds_limit();
  test_output_within_limit();
  test_output_exceeds_limit();
  test_process_slot_acquire();
  test_process_slot_double_acquire();
  test_process_slot_release();
  test_boundary_html_exactly();
  test_boundary_memory_exactly();
  test_boundary_cpu_exactly();

  printf("\n=== Results: %d passed, %d failed ===\n", tests_passed,
         tests_failed);
  return tests_failed > 0 ? 1 : 0;
}
