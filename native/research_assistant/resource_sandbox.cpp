/*
 * resource_sandbox.cpp — Strict Resource Sandbox for Research Mode
 *
 * ENFORCEMENT:
 *   - Max 1 research process at a time
 *   - 10s hard timeout per query
 *   - 512MB memory cap per process
 *   - 25% CPU cap
 *   - 3MB HTML input limit
 *   - Kill process if any threshold exceeded
 */

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

#ifdef _WIN32
#include <windows.h>
#else
#include <signal.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>
#endif

// =========================================================================
// CONSTANTS — COMPILE-TIME, IMMUTABLE
// =========================================================================

static constexpr int MAX_RESEARCH_PROCESSES = 1;
static constexpr int HARD_TIMEOUT_SECONDS = 10;
static constexpr size_t MAX_MEMORY_BYTES = 512ULL * 1024 * 1024; // 512MB
static constexpr int MAX_CPU_PERCENT = 25;
static constexpr size_t MAX_HTML_INPUT_BYTES = 3ULL * 1024 * 1024; // 3MB
static constexpr size_t MAX_OUTPUT_BYTES = 65536;                  // 64KB

static_assert(MAX_RESEARCH_PROCESSES == 1,
              "Only 1 research process allowed at a time");
static_assert(HARD_TIMEOUT_SECONDS == 10, "Timeout must be exactly 10 seconds");
static_assert(MAX_MEMORY_BYTES == 536870912ULL,
              "Memory cap must be exactly 512MB");
static_assert(MAX_CPU_PERCENT == 25, "CPU cap must be exactly 25%");
static_assert(MAX_HTML_INPUT_BYTES == 3145728ULL,
              "HTML limit must be exactly 3MB");

// =========================================================================
// TYPES
// =========================================================================

enum class SandboxStatus {
  OK,
  PROCESS_LIMIT_EXCEEDED,
  TIMEOUT_EXCEEDED,
  MEMORY_EXCEEDED,
  CPU_EXCEEDED,
  HTML_SIZE_EXCEEDED,
  OUTPUT_SIZE_EXCEEDED,
  PROCESS_KILLED,
  SANDBOX_ERROR
};

struct SandboxLimits {
  int max_processes;
  int timeout_seconds;
  size_t max_memory_bytes;
  int max_cpu_percent;
  size_t max_html_bytes;
  size_t max_output_bytes;
};

struct SandboxCheckResult {
  SandboxStatus status;
  bool within_limits;
  char reason[256];
};

// =========================================================================
// RESOURCE SANDBOX
// =========================================================================

class ResearchSandbox {
private:
  std::atomic<int> active_processes_{0};
  std::atomic<bool> process_killed_{false};

public:
  ResearchSandbox() = default;

  // Get immutable limits
  static SandboxLimits get_limits() {
    return SandboxLimits{
        MAX_RESEARCH_PROCESSES, HARD_TIMEOUT_SECONDS, MAX_MEMORY_BYTES,
        MAX_CPU_PERCENT,        MAX_HTML_INPUT_BYTES, MAX_OUTPUT_BYTES,
    };
  }

  // =====================================================================
  // PRE-LAUNCH CHECKS
  // =====================================================================

  SandboxCheckResult can_spawn_process() {
    SandboxCheckResult result;
    memset(&result, 0, sizeof(result));

    int current = active_processes_.load();
    if (current >= MAX_RESEARCH_PROCESSES) {
      result.status = SandboxStatus::PROCESS_LIMIT_EXCEEDED;
      result.within_limits = false;
      snprintf(result.reason, sizeof(result.reason),
               "Process limit exceeded: %d/%d active", current,
               MAX_RESEARCH_PROCESSES);
      return result;
    }

    result.status = SandboxStatus::OK;
    result.within_limits = true;
    snprintf(result.reason, sizeof(result.reason), "Process spawn allowed");
    return result;
  }

  SandboxCheckResult check_html_size(size_t html_bytes) {
    SandboxCheckResult result;
    memset(&result, 0, sizeof(result));

    if (html_bytes > MAX_HTML_INPUT_BYTES) {
      result.status = SandboxStatus::HTML_SIZE_EXCEEDED;
      result.within_limits = false;
      snprintf(result.reason, sizeof(result.reason),
               "HTML size %zu exceeds limit %zu", html_bytes,
               MAX_HTML_INPUT_BYTES);
      return result;
    }

    result.status = SandboxStatus::OK;
    result.within_limits = true;
    snprintf(result.reason, sizeof(result.reason), "HTML size within limits");
    return result;
  }

  SandboxCheckResult check_output_size(size_t output_bytes) {
    SandboxCheckResult result;
    memset(&result, 0, sizeof(result));

    if (output_bytes > MAX_OUTPUT_BYTES) {
      result.status = SandboxStatus::OUTPUT_SIZE_EXCEEDED;
      result.within_limits = false;
      snprintf(result.reason, sizeof(result.reason),
               "Output size %zu exceeds limit %zu", output_bytes,
               MAX_OUTPUT_BYTES);
      return result;
    }

    result.status = SandboxStatus::OK;
    result.within_limits = true;
    snprintf(result.reason, sizeof(result.reason), "Output size within limits");
    return result;
  }

  SandboxCheckResult check_memory(size_t memory_bytes) {
    SandboxCheckResult result;
    memset(&result, 0, sizeof(result));

    if (memory_bytes > MAX_MEMORY_BYTES) {
      result.status = SandboxStatus::MEMORY_EXCEEDED;
      result.within_limits = false;
      snprintf(result.reason, sizeof(result.reason),
               "Memory %zu exceeds limit %zu", memory_bytes, MAX_MEMORY_BYTES);
      return result;
    }

    result.status = SandboxStatus::OK;
    result.within_limits = true;
    snprintf(result.reason, sizeof(result.reason), "Memory within limits");
    return result;
  }

  SandboxCheckResult check_cpu(int cpu_percent) {
    SandboxCheckResult result;
    memset(&result, 0, sizeof(result));

    if (cpu_percent > MAX_CPU_PERCENT) {
      result.status = SandboxStatus::CPU_EXCEEDED;
      result.within_limits = false;
      snprintf(result.reason, sizeof(result.reason),
               "CPU %d%% exceeds limit %d%%", cpu_percent, MAX_CPU_PERCENT);
      return result;
    }

    result.status = SandboxStatus::OK;
    result.within_limits = true;
    snprintf(result.reason, sizeof(result.reason), "CPU within limits");
    return result;
  }

  // =====================================================================
  // COMBINED CHECK
  // =====================================================================

  SandboxCheckResult is_within_limits(size_t html_bytes, size_t output_bytes,
                                      size_t memory_bytes, int cpu_percent) {
    SandboxCheckResult r;

    r = can_spawn_process();
    if (!r.within_limits)
      return r;

    r = check_html_size(html_bytes);
    if (!r.within_limits)
      return r;

    r = check_output_size(output_bytes);
    if (!r.within_limits)
      return r;

    r = check_memory(memory_bytes);
    if (!r.within_limits)
      return r;

    r = check_cpu(cpu_percent);
    if (!r.within_limits)
      return r;

    r.status = SandboxStatus::OK;
    r.within_limits = true;
    snprintf(r.reason, sizeof(r.reason), "All resource checks passed");
    return r;
  }

  // =====================================================================
  // PROCESS LIFECYCLE
  // =====================================================================

  bool acquire_process_slot() {
    int expected = 0;
    return active_processes_.compare_exchange_strong(expected, 1);
  }

  void release_process_slot() { active_processes_.store(0); }

  int active_process_count() const { return active_processes_.load(); }

  // =====================================================================
  // KILL ON THRESHOLD BREACH
  // =====================================================================

  void kill_process(long process_id, const char *reason) {
    process_killed_.store(true);
    fprintf(stderr, "[SANDBOX] Killing research process %ld: %s\n", process_id,
            reason);

#ifdef _WIN32
    HANDLE hProcess = OpenProcess(PROCESS_TERMINATE, FALSE, (DWORD)process_id);
    if (hProcess) {
      TerminateProcess(hProcess, 1);
      CloseHandle(hProcess);
    }
#else
    kill((pid_t)process_id, SIGKILL);
#endif

    release_process_slot();
  }

  bool was_process_killed() const { return process_killed_.load(); }

  void reset_kill_flag() { process_killed_.store(false); }

  // =====================================================================
  // GUARDS — immutable
  // =====================================================================

  static bool can_increase_process_limit() { return false; }
  static bool can_extend_timeout() { return false; }
  static bool can_increase_memory_limit() { return false; }
  static bool can_increase_cpu_limit() { return false; }
  static bool can_bypass_html_limit() { return false; }
  static bool can_modify_limits_at_runtime() { return false; }
};
