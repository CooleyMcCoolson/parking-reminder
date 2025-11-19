#!/bin/bash
# Manual test script for ack system validation
# Run inside container: docker exec parking-reminder /usr/local/bin/test-ack-manual.sh

set -euo pipefail

echo "=== PARKING REMINDER ACK SYSTEM MANUAL TEST ==="
echo ""

# Source library
. /usr/local/bin/parking-lib.sh || { echo "Failed to load parking-lib.sh"; exit 1; }

echo "Test 1: Create test ack file..."
timestamp=$(date +%s)
test_file="/var/lib/parking-reminder/ack-manualtest.$timestamp"
touch "$test_file"
echo "  Created: $(basename $test_file)"
ls -la "$test_file"
echo ""

echo "Test 2: Verify has_ack() finds it..."
if has_ack "manualtest"; then
    echo "  ✓ SUCCESS: has_ack() found file"
else
    echo "  ✗ FAILURE: has_ack() did not find file"
fi
echo ""

echo "Test 3: Check clock drift..."
file_mtime=$(stat -c %Y "$test_file")
current_time=$(date +%s)
drift=$((current_time - timestamp))
echo "  Created at: $timestamp ($(date -d @$timestamp))"
echo "  Current time: $current_time ($(date -d @$current_time))"
echo "  Drift: ${drift}s"
if [ "$drift" -gt 5 ]; then
    echo "  ⚠ WARNING: Significant clock drift detected"
else
    echo "  ✓ Clock appears synchronized"
fi
echo ""

echo "Test 4: Test webhook endpoint..."
if curl -s -f -X POST http://localhost:8085/ack/webhooktest >/dev/null 2>&1; then
    echo "  ✓ Webhook endpoint responding"
    if ls /var/lib/parking-reminder/ack-webhooktest.* >/dev/null 2>&1; then
        echo "  ✓ Webhook created ack file"
        ls -la /var/lib/parking-reminder/ack-webhooktest.* | tail -1
    else
        echo "  ✗ Webhook did not create file"
    fi
else
    echo "  ✗ Webhook endpoint failed"
fi
echo ""

echo "Cleanup..."
rm -f /var/lib/parking-reminder/ack-manualtest.* /var/lib/parking-reminder/ack-webhooktest.*
echo "✓ Test complete"
