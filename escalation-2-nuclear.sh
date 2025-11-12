#!/bin/bash
# Parking Reminder v2.2.0 - Nuclear Escalation (ntfy-only)
# Sends THREE max-priority notifications at 7:00pm if no acknowledgment
# Notifications fire 20 seconds apart to force multiple alert cycles
# Version: 2.2.0 - Replaced Twilio phone call with triple notification barrage

set -euo pipefail

# Source shared library
. /usr/local/bin/parking-lib.sh

LOG=/var/log/parking-reminder/reminder.log
VACATION_FILE=/var/lib/parking-reminder/vacation-mode
ACK_DIR=/var/lib/parking-reminder

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ESCALATION-NUCLEAR: $*" >> $LOG
}

# Helper function to send a single notification
# Args: $1=title, $2=message, $3=attempt_number
# FIXED v2.2.0: Removed eval, use -f flag, conditional auth execution
send_notification() {
    local title="$1"
    local message="$2"
    local attempt_num="$3"

    # Construct webhook URL
    local webhook_base="${WEBHOOK_BASE_URL:-http://localhost:8085}"

    # Send notification with conditional authentication (FIXED: no eval, capture errors)
    local curl_output
    if [ -n "${NTFY_AUTH_USER:-}" ] && [ -n "${NTFY_AUTH_PASS:-}" ]; then
        if curl_output=$(curl -f -s -m 10 --user "${NTFY_AUTH_USER}:${NTFY_AUTH_PASS}" \
            -H "Title: $title" \
            -H "Priority: 5" \
            -H "Tags: rotating_light,fire,sos,warning" \
            -H "Actions: view, I MOVED IT, $webhook_base/ack/done, clear=true; view, Not home, $webhook_base/ack/nothome, clear=true" \
            -d "$message" \
            "$NTFY_SERVER/$NTFY_TOPIC" 2>&1); then
            log "SUCCESS: Nuclear notification $attempt_num/3 sent"
            return 0
        else
            log "WARNING: Nuclear notification $attempt_num/3 failed (with auth): ${curl_output:-no error output}"
            return 1
        fi
    else
        # No authentication
        if curl_output=$(curl -f -s -m 10 \
            -H "Title: $title" \
            -H "Priority: 5" \
            -H "Tags: rotating_light,fire,sos,warning" \
            -H "Actions: view, I MOVED IT, $webhook_base/ack/done, clear=true; view, Not home, $webhook_base/ack/nothome, clear=true" \
            -d "$message" \
            "$NTFY_SERVER/$NTFY_TOPIC" 2>&1); then
            log "SUCCESS: Nuclear notification $attempt_num/3 sent"
            return 0
        else
            log "WARNING: Nuclear notification $attempt_num/3 failed (no auth): ${curl_output:-no error output}"
            return 1
        fi
    fi
}

# Vacation mode check
if [ -f "$VACATION_FILE" ]; then
    log "INFO: Vacation mode enabled, skipping nuclear escalation"
    exit 0
fi

# Check if user has acknowledged
if has_ack "gotit" || has_ack "nothome" || has_ack "moved" || has_ack "done"; then
    log "INFO: User has acknowledged, no nuclear escalation needed"
    exit 0
fi

# Calculate parking sides (using shared library function)
read CURRENT DESTINATION <<< "$(calculate_parking_sides)"

# Validate environment
if [ -z "${NTFY_SERVER:-}" ] || [ -z "${NTFY_TOPIC:-}" ]; then
    log "ERROR: NTFY_SERVER or NTFY_TOPIC not configured"
    exit 1
fi

# Validate parking sides calculated correctly
if [ -z "$CURRENT" ] || [ -z "$DESTINATION" ]; then
    log "ERROR: Failed to calculate parking sides (CURRENT='$CURRENT', DESTINATION='$DESTINATION')"
    exit 1
fi

log "CRITICAL: No acknowledgment detected, initiating NUCLEAR ESCALATION (3x notifications)"

# Track success/failure counts (FIXED v2.2.0: accurate reporting)
SUCCESS_COUNT=0
TOTAL_ATTEMPTS=3

# === FIRST NOTIFICATION - WARNING ===
TITLE_1="🔔 FINAL WARNING - WINDOW CLOSING"
MESSAGE_1="⚠️  STILL NO ACKNOWLEDGMENT

🚗 Move car IMMEDIATELY:
   $CURRENT side → $DESTINATION side

⏰ Parking window closes NOW!
🎫 Ticket risk is HIGH!"

if send_notification "$TITLE_1" "$MESSAGE_1" 1; then
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
fi
sleep 20  # 20 second delay

# Check again for acknowledgment (user might have responded to first notification)
if has_ack "gotit" || has_ack "nothome" || has_ack "moved" || has_ack "done"; then
    log "INFO: User acknowledged after 1st nuclear notification, stopping barrage (sent: $SUCCESS_COUNT/1)"
    exit 0
fi

# === SECOND NOTIFICATION - PANIC ===
TITLE_2="🚨 YOU'RE GETTING A TICKET"
MESSAGE_2="💥 PARKING WINDOW HAS CLOSED

🚗 Car must be on $DESTINATION side
📍 Currently on: $CURRENT side

🎫 ENFORCEMENT IS ACTIVE
⚠️  MOVE CAR NOW TO AVOID TICKET"

if send_notification "$TITLE_2" "$MESSAGE_2" 2; then
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
fi
sleep 20  # 20 second delay

# Check again for acknowledgment
if has_ack "gotit" || has_ack "nothome" || has_ack "moved" || has_ack "done"; then
    log "INFO: User acknowledged after 2nd nuclear notification, stopping barrage (sent: $SUCCESS_COUNT/2)"
    exit 0
fi

# === THIRD NOTIFICATION - FINAL CALL ===
TITLE_3="☎️ WAKE UP - FINAL ALERT"
MESSAGE_3="🔥 THIS IS THE THIRD ALERT

🚗 $CURRENT → $DESTINATION SIDE
🎫 TICKET INCOMING IF NOT MOVED

⏰ Window closed at 7:00pm
🚨 TAKE ACTION NOW"

if send_notification "$TITLE_3" "$MESSAGE_3" 3; then
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
fi

# Calculate failure count
FAILURE_COUNT=$((TOTAL_ATTEMPTS - SUCCESS_COUNT))

# Send failsafe notification after completing barrage (FIXED: priority 5 not 'urgent')
if [ -n "${NTFY_FAILSAFE_TOPIC:-}" ]; then
    curl -s -m 5 \
         -H "Priority: 5" \
         -H "Title: NUCLEAR ESCALATION COMPLETE" \
         -d "Triple notification barrage sent (7:00pm). Successful: $SUCCESS_COUNT/3. No acknowledgment received. Car needs to move: $CURRENT → $DESTINATION" \
         "https://ntfy.sh/$NTFY_FAILSAFE_TOPIC" > /dev/null 2>&1 || true
    log "INFO: Failsafe notification sent to cloud ntfy.sh"
fi

# Log accurate results (FIXED v2.2.0: report actual success/failure)
if [ $SUCCESS_COUNT -eq $TOTAL_ATTEMPTS ]; then
    log "COMPLETE: Nuclear escalation barrage complete (sent: $SUCCESS_COUNT/$TOTAL_ATTEMPTS, failed: 0)"
    exit 0
elif [ $SUCCESS_COUNT -gt 0 ]; then
    log "PARTIAL: Nuclear escalation barrage complete (sent: $SUCCESS_COUNT/$TOTAL_ATTEMPTS, failed: $FAILURE_COUNT)"
    exit 0
else
    log "FAILED: Nuclear escalation barrage FAILED (sent: 0/$TOTAL_ATTEMPTS, failed: $TOTAL_ATTEMPTS)"
    exit 1
fi
