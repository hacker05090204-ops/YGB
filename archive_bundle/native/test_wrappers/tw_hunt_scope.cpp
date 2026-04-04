#include "../hunt_guard/hunt_scope_guard.cpp"
extern "C" bool test_hunt_scope_guard() {
  return hunt_guard::HuntScopeGuard::run_tests();
}
