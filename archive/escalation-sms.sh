#!/bin/bash
# Parking Reminder v2.1.0 - SMS Escalation (REFACTORED)
# Sends SMS at 6:55pm if no acknowledgment
# Version: 2.1.0 - Code deduplication: using shared library for common functions

set -euo pipefail

# Source shared library
. /usr/local/bin/parking-lib.sh

LOG=/var/log/parking-reminder/reminder.log
VACATION_FILE=/var/lib/parking-reminder/vacation-mode
ACK_DIR=/var/lib/parking-reminder

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ESCALATION-SMS: $*" >> $LOG
}

# has_ack() function now provided by parking-lib.sh

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

# Calculate parking sides (using shared library function)
read CURRENT DESTINATION <<< "$(calculate_parking_sides)"

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
