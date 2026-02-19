#include "../runtime_cert_monitor/drift_monitor.cpp"
extern "C" bool test_drift_monitor() {
  return runtime_cert_monitor::PostCertDriftMonitor::run_tests();
}
