#!/usr/bin/env bash
# build_cpp_tests.sh — Build and run C++ self-tests with coverage
# Used by CI (GitHub Actions) on Linux runners
# Local use: WSL or any Linux environment with g++ and gcovr

set -e

CXX="${CXX:-g++}"
CXXFLAGS="-std=c++17 -O0 --coverage -fprofile-arcs -ftest-coverage"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OBJ_DIR="$ROOT/obj"
NATIVE_DIR="$ROOT/native"

echo "=== Building C++ test suite ==="
mkdir -p "$OBJ_DIR"

WRAPPERS=(
  "tw_precision_monitor"
  "tw_drift_monitor"
  "tw_freeze_invalidator"
  "tw_shadow_merge_validator"
  "tw_dataset_entropy"
  "tw_curriculum_scheduler"
  "tw_cross_device_validator"
  "tw_hunt_precision"
  "tw_hunt_duplicate"
  "tw_hunt_scope"
)

for w in "${WRAPPERS[@]}"; do
  echo "  Compiling $w..."
  $CXX $CXXFLAGS -c "$NATIVE_DIR/test_wrappers/$w.cpp" -o "$OBJ_DIR/$w.o"
done

echo "  Linking..."
OBJ_FILES=$(printf "$OBJ_DIR/%s.o " "${WRAPPERS[@]}")
$CXX $CXXFLAGS "$NATIVE_DIR/run_cpp_tests.cpp" $OBJ_FILES -o "$ROOT/run_cpp_tests"

echo "=== Running C++ self-tests ==="
"$ROOT/run_cpp_tests"
TEST_EXIT=$?

echo ""
echo "=== C++ Coverage Report ==="
gcovr -r "$ROOT" --filter "$NATIVE_DIR/" \
  --exclude "$NATIVE_DIR/test_wrappers/" \
  --exclude "$NATIVE_DIR/run_cpp_tests.cpp" \
  --json "$ROOT/coverage_cpp.json" \
  --print-summary

exit $TEST_EXIT
