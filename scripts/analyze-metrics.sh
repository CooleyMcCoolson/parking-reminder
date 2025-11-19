#!/bin/bash
# Metrics analysis script - extract insights from logs

LOG_FILE="${1:-/var/log/parking-reminder/reminder.log}"

if [ ! -f "$LOG_FILE" ]; then
    echo "Error: Log file not found: $LOG_FILE"
    exit 1
fi

echo "=== PARKING REMINDER METRICS ANALYSIS ==="
echo "Log file: $LOG_FILE"
echo "Analysis date: $(date)"
echo ""

echo "--- Ack Creation Stats ---"
echo "Total acks created: $(grep -c "METRIC: ack_created" "$LOG_FILE" 2>/dev/null || echo 0)"
echo "  - gotit:   $(grep "METRIC: ack_created type=gotit" "$LOG_FILE" 2>/dev/null | wc -l)"
echo "  - nothome: $(grep "METRIC: ack_created type=nothome" "$LOG_FILE" 2>/dev/null | wc -l)"
echo "  - moved:   $(grep "METRIC: ack_created type=moved" "$LOG_FILE" 2>/dev/null | wc -l)"
echo "  - done:    $(grep "METRIC: ack_created type=done" "$LOG_FILE" 2>/dev/null | wc -l)"
echo ""

echo "--- Notification Stats ---"
echo "Notifications sent: $(grep -c "METRIC: notification_sent" "$LOG_FILE" 2>/dev/null || echo 0)"
echo "  - 5:45pm: $(grep "METRIC: notification_sent time=545pm" "$LOG_FILE" 2>/dev/null | wc -l)"
echo "  - 6:00pm: $(grep "METRIC: notification_sent time=600pm" "$LOG_FILE" 2>/dev/null | wc -l)"
echo "  - 6:45pm: $(grep "METRIC: notification_sent time=645pm" "$LOG_FILE" 2>/dev/null | wc -l)"
echo ""

echo "Notifications skipped: $(grep -c "METRIC: notification_skipped" "$LOG_FILE" 2>/dev/null || echo 0)"
echo "  - Due to gotit:   $(grep "METRIC: notification_skipped.*reason=ack_gotit" "$LOG_FILE" 2>/dev/null | wc -l)"
echo "  - Due to nothome: $(grep "METRIC: notification_skipped.*reason=ack_nothome" "$LOG_FILE" 2>/dev/null | wc -l)"
echo "  - Due to moved:   $(grep "METRIC: notification_skipped.*reason=ack_moved" "$LOG_FILE" 2>/dev/null | wc -l)"
echo ""

echo "Notifications failed: $(grep -c "METRIC: notification_failed" "$LOG_FILE" 2>/dev/null || echo 0)"
echo ""

echo "--- Cleanup Stats ---"
echo "Cleanup runs: $(grep -c "METRIC: cleanup_completed" "$LOG_FILE" 2>/dev/null || echo 0)"
echo "Total acks deleted: $(grep "METRIC: ack_deleted" "$LOG_FILE" 2>/dev/null | wc -l)"
echo ""

echo "--- Effectiveness Analysis ---"
total_sent=$(grep -c "METRIC: notification_sent" "$LOG_FILE" 2>/dev/null || echo 0)
total_skipped=$(grep -c "METRIC: notification_skipped" "$LOG_FILE" 2>/dev/null || echo 0)
total_scheduled=$((total_sent + total_skipped))

if [ "$total_scheduled" -gt 0 ]; then
    ack_rate=$((total_skipped * 100 / total_scheduled))
    echo "Acknowledgment rate: ${ack_rate}% ($total_skipped / $total_scheduled reminders)"
else
    echo "Acknowledgment rate: N/A (no data)"
fi
echo ""

echo "✓ Analysis complete"
