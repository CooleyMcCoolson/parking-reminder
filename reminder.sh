#!/bin/bash
# Parking Reminder v2.0 - With smart acknowledgment buttons (FIXED)
# Version: 2.0.1 - Security and logic bug fixes

set -euo pipefail

LOG=/var/log/parking-reminder/reminder.log
LOCK_DIR=/var/run/parking-reminder-lock
VACATION_FILE=/var/lib/parking-reminder/vacation-mode
ACK_DIR=/var/lib/parking-reminder

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> $LOG
}

# Atomic lock using mkdir (FIXED: was non-atomic touch)
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    log "WARNING: Lock exists, another instance running"
    exit 1
fi
trap "rmdir $LOCK_DIR" EXIT

# Clean old acknowledgment files (>4 hours old)
find "$ACK_DIR" -name "ack-*.*" -mmin +240 -delete 2>/dev/null || true

# Vacation mode check
if [ -f "$VACATION_FILE" ]; then
    log "INFO: Vacation mode enabled, skipping reminders"
    exit 0
fi

# Validation
for var in NTFY_SERVER NTFY_TOPIC WEBHOOK_BASE_URL; do
    if [ -z "${!var:-}" ]; then
        log "ERROR: $var environment variable not set"
        exit 1
    fi
done

# Force C locale for consistent date handling (FIXED)
day=$(LC_ALL=C date +%u)
hour=$(LC_ALL=C date +%H)
minute=$(LC_ALL=C date +%M)
current_time="$hour$minute"

# Sunday check
if [ "$day" -eq 7 ]; then
    log "INFO: Sunday detected, no reminders"
    exit 0
fi

# Calculate sides
if [ "$day" -eq 1 ] || [ "$day" -eq 3 ] || [ "$day" -eq 5 ]; then
    CURRENT="AWAY"
    DESTINATION="HOUSE"
else
    CURRENT="HOUSE"
    DESTINATION="AWAY"
fi

# Build auth for curl (FIXED: was vulnerable to command injection)
CURL_AUTH=""
if [ -n "${NTFY_AUTH_USER:-}" ] && [ -n "${NTFY_AUTH_PASS:-}" ]; then
    CURL_AUTH="--user ${NTFY_AUTH_USER}:${NTFY_AUTH_PASS}"
fi

# Helper function to check for acknowledgment files
has_ack() {
    local ack_type="$1"
    # Check if any ack file for this type exists and is recent (<4 hours)
    find "$ACK_DIR" -name "ack-${ack_type}.*" -mmin -240 2>/dev/null | grep -q .
}

# Determine notification based on time and state
# FIXED: Use arithmetic comparison to handle times correctly
if [ $((10#$current_time)) -ge 1743 ] && [ $((10#$current_time)) -le 1747 ]; then
    # 5:45pm - First warning
    # Skip if user clicked "Not home"
    if has_ack "nothome"; then
        log "INFO: User clicked 'Not home', skipping 5:45pm reminder"
        exit 0
    fi

    MSG="⚠️ 15 minutes: Move car from $CURRENT to $DESTINATION side"
    PRIORITY="high"
    TAGS="warning,car"
    # FIXED: Use environment variable instead of hardcoded IP
    ACTIONS='[
        {"action":"view","label":"Got it!","url":"'"${WEBHOOK_BASE_URL}"'/ack/gotit","clear":true},
        {"action":"view","label":"Not home","url":"'"${WEBHOOK_BASE_URL}"'/ack/nothome","clear":true}
    ]'
    REMINDER_TYPE="545pm-warning"

elif [ $((10#$current_time)) -ge 1758 ] && [ $((10#$current_time)) -le 1802 ]; then
    # 6:00pm - Urgent
    # FIXED: Only skip if "Not home" or "Moved", NOT "Got it!"
    # "Got it!" means acknowledged but not moved yet - keep sending
    if has_ack "nothome" || has_ack "moved"; then
        log "INFO: User already acknowledged, skipping 6:00pm reminder"
        exit 0
    fi

    MSG="🚗 MOVE NOW: $CURRENT → $DESTINATION side (window closes at 7pm)"
    PRIORITY="urgent"
    TAGS="rotating_light,car"
    # FIXED: Use environment variable instead of hardcoded IP
    ACTIONS='[
        {"action":"view","label":"I moved it","url":"'"${WEBHOOK_BASE_URL}"'/ack/moved","clear":true},
        {"action":"view","label":"Not home","url":"'"${WEBHOOK_BASE_URL}"'/ack/nothome","clear":true}
    ]'
    REMINDER_TYPE="6pm-urgent"

elif [ $((10#$current_time)) -ge 1843 ] && [ $((10#$current_time)) -le 1847 ]; then
    # 6:45pm - Last call
    # Skip if "Not home" or "Moved"
    if has_ack "nothome" || has_ack "moved"; then
        log "INFO: User already acknowledged, skipping 6:45pm reminder"
        exit 0
    fi

    MSG="🚨 15 MIN LEFT: Move from $CURRENT to $DESTINATION side!"
    PRIORITY="urgent"
    TAGS="rotating_light,sos"
    # FIXED: Use environment variable instead of hardcoded IP
    ACTIONS='[
        {"action":"view","label":"Done!","url":"'"${WEBHOOK_BASE_URL}"'/ack/done","clear":true},
        {"action":"view","label":"Not home","url":"'"${WEBHOOK_BASE_URL}"'/ack/nothome","clear":true}
    ]'
    REMINDER_TYPE="645pm-lastcall"

else
    log "INFO: Current time $hour:$minute not a scheduled reminder"
    exit 0
fi

log "INFO: Sending $REMINDER_TYPE notification: $CURRENT → $DESTINATION"

# Send notification with retries
MAX_RETRIES=3
RETRY_COUNT=0
SUCCESS=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    # FIXED: Use CURL_AUTH instead of AUTH_HEADER to prevent command injection
    if curl -f -m 10 $CURL_AUTH \
         -H "Priority: $PRIORITY" \
         -H "Title: Parking Reminder" \
         -H "Tags: $TAGS" \
         -H "Actions: $ACTIONS" \
         -d "$MSG" \
         "$NTFY_SERVER/$NTFY_TOPIC" > /dev/null 2>&1; then
        log "SUCCESS: $REMINDER_TYPE notification sent"
        SUCCESS=true
        break
    else
        RETRY_COUNT=$((RETRY_COUNT + 1))
        log "WARNING: Notification failed (attempt $RETRY_COUNT/$MAX_RETRIES)"
        [ $RETRY_COUNT -lt $MAX_RETRIES ] && sleep 2
    fi
done

if [ "$SUCCESS" = false ]; then
    log "ERROR: Failed after $MAX_RETRIES attempts"

    # Failsafe: Send to cloud ntfy.sh if self-hosted failed
    if [ -n "${NTFY_FAILSAFE_TOPIC:-}" ]; then
        curl -f -m 5 \
             -H "Priority: urgent" \
             -H "Title: Parking System FAILURE" \
             -d "Self-hosted ntfy failed! Original message: $MSG" \
             "https://ntfy.sh/$NTFY_FAILSAFE_TOPIC" > /dev/null 2>&1 || true
    fi
    exit 1
fi

# Notify Uptime Kuma of successful run
if [ -n "${UPTIME_KUMA_PUSH_URL:-}" ]; then
    curl -m 5 "$UPTIME_KUMA_PUSH_URL?status=up&msg=$REMINDER_TYPE" > /dev/null 2>&1 || true
fi

exit 0
