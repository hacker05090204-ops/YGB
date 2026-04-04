#include "../data_freshness/dataset_entropy_monitor.cpp"
extern "C" bool test_dataset_entropy_monitor() {
  return data_freshness::DatasetEntropyMonitor::run_tests();
}
