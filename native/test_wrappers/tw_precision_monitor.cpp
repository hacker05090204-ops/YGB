#include "../runtime_cert_monitor/precision_monitor.cpp"
extern "C" bool test_precision_monitor() {
  return runtime_cert_monitor::PostCertPrecisionMonitor::run_tests();
}
