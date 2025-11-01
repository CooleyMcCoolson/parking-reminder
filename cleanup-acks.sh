#!/bin/bash
# Parking Reminder v2.0.2 - Acknowledgment File Cleanup
# Runs daily to clean up stale acknowledgment files
# FIXED v2.0.2: Separate cron job ensures cleanup even during vacations/Sundays

set -euo pipefail

LOG=/var/log/parking-reminder/reminder.log
ACK_DIR=/var/lib/parking-reminder

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] CLEANUP: $*" >> $LOG
}

# Clean old acknowledgment files (>4 hours old)
# Parse timestamps from filename for accurate cleanup
current_timestamp=$(date +%s)
max_age=14400  # 4 hours in seconds
cleaned=0

for ack_file in "$ACK_DIR"/ack-*.* 2>/dev/null; do
    [ -f "$ack_file" ] || continue

    file_timestamp=$(basename "$ack_file" | cut -d. -f2)

    # Validate timestamp is a number
    if [[ "$file_timestamp" =~ ^[0-9]+$ ]]; then
        age=$((current_timestamp - file_timestamp))
        if [ "$age" -gt "$max_age" ]; then
            rm -f "$ack_file" && cleaned=$((cleaned + 1))
        fi
    else
        # Invalid format - remove it
        log "WARNING: Removing malformed ack file: $(basename $ack_file)"
        rm -f "$ack_file" && cleaned=$((cleaned + 1))
    fi
done

if [ "$cleaned" -gt 0 ]; then
    log "INFO: Cleaned $cleaned stale acknowledgment file(s)"
else
    log "INFO: No stale acknowledgment files to clean"
fi

exit 0
