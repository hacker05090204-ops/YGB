#include "../runtime_cert_monitor/freeze_invalidator.cpp"
extern "C" bool test_freeze_invalidator() {
  return runtime_cert_monitor::FreezeInvalidator::run_tests();
}
