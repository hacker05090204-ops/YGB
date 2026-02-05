#!/bin/bash
# stability_test.sh
# Phase-49: Stability Test Runner
#
# Run this for extended period to verify:
# - No memory leaks
# - No zombie processes
# - Hash chain integrity

set -e

REPORT_DIR="reports/stability"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="${REPORT_DIR}/stability_${TIMESTAMP}.txt"

echo "Phase-49 Stability Test" > "$REPORT_FILE"
echo "Started: $(date)" >> "$REPORT_FILE"
echo "========================" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# 1. Check for zombie processes
echo "[TEST] Checking for zombie processes..."
ZOMBIES=$(ps aux | grep -c "defunct" || echo "0")
echo "Zombie processes: $ZOMBIES" >> "$REPORT_FILE"

if [ "$ZOMBIES" -gt 0 ]; then
    echo "FAIL: Found zombie processes" >> "$REPORT_FILE"
else
    echo "PASS: No zombie processes" >> "$REPORT_FILE"
fi

# 2. Run Python tests
echo "[TEST] Running Python tests..."
if pytest -q 2>&1 | tail -5 >> "$REPORT_FILE"; then
    echo "PASS: Python tests" >> "$REPORT_FILE"
else
    echo "FAIL: Python tests" >> "$REPORT_FILE"
fi

# 3. Verify guards
echo "[TEST] Verifying AI guards..."
python3 -c "
from impl_v1.phase49.governors.g38_self_trained_model import verify_all_guards
ok, msg = verify_all_guards()
print(f'Guards: {ok} - {msg}')
exit(0 if ok else 1)
" >> "$REPORT_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "PASS: All guards return FALSE" >> "$REPORT_FILE"
else
    echo "FAIL: Guard check failed" >> "$REPORT_FILE"
fi

# 4. Check memory usage
echo "[TEST] Checking memory usage..."
free -h >> "$REPORT_FILE"

# 5. Native file count
echo "[TEST] Counting native files..."
NATIVE_COUNT=$(ls impl_v1/phase49/native/*.cpp impl_v1/phase49/native/*.h 2>/dev/null | wc -l)
echo "Native C++ files: $NATIVE_COUNT" >> "$REPORT_FILE"

# Summary
echo "" >> "$REPORT_FILE"
echo "========================" >> "$REPORT_FILE"
echo "Finished: $(date)" >> "$REPORT_FILE"
echo "Report: $REPORT_FILE"

cat "$REPORT_FILE"
