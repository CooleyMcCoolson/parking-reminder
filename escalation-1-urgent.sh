#!/bin/bash
# Parking Reminder v2.2.0 - Urgent Escalation (ntfy-only)
# Sends max-priority notification at 6:55pm if no acknowledgment
# Version: 2.2.0 - Replaced Twilio SMS with ntfy priority escalation

set -euo pipefail

# Source shared library
. /usr/local/bin/parking-lib.sh

# Use constants from shared library
LOG="$PARKING_LOG"
VACATION_FILE="$PARKING_VACATION_FILE"
ACK_DIR="$PARKING_ACK_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ESCALATION-URGENT: $*" >> $LOG
}

# Source vacation library (FIXED v2.3.0: auto-expiration support)
. /usr/local/bin/vacation-lib.sh

# Vacation mode check with auto-expiration
if is_vacation_mode; then
    exit 0  # Logging handled by is_vacation_mode()
fi

# Check if user has acknowledged (check each individually for logging)
if has_ack "nothome"; then
    log "INFO: Skipping urgent escalation - 'Not home' acknowledged"
    exit 0
fi

if has_ack "gotit"; then
    log "INFO: Skipping urgent escalation - 'Got it!' acknowledged"
    exit 0
fi

if has_ack "moved"; then
    log "INFO: Skipping urgent escalation - 'I moved it' acknowledged"
    exit 0
fi

if has_ack "done"; then
    log "INFO: Skipping urgent escalation - 'Done!' acknowledged"
    exit 0
fi

log "INFO: No acknowledgments found - proceeding with urgent escalation"

# Calculate parking sides (using shared library function)
read CURRENT DESTINATION <<< "$(calculate_parking_sides)"

# Validate environment
if [ -z "${NTFY_SERVER:-}" ] || [ -z "${NTFY_TOPIC:-}" ]; then
    log "ERROR: NTFY_SERVER or NTFY_TOPIC not configured"
    exit 1
fi

log "WARNING: No acknowledgment detected, sending URGENT notification"

# Validate parking sides calculated correctly
if [ -z "$CURRENT" ] || [ -z "$DESTINATION" ]; then
    log "ERROR: Failed to calculate parking sides (CURRENT='$CURRENT', DESTINATION='$DESTINATION')"
    exit 1
fi

# Construct webhook URL
WEBHOOK_BASE="${WEBHOOK_BASE_URL:-http://localhost:8085}"

# Send max-priority notification with action buttons
NOTIFICATION_TITLE="🚨 PARKING EMERGENCY - 5 MIN LEFT"
NOTIFICATION_MESSAGE="⚠️  NO ACKNOWLEDGMENT RECEIVED
⏰ Window closes at 7:00pm

📍 Move car NOW:
   $CURRENT side → $DESTINATION side

🚗 You have 5 minutes remaining!"

# Send notification with retry logic (FIXED: no eval, use -f flag, conditional auth, capture errors)
MAX_RETRIES=3
for attempt in 1 2 3; do
    # Send with conditional authentication (FIXED: no eval, direct execution, error capture)
    CURL_OUTPUT=""
    if [ -n "${NTFY_AUTH_USER:-}" ] && [ -n "${NTFY_AUTH_PASS:-}" ]; then
        if CURL_OUTPUT=$(curl -f -s -m 10 --user "${NTFY_AUTH_USER}:${NTFY_AUTH_PASS}" \
            -H "Title: $NOTIFICATION_TITLE" \
            -H "Priority: 5" \
            -H "Tags: rotating_light,alarm,warning" \
            -H "Actions: view, I'M MOVING IT NOW, $WEBHOOK_BASE/ack/done, clear=true; view, Not home, $WEBHOOK_BASE/ack/nothome, clear=true" \
            -d "$NOTIFICATION_MESSAGE" \
            "$NTFY_SERVER/$NTFY_TOPIC" 2>&1); then

            log "SUCCESS: Urgent escalation sent (attempt $attempt/$MAX_RETRIES)"

            # Send failsafe notification if configured (FIXED: priority 5 not 'urgent')
            if [ -n "${NTFY_FAILSAFE_TOPIC:-}" ]; then
                curl -s -m 5 \
                     -H "Priority: 5" \
                     -H "Title: URGENT ESCALATION SENT" \
                     -d "No acknowledgment received! Urgent notification sent. Car needs to move: $CURRENT → $DESTINATION" \
                     "https://ntfy.sh/$NTFY_FAILSAFE_TOPIC" > /dev/null 2>&1 || true
                log "INFO: Failsafe notification sent to cloud ntfy.sh"
            fi
            exit 0
        fi
    else
        # No authentication
        if CURL_OUTPUT=$(curl -f -s -m 10 \
            -H "Title: $NOTIFICATION_TITLE" \
            -H "Priority: 5" \
            -H "Tags: rotating_light,alarm,warning" \
            -H "Actions: view, I'M MOVING IT NOW, $WEBHOOK_BASE/ack/done, clear=true; view, Not home, $WEBHOOK_BASE/ack/nothome, clear=true" \
            -d "$NOTIFICATION_MESSAGE" \
            "$NTFY_SERVER/$NTFY_TOPIC" 2>&1); then

            log "SUCCESS: Urgent escalation sent (attempt $attempt/$MAX_RETRIES)"
            exit 0
        fi
    fi

    log "WARNING: Urgent escalation failed (attempt $attempt/$MAX_RETRIES): ${CURL_OUTPUT:-no error output}"
    [ $attempt -lt $MAX_RETRIES ] && sleep 2
done

log "ERROR: Urgent escalation failed after $MAX_RETRIES attempts"
exit 1
