#include "../merge_guard/shadow_merge_validator.cpp"
extern "C" bool test_shadow_merge_validator() {
  return merge_guard::ShadowMergeValidator::run_tests();
}
