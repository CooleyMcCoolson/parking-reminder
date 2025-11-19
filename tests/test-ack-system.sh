#!/bin/bash
# Comprehensive Ack System Test Suite
# 42 test cases covering all edge cases identified by expert reviews

set -euo pipefail

TEST_DIR="/tmp/parking-test-$$"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Set environment variables BEFORE sourcing library (to override readonly variables)
export PARKING_ACK_DIR="$TEST_DIR/acks"
export PARKING_LOG="$TEST_DIR/test.log"
export PARKING_ACK_MAX_AGE=14400

# Source shared library (will use env vars set above)
. /usr/local/bin/parking-lib.sh 2>/dev/null || . "$SCRIPT_DIR/../parking-lib.sh"

ACK_DIR="$PARKING_ACK_DIR"
mkdir -p "$ACK_DIR"

TESTS_PASSED=0
TESTS_FAILED=0

# Test helper functions
assert_true() {
    local description="$1"
    local command="$2"

    if eval "$command"; then
        echo "✓ PASS: $description"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo "✗ FAIL: $description"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
}

assert_false() {
    local description="$1"
    local command="$2"

    if ! eval "$command"; then
        echo "✓ PASS: $description"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo "✗ FAIL: $description"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
}

# Test Suite 1: Basic Ack File Creation and Detection
echo "=== Test Suite 1: Basic Ack Creation ==="

# Test 1: Create fresh ack, should be found
touch "$ACK_DIR/ack-gotit.$(date +%s)"
assert_true "Test 1: Fresh ack file is found" "has_ack gotit"
rm -f "$ACK_DIR"/ack-*

# Test 2: No ack file, should not be found
assert_false "Test 2: No ack file returns false" "has_ack gotit"

# Test 3: Expired ack (5 hours old), should not be found
old_timestamp=$(($(date +%s) - 18000))
touch "$ACK_DIR/ack-gotit.$old_timestamp"
assert_false "Test 3: Expired ack (5h) is rejected" "has_ack gotit"
rm -f "$ACK_DIR"/ack-*

# Test 4: Ack at expiration boundary (exactly 4 hours), should be found
boundary_timestamp=$(($(date +%s) - 14400))
touch "$ACK_DIR/ack-gotit.$boundary_timestamp"
assert_true "Test 4: Ack at 4h boundary is valid" "has_ack gotit"
rm -f "$ACK_DIR"/ack-*

# Test 5: Multiple ack files, newest valid should match
touch "$ACK_DIR/ack-gotit.$(($(date +%s) - 18000))"  # Expired
touch "$ACK_DIR/ack-gotit.$(date +%s)"  # Valid
assert_true "Test 5: Multiple files, finds valid one" "has_ack gotit"
rm -f "$ACK_DIR"/ack-*

echo ""

# Test Suite 2: Clock Skew and Time Edge Cases
echo "=== Test Suite 2: Clock Skew ==="

# Test 6: Future timestamp (5 min ahead) - should be accepted with tolerance
future_timestamp=$(($(date +%s) + 300))
touch "$ACK_DIR/ack-gotit.$future_timestamp"
assert_true "Test 6: Future ack (5m) accepted with tolerance" "has_ack gotit"
rm -f "$ACK_DIR"/ack-*

# Test 7: Far future timestamp (1 hour ahead) - should be rejected
far_future=$(($(date +%s) + 3600))
touch "$ACK_DIR/ack-gotit.$far_future"
assert_false "Test 7: Far future ack (1h) is rejected" "has_ack gotit"
rm -f "$ACK_DIR"/ack-*

echo ""

# Test Suite 3: Malformed Filenames
echo "=== Test Suite 3: Malformed Files ==="

# Test 8: Invalid timestamp (non-numeric)
touch "$ACK_DIR/ack-gotit.invalid"
assert_false "Test 8: Non-numeric timestamp rejected" "has_ack gotit"
rm -f "$ACK_DIR"/ack-*

# Test 9: Missing timestamp
touch "$ACK_DIR/ack-gotit"
assert_false "Test 9: Missing timestamp rejected" "has_ack gotit"
rm -f "$ACK_DIR"/ack-*

# Test 10: Extra file extensions
touch "$ACK_DIR/ack-gotit.$(date +%s).extra"
assert_false "Test 10: Extra extensions are skipped" "has_ack gotit"
rm -f "$ACK_DIR"/ack-*

echo ""

# Test Suite 4: Different Ack Types
echo "=== Test Suite 4: Ack Type Isolation ==="

# Test 11: gotit ack doesn't match nothome
touch "$ACK_DIR/ack-gotit.$(date +%s)"
assert_false "Test 11: gotit ack doesn't match nothome" "has_ack nothome"
rm -f "$ACK_DIR"/ack-*

# Test 12: Multiple types, each matches correctly
touch "$ACK_DIR/ack-gotit.$(date +%s)"
touch "$ACK_DIR/ack-nothome.$(date +%s)"
touch "$ACK_DIR/ack-moved.$(date +%s)"
assert_true "Test 12a: gotit ack found" "has_ack gotit"
assert_true "Test 12b: nothome ack found" "has_ack nothome"
assert_true "Test 12c: moved ack found" "has_ack moved"
assert_false "Test 12d: done ack not found" "has_ack done"
rm -f "$ACK_DIR"/ack-*

echo ""

# Test Suite 5: Parking Side Calculation
echo "=== Test Suite 5: Parking Side Logic ==="

# Test 13-19: Test each day of the week
for day in 1 2 3 4 5 6 7; do
    # Override get_day_of_week for testing
    get_day_of_week() { echo $day; }
    export -f get_day_of_week

    calculate_parking_sides

    case $day in
        1|3|5)  # Mon/Wed/Fri
            assert_true "Test $((12 + day)): Day $day has AWAY→HOUSE" \
                '[ "$CURRENT_SIDE" = "AWAY" ] && [ "$DESTINATION_SIDE" = "HOUSE" ]'
            ;;
        2|4|6)  # Tue/Thu/Sat
            assert_true "Test $((12 + day)): Day $day has HOUSE→AWAY" \
                '[ "$CURRENT_SIDE" = "HOUSE" ] && [ "$DESTINATION_SIDE" = "AWAY" ]'
            ;;
        7)  # Sunday
            assert_true "Test $((12 + day)): Sunday is Sunday" "is_sunday"
            ;;
    esac
done

# Restore original function
unset -f get_day_of_week
. /usr/local/bin/parking-lib.sh 2>/dev/null || . ../parking-lib.sh

echo ""

# Test Suite 6: Concurrent Access
echo "=== Test Suite 6: Concurrent Access ==="

# Test 20: Multiple processes creating acks simultaneously
(
    for i in {1..5}; do
        (
            timestamp=$(date +%s)
            touch "$ACK_DIR/ack-concurrent.$timestamp.$i"
        ) &
    done
    wait
)
count=$(ls "$ACK_DIR"/ack-concurrent.* 2>/dev/null | wc -l)
assert_true "Test 20: Concurrent ack creation (created $count files)" '[ "$count" -ge 1 ]'
rm -f "$ACK_DIR"/ack-*

echo ""

# Test Suite 7: Boundary Conditions
echo "=== Test Suite 7: Boundary Conditions ==="

# Test 21: Ack created exactly at expiration time (14400 seconds ago)
exact_boundary=$(($(date +%s) - 14400))
touch "$ACK_DIR/ack-boundary.$exact_boundary"
assert_true "Test 21: Exact 4h boundary is valid" "has_ack boundary"
rm -f "$ACK_DIR"/ack-*

# Test 22: Ack created 1 second past expiration (14401 seconds ago)
past_boundary=$(($(date +%s) - 14401))
touch "$ACK_DIR/ack-boundary.$past_boundary"
assert_false "Test 22: 1s past 4h boundary is expired" "has_ack boundary"
rm -f "$ACK_DIR"/ack-*

# Test 23: Very old ack (1 week ago)
very_old=$(($(date +%s) - 604800))
touch "$ACK_DIR/ack-ancient.$very_old"
assert_false "Test 23: Week-old ack is expired" "has_ack ancient"
rm -f "$ACK_DIR"/ack-*

echo ""

# Test Suite 8: Special Characters and Edge Cases
echo "=== Test Suite 8: Special Characters ==="

# Test 24: Ack type with uppercase (should not match)
touch "$ACK_DIR/ack-GOTIT.$(date +%s)"
assert_false "Test 24: Uppercase ack type not found" "has_ack gotit"
rm -f "$ACK_DIR"/ack-*

# Test 25: Negative timestamp (should be rejected)
touch "$ACK_DIR/ack-negative.-12345"
assert_false "Test 25: Negative timestamp rejected" "has_ack negative"
rm -f "$ACK_DIR"/ack-*

# Test 26: Zero timestamp (Unix epoch)
touch "$ACK_DIR/ack-epoch.0"
assert_false "Test 26: Epoch timestamp (1970) is expired" "has_ack epoch"
rm -f "$ACK_DIR"/ack-*

# Test 27: Float timestamp (with decimal)
touch "$ACK_DIR/ack-float.123456.789"
assert_false "Test 27: Float timestamp rejected" "has_ack float"
rm -f "$ACK_DIR"/ack-*

echo ""

# Test Suite 9: Directory and Permission Issues
echo "=== Test Suite 9: Directory Handling ==="

# Test 28: Empty directory
rm -f "$ACK_DIR"/*
assert_false "Test 28: Empty directory returns false" "has_ack missing"

# Test 29: Directory with only wrong type
touch "$ACK_DIR/ack-wrongtype.$(date +%s)"
assert_false "Test 29: Wrong ack type not found" "has_ack correcttype"
rm -f "$ACK_DIR"/ack-*

# Test 30: Mixed valid and invalid files
touch "$ACK_DIR/ack-valid.$(date +%s)"
touch "$ACK_DIR/ack-valid.invalid"
touch "$ACK_DIR/random-file.txt"
assert_true "Test 30: Valid file found among invalid ones" "has_ack valid"
rm -f "$ACK_DIR"/*

echo ""

# Test Suite 10: Timestamp Parsing Robustness
echo "=== Test Suite 10: Timestamp Parsing ==="

# Test 31: Multiple dots in filename
touch "$ACK_DIR/ack-test.$(date +%s).extra.stuff"
assert_false "Test 31: Multiple dots cause rejection" "has_ack test"
rm -f "$ACK_DIR"/ack-*

# Test 32: Very long timestamp (overflow)
touch "$ACK_DIR/ack-overflow.99999999999999999999"
assert_false "Test 32: Overflow timestamp rejected" "has_ack overflow"
rm -f "$ACK_DIR"/ack-*

# Test 33: Leading zeros in timestamp
valid_ts=$(date +%s)
touch "$ACK_DIR/ack-zeros.0000$valid_ts"
assert_false "Test 33: Leading zeros cause mismatch" "has_ack zeros"
rm -f "$ACK_DIR"/ack-*

# Test 34: Whitespace in timestamp
touch "$ACK_DIR/ack-space. $(date +%s)"
assert_false "Test 34: Whitespace in timestamp rejected" "has_ack space"
rm -f "$ACK_DIR"/ack-*

echo ""

# Test Suite 11: Real-World Scenarios
echo "=== Test Suite 11: Real-World Scenarios ==="

# Test 35: User clicks "Got it!" multiple times rapidly
ts1=$(date +%s)
sleep 1
ts2=$(date +%s)
sleep 1
ts3=$(date +%s)
touch "$ACK_DIR/ack-gotit.$ts1"
touch "$ACK_DIR/ack-gotit.$ts2"
touch "$ACK_DIR/ack-gotit.$ts3"
assert_true "Test 35: Multiple rapid acks, newest is found" "has_ack gotit"
rm -f "$ACK_DIR"/ack-*

# Test 36: User changes mind (different ack types at different times)
touch "$ACK_DIR/ack-gotit.$(($(date +%s) - 1000))"  # Old gotit
touch "$ACK_DIR/ack-nothome.$(date +%s)"  # Recent nothome
assert_true "Test 36a: Old gotit found" "has_ack gotit"
assert_true "Test 36b: Recent nothome found" "has_ack nothome"
rm -f "$ACK_DIR"/ack-*

# Test 37: System clock jumps backward (file in future)
future=$(($(date +%s) + 120))
touch "$ACK_DIR/ack-clockjump.$future"
assert_true "Test 37: Future ack accepted (2m tolerance)" "has_ack clockjump"
rm -f "$ACK_DIR"/ack-*

# Test 38: Stale acks from previous day
yesterday=$(($(date +%s) - 86400))
touch "$ACK_DIR/ack-yesterday.$yesterday"
assert_false "Test 38: Yesterday's ack is expired" "has_ack yesterday"
rm -f "$ACK_DIR"/ack-*

echo ""

# Test Suite 12: Performance and Scalability
echo "=== Test Suite 12: Performance ==="

# Test 39: Many stale files (100), find one valid
for i in {1..100}; do
    touch "$ACK_DIR/ack-stale.$(($(date +%s) - 20000 - i))"
done
touch "$ACK_DIR/ack-stale.$(date +%s)"
start_time=$(date +%s%N)
has_ack stale
end_time=$(date +%s%N)
duration=$(( (end_time - start_time) / 1000000 ))  # Convert to milliseconds
assert_true "Test 39: Find valid among 100 stale files (${duration}ms)" "[ $duration -lt 1000 ]"
rm -f "$ACK_DIR"/ack-*

# Test 40: Large directory (1000 files of various types)
for i in {1..250}; do
    touch "$ACK_DIR/ack-perf1.$(($(date +%s) - 20000 - i))"
    touch "$ACK_DIR/ack-perf2.$(($(date +%s) - 20000 - i))"
    touch "$ACK_DIR/ack-perf3.$(($(date +%s) - 20000 - i))"
    touch "$ACK_DIR/random-file-$i.txt"
done
touch "$ACK_DIR/ack-target.$(date +%s)"
start_time=$(date +%s%N)
has_ack target
end_time=$(date +%s%N)
duration=$(( (end_time - start_time) / 1000000 ))
assert_true "Test 40: Search in 1000-file directory (${duration}ms)" "[ $duration -lt 2000 ]"
rm -f "$ACK_DIR"/*

echo ""

# Test Suite 13: Final Integration Tests
echo "=== Test Suite 13: Integration Tests ==="

# Test 41: Complete workflow - fresh notification to ack
rm -f "$ACK_DIR"/*
assert_false "Test 41a: Start with no acks" "has_ack gotit || has_ack nothome || has_ack moved || has_ack done"
touch "$ACK_DIR/ack-gotit.$(date +%s)"
assert_true "Test 41b: After 'Got it!' click" "has_ack gotit"
touch "$ACK_DIR/ack-moved.$(date +%s)"
assert_true "Test 41c: After 'I moved it' click" "has_ack moved"
rm -f "$ACK_DIR"/*

# Test 42: Cleanup after expiration
old=$(($(date +%s) - 20000))
recent=$(date +%s)
touch "$ACK_DIR/ack-old.$old"
touch "$ACK_DIR/ack-recent.$recent"
assert_false "Test 42a: Old ack expired" "has_ack old"
assert_true "Test 42b: Recent ack valid" "has_ack recent"
rm -f "$ACK_DIR"/*

echo ""

# Cleanup and report
rm -rf "$TEST_DIR"

echo ""
echo "=== TEST RESULTS ==="
echo "Passed: $TESTS_PASSED"
echo "Failed: $TESTS_FAILED"
echo "Total:  $((TESTS_PASSED + TESTS_FAILED))"
echo ""

if [ "$TESTS_FAILED" -eq 0 ]; then
    echo "✓ ALL TESTS PASSED"
    exit 0
else
    echo "✗ SOME TESTS FAILED"
    exit 1
fi
