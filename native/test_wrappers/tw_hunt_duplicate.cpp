#include "../hunt_guard/hunt_duplicate_guard.cpp"
extern "C" bool test_hunt_duplicate_guard() {
  return hunt_guard::HuntDuplicateGuard::run_tests();
}
