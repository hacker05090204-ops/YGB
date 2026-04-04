#include "../data_freshness/curriculum_scheduler.cpp"
extern "C" bool test_curriculum_scheduler() {
  return data_freshness::CurriculumScheduler::run_tests();
}
