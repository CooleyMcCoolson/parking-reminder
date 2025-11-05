#!/bin/bash
# Parking Reminder v2.0.3 - SMS Escalation (FIXED)
# Sends SMS at 6:55pm if no acknowledgment
# Version: 2.0.3 - Fixed acknowledgment checking to use filename timestamps

set -euo pipefail

LOG=/var/log/parking-reminder/reminder.log
VACATION_FILE=/var/lib/parking-reminder/vacation-mode
ACK_DIR=/var/lib/parking-reminder

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ESCALATION-SMS: $*" >> $LOG
}

# Helper function to check for acknowledgment files
# FIXED v2.0.3: Use filename timestamp parsing (consistent with reminder.sh)
has_ack() {
    local ack_type="$1"
    local current_timestamp=$(date +%s)
    local max_age=14400  # 4 hours in seconds

    # Find all ack files for this type
    for ack_file in "$ACK_DIR"/ack-${ack_type}.*; do
        [ -f "$ack_file" ] || continue

        # Extract timestamp from filename (format: ack-TYPE.TIMESTAMP)
        local file_timestamp=$(basename "$ack_file" | cut -d. -f2)

        # Validate timestamp is a number
        if ! [[ "$file_timestamp" =~ ^[0-9]+$ ]]; then
            log "WARNING: Invalid ack file format: $ack_file"
            continue
        fi

        # Check if timestamp is within max age
        local age=$((current_timestamp - file_timestamp))
        if [ "$age" -le "$max_age" ] && [ "$age" -ge 0 ]; then
            log "DEBUG: Found valid ack file: $ack_type (age: ${age}s)"
            return 0  # Found valid acknowledgment
        fi
    done

    return 1  # No valid acknowledgment found
}

# Vacation mode check
if [ -f "$VACATION_FILE" ]; then
    log "INFO: Vacation mode enabled, skipping SMS escalation"
    exit 0
fi

# Check if user has acknowledged
if has_ack "gotit" || has_ack "nothome" || has_ack "moved" || has_ack "done"; then
    log "INFO: User has acknowledged, no SMS escalation needed"
    exit 0
fi

# Calculate parking sides
day=$(LC_ALL=C date +%u)
if [ "$day" -eq 1 ] || [ "$day" -eq 3 ] || [ "$day" -eq 5 ]; then
    CURRENT="AWAY"
    DESTINATION="HOUSE"
else
    CURRENT="HOUSE"
    DESTINATION="AWAY"
fi

# Check Twilio configuration
if [ -z "${TWILIO_ACCOUNT_SID:-}" ] || [ -z "${TWILIO_AUTH_TOKEN:-}" ] || \
   [ -z "${TWILIO_FROM_PHONE:-}" ] || [ -z "${TWILIO_TO_PHONE:-}" ]; then
    log "WARNING: Twilio not configured, SMS escalation disabled"
    exit 0
fi

log "WARNING: No acknowledgment detected, sending SMS"

SMS_BODY="🚨 PARKING ALERT: You have 5 minutes to move car from $CURRENT to $DESTINATION side! No acknowledgment received."

# Send SMS via Twilio with retry logic (FIXED: added retries like ntfy)
MAX_RETRIES=3
for attempt in 1 2 3; do
    SMS_RESPONSE=$(curl -s -X POST "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID/Messages.json" \
        --data-urlencode "From=$TWILIO_FROM_PHONE" \
        --data-urlencode "To=$TWILIO_TO_PHONE" \
        --data-urlencode "Body=$SMS_BODY" \
        -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN")

    if echo "$SMS_RESPONSE" | grep -q '"status"'; then
        log "SUCCESS: SMS sent via Twilio (attempt $attempt/$MAX_RETRIES)"

        # Send failsafe notification if configured
        if [ -n "${NTFY_FAILSAFE_TOPIC:-}" ]; then
            curl -s -m 5 \
                 -H "Priority: urgent" \
                 -H "Title: SMS ESCALATION SENT" \
                 -d "No acknowledgment received! SMS sent. Car needs to move: $CURRENT → $DESTINATION" \
                 "https://ntfy.sh/$NTFY_FAILSAFE_TOPIC" > /dev/null 2>&1 || true
            log "INFO: Failsafe notification sent to cloud ntfy.sh"
        fi
        exit 0
    else
        log "WARNING: SMS failed (attempt $attempt/$MAX_RETRIES): $SMS_RESPONSE"
        [ $attempt -lt $MAX_RETRIES ] && sleep 2
    fi
done

log "ERROR: SMS failed after $MAX_RETRIES attempts"
exit 1
