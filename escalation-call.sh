#!/bin/bash
# Parking Reminder v2.0.2 - Phone Call Escalation (FIXED)
# Makes phone call at 7:00pm if still no acknowledgment
# Version: 2.0.2 - Split from monolithic escalation.sh, XML escaping fixed

set -euo pipefail

LOG=/var/log/parking-reminder/reminder.log
VACATION_FILE=/var/lib/parking-reminder/vacation-mode
ACK_DIR=/var/lib/parking-reminder

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ESCALATION-CALL: $*" >> $LOG
}

# Helper function to check for acknowledgment files
has_ack() {
    local ack_type="$1"
    find "$ACK_DIR" -name "ack-${ack_type}.*" -mmin -240 2>/dev/null | grep -q .
}

# XML escape function (FIXED: prevent XML injection in TwiML)
escape_xml() {
    echo "$1" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g; s/"/\&quot;/g; s/'\''/\&apos;/g'
}

# Vacation mode check
if [ -f "$VACATION_FILE" ]; then
    log "INFO: Vacation mode enabled, skipping phone call escalation"
    exit 0
fi

# Check if user has acknowledged
if has_ack "gotit" || has_ack "nothome" || has_ack "moved" || has_ack "done"; then
    log "INFO: User acknowledged during wait period, no phone call needed"
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
    log "WARNING: Twilio not configured, phone call escalation disabled"
    exit 0
fi

log "CRITICAL: Still no acknowledgment at 7:00pm, making phone call"

# Escape variables for XML safety (FIXED)
CURRENT_SAFE=$(escape_xml "$CURRENT")
DESTINATION_SAFE=$(escape_xml "$DESTINATION")

# TwiML for voice call with properly escaped variables
TWIML="<Response><Say voice=\"alice\">Parking reminder! You need to move your car immediately from the $CURRENT_SAFE side to the $DESTINATION_SAFE side. The parking window closes at 7 PM. Move your car now!</Say><Pause length=\"2\"/><Say voice=\"alice\">I repeat: Move your car from $CURRENT_SAFE to $DESTINATION_SAFE side now!</Say></Response>"

# Make voice call via Twilio with retry logic (FIXED: added retries)
MAX_RETRIES=3
for attempt in 1 2 3; do
    CALL_RESPONSE=$(curl -s -X POST "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID/Calls.json" \
        --data-urlencode "From=$TWILIO_FROM_PHONE" \
        --data-urlencode "To=$TWILIO_TO_PHONE" \
        --data-urlencode "Twiml=$TWIML" \
        -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN")

    if echo "$CALL_RESPONSE" | grep -q '"status"'; then
        log "SUCCESS: Phone call initiated via Twilio (attempt $attempt/$MAX_RETRIES)"

        # Final failsafe notification
        if [ -n "${NTFY_FAILSAFE_TOPIC:-}" ]; then
            curl -s -m 5 \
                 -H "Priority: urgent" \
                 -H "Title: PHONE CALL ESCALATION TRIGGERED" \
                 -d "CRITICAL: No acknowledgment received! Phone call made. Car needs to move: $CURRENT → $DESTINATION" \
                 "https://ntfy.sh/$NTFY_FAILSAFE_TOPIC" > /dev/null 2>&1 || true
            log "INFO: Failsafe notification sent to cloud ntfy.sh"
        fi
        exit 0
    else
        log "WARNING: Phone call failed (attempt $attempt/$MAX_RETRIES): $CALL_RESPONSE"
        [ $attempt -lt $MAX_RETRIES ] && sleep 2
    fi
done

log "ERROR: Phone call failed after $MAX_RETRIES attempts"
exit 1
