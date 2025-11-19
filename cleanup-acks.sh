#!/bin/bash
# Parking Reminder v2.0.2 - Acknowledgment File Cleanup
# Runs daily to clean up stale acknowledgment files
# FIXED v2.0.2: Separate cron job ensures cleanup even during vacations/Sundays

set -euo pipefail

# Source shared library for constants
. /usr/local/bin/parking-lib.sh

# Use constants from shared library
LOG="$PARKING_LOG"
ACK_DIR="$PARKING_ACK_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] CLEANUP: $*" >> $LOG
}

# Clean old acknowledgment files (>4 hours old)
# Parse timestamps from filename for accurate cleanup
current_timestamp=$(date +%s)
max_age="$PARKING_ACK_MAX_AGE"  # 4 hours in seconds (from library)
cleaned=0

log "INFO: Starting cleanup scan (max_age=${max_age}s / $((max_age/3600))h)"

for ack_file in "$ACK_DIR"/ack-*.* 2>/dev/null; do
    [ -f "$ack_file" ] || continue

    filename=$(basename "$ack_file")
    file_timestamp=$(echo "$filename" | cut -d. -f2)

    # Validate timestamp is a number
    if [[ "$file_timestamp" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
        # Handle decimal timestamps (microseconds)
        file_timestamp_int=${file_timestamp%.*}
        age=$((current_timestamp - file_timestamp_int))

        if [ "$age" -gt "$max_age" ]; then
            log "INFO: Deleting expired ack: $filename, age=${age}s ($((age/3600))h)"
            if rm -f "$ack_file" 2>/dev/null; then
                cleaned=$((cleaned + 1))
                # Extract ack type (gotit, nothome, moved, done)
                ack_type=$(echo "$filename" | cut -d- -f2 | cut -d. -f1)
                log "METRIC: ack_deleted type=$ack_type age=$age"
            else
                log "WARNING: Failed to delete: $filename"
            fi
        else
            log "DEBUG: Keeping valid ack: $filename, age=${age}s ($((age/60))m)"
        fi
    else
        # Invalid format - remove it
        log "WARNING: Removing malformed ack file: $filename (invalid timestamp)"
        if rm -f "$ack_file" 2>/dev/null; then
            cleaned=$((cleaned + 1))
            log "METRIC: ack_deleted type=malformed reason=invalid_timestamp"
        fi
    fi
done

if [ "$cleaned" -gt 0 ]; then
    log "INFO: Cleanup complete - cleaned $cleaned stale acknowledgment file(s)"
    log "METRIC: cleanup_completed files_deleted=$cleaned"
else
    log "INFO: Cleanup complete - no stale acknowledgment files to clean"
    log "METRIC: cleanup_completed files_deleted=0"
fi

exit 0
