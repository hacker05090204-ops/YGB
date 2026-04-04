#include "../hunt_guard/hunt_precision_guard.cpp"
extern "C" bool test_hunt_precision_guard() {
  return hunt_guard::HuntPrecisionGuard::run_tests();
}
