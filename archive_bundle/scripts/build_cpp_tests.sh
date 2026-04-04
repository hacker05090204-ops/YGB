#!/usr/bin/env bash
# build_cpp_tests.sh - Build and run C++ self-tests with coverage when possible.
# Used by CI (GitHub Actions) on Linux runners.
# On Windows-like environments without a compiler, this script can fall back to
# the checked-in run_cpp_tests.exe if the wrapper inputs are not newer.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OBJ_DIR="$ROOT/obj"
NATIVE_DIR="$ROOT/native"
PREBUILT_EXE="$ROOT/run_cpp_tests.exe"
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

find_compiler() {
  local candidate
  for candidate in "${CXX:-}" g++ clang++; do
    if [[ -n "${candidate}" ]] && command -v "${candidate}" >/dev/null 2>&1; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

collect_dependency_paths() {
  local wrapper_path wrapper_dir line include_path
  printf '%s\n' "$NATIVE_DIR/run_cpp_tests.cpp"
  for wrapper in "${WRAPPERS[@]}"; do
    wrapper_path="$NATIVE_DIR/test_wrappers/$wrapper.cpp"
    printf '%s\n' "$wrapper_path"
    wrapper_dir="$(dirname "$wrapper_path")"
    while IFS= read -r line; do
      if [[ "$line" =~ ^[[:space:]]*#include[[:space:]]+\"(\.\./[^\"]+)\" ]]; then
        include_path="${BASH_REMATCH[1]}"
        printf '%s\n' "$wrapper_dir/$include_path"
      fi
    done < "$wrapper_path"
  done
}

warn_if_prebuilt_stale() {
  local dep stale=0
  [[ -f "$PREBUILT_EXE" ]] || return 0
  while IFS= read -r dep; do
    [[ -n "$dep" ]] || continue
    if [[ "$dep" -nt "$PREBUILT_EXE" ]]; then
      if [[ $stale -eq 0 ]]; then
        echo "WARNING: Prebuilt binary may be stale relative to local sources" >&2
      fi
      stale=1
      printf 'WARNING:   newer source: %s\n' "$dep" >&2
    fi
  done < <(collect_dependency_paths | sort -u)
}

run_coverage_if_available() {
  if ! command -v gcov >/dev/null 2>&1 || ! command -v gcovr >/dev/null 2>&1; then
    echo ""
    echo "=== C++ Coverage Report ==="
    echo "Skipping coverage: gcov/gcovr not available"
    return 0
  fi

  echo ""
  echo "=== C++ Coverage Report ==="
  gcovr -r "$ROOT" --filter "$NATIVE_DIR/" \
    --exclude "$NATIVE_DIR/test_wrappers/" \
    --exclude "$NATIVE_DIR/run_cpp_tests.cpp" \
    --json "$ROOT/coverage_cpp.json" \
    --print-summary
}

CXX="$(find_compiler || true)"
CXXFLAGS="-std=c++17 -O0 --coverage -fprofile-arcs -ftest-coverage"

if [[ -n "$CXX" ]]; then
  echo "=== Building C++ test suite ==="
  mkdir -p "$OBJ_DIR"

  for w in "${WRAPPERS[@]}"; do
    echo "  Compiling $w..."
    "$CXX" $CXXFLAGS -c "$NATIVE_DIR/test_wrappers/$w.cpp" -o "$OBJ_DIR/$w.o"
  done

  echo "  Linking..."
  OBJ_FILES=$(printf "$OBJ_DIR/%s.o " "${WRAPPERS[@]}")
  "$CXX" $CXXFLAGS "$NATIVE_DIR/run_cpp_tests.cpp" $OBJ_FILES -o "$ROOT/run_cpp_tests"
  TEST_BIN="$ROOT/run_cpp_tests"
else
  if [[ -f "$PREBUILT_EXE" ]]; then
    echo "=== Using checked-in native test binary (no compiler found) ==="
    warn_if_prebuilt_stale
    if command -v powershell.exe >/dev/null 2>&1; then
      if powershell.exe -NoProfile -Command "exit 0" >/dev/null 2>&1; then
        powershell.exe -ExecutionPolicy Bypass -File "$ROOT/scripts/build_cpp_tests.ps1"
        exit $?
      fi
      echo "This bash host cannot launch powershell.exe." >&2
      echo "Run powershell -ExecutionPolicy Bypass -File .\\scripts\\build_cpp_tests.ps1 from Windows PowerShell," >&2
      echo "or install g++/clang++ for bash-native builds." >&2
      exit 1
    fi
    TEST_BIN="$PREBUILT_EXE"
  else
    echo "No supported compiler found and no prebuilt run_cpp_tests.exe is available." >&2
    exit 1
  fi
fi

echo "=== Running C++ self-tests ==="
"$TEST_BIN"
TEST_EXIT=$?

if [[ -n "$CXX" ]]; then
  run_coverage_if_available
else
  echo ""
  echo "=== C++ Coverage Report ==="
  echo "Skipping coverage: no compiler toolchain available on this machine"
fi

exit $TEST_EXIT
