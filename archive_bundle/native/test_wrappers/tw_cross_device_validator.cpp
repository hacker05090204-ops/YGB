#include "../determinism/cross_device_validator.cpp"
extern "C" bool test_cross_device_validator() {
  return determinism::CrossDeviceValidator::run_tests();
}
