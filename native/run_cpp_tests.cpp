/**
 * run_cpp_tests.cpp — Unified C++ Self-Test Harness
 *
 * Each module is compiled separately into its own .o file via a thin wrapper
 * that exports a test_xxx() free function. This avoids namespace collisions
 * between modules that share the same namespace (e.g. data_freshness).
 *
 * Build:
 *   scripts/build_cpp_tests.ps1
 */

#include <cstdio>

// External test functions defined in test_wrappers/*.cpp
extern "C" {
bool test_precision_monitor();
bool test_drift_monitor();
bool test_freeze_invalidator();
bool test_shadow_merge_validator();
bool test_dataset_entropy_monitor();
bool test_curriculum_scheduler();
bool test_cross_device_validator();
bool test_hunt_precision_guard();
bool test_hunt_duplicate_guard();
bool test_hunt_scope_guard();
}

struct TestResult {
  const char *name;
  bool (*fn)();
};

int main() {
  std::printf("============================================\n");
  std::printf("   YGB C++ Self-Test Suite\n");
  std::printf("============================================\n\n");

  TestResult tests[] = {
      {"precision_monitor      ", test_precision_monitor},
      {"drift_monitor          ", test_drift_monitor},
      {"freeze_invalidator     ", test_freeze_invalidator},
      {"shadow_merge_validator ", test_shadow_merge_validator},
      {"dataset_entropy_monitor", test_dataset_entropy_monitor},
      {"curriculum_scheduler   ", test_curriculum_scheduler},
      {"cross_device_validator ", test_cross_device_validator},
      {"hunt_precision_guard   ", test_hunt_precision_guard},
      {"hunt_duplicate_guard   ", test_hunt_duplicate_guard},
      {"hunt_scope_guard       ", test_hunt_scope_guard},
  };

  int total = sizeof(tests) / sizeof(tests[0]);
  int passed = 0;
  int failed = 0;

  for (int i = 0; i < total; i++) {
    bool ok = tests[i].fn();
    const char *status = ok ? "PASS" : "FAIL";
    std::printf("[%s] %s\n", status, tests[i].name);
    if (ok)
      passed++;
    else
      failed++;
  }

  std::printf("\n============================================\n");
  std::printf("  Results: %d/%d passed", passed, total);
  if (failed > 0)
    std::printf(", %d FAILED", failed);
  std::printf("\n============================================\n");

  return failed > 0 ? 1 : 0;
}
