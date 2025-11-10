#!/bin/bash
# Parking Reminder v2.1.2 - With smart acknowledgment buttons (BUGFIX)
# Version: 2.1.2 - Fixed "Got it!" button acknowledgment logic

set -euo pipefail

# Source shared library
. /usr/local/bin/parking-lib.sh

LOG=/var/log/parking-reminder/reminder.log
LOCK_DIR=/var/run/parking-reminder-lock
VACATION_FILE=/var/lib/parking-reminder/vacation-mode
ACK_DIR=/var/lib/parking-reminder

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> $LOG
}

# Atomic lock with stale lock cleanup (FIXED v2.0.2: handles crashes properly)
LOCK_PID_FILE="$LOCK_DIR/pid"
MAX_LOCK_AGE=600  # 10 minutes - if lock is older, it's stale

# Check for stale lock
if [ -d "$LOCK_DIR" ]; then
    if [ -f "$LOCK_PID_FILE" ]; then
        LOCK_PID=$(cat "$LOCK_PID_FILE" 2>/dev/null || echo "")
        LOCK_AGE=$(($(date +%s) - $(stat -c %Y "$LOCK_PID_FILE" 2>/dev/null || echo 0)))

        # Clean up if process doesn't exist OR lock is older than MAX_LOCK_AGE
        if [ -n "$LOCK_PID" ] && ! kill -0 "$LOCK_PID" 2>/dev/null; then
            log "WARNING: Cleaning stale lock (PID $LOCK_PID no longer exists)"
            rm -rf "$LOCK_DIR"
        elif [ "$LOCK_AGE" -gt "$MAX_LOCK_AGE" ]; then
            log "WARNING: Cleaning stale lock (age: ${LOCK_AGE}s > ${MAX_LOCK_AGE}s)"
            rm -rf "$LOCK_DIR"
        else
            log "WARNING: Lock exists, another instance running (PID $LOCK_PID)"
            exit 1
        fi
    else
        # Lock dir exists but no PID file - definitely stale
        log "WARNING: Cleaning malformed lock (no PID file)"
        rm -rf "$LOCK_DIR"
    fi
fi

# Create new lock
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    log "ERROR: Failed to create lock directory"
    exit 1
fi
echo $$ > "$LOCK_PID_FILE"
trap "rm -rf $LOCK_DIR" EXIT

# FIXED v2.0.2: Cleanup moved to separate cron job (cleanup-acks.sh at 3am daily)
# This ensures cleanup happens even during vacations/Sundays

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

# FIXED v2.0.2: Re-validate WEBHOOK_BASE_URL to prevent JSON injection
if ! echo "$WEBHOOK_BASE_URL" | grep -Eq '^https?://[a-zA-Z0-9.-]+(:[0-9]+)?$'; then
    log "ERROR: WEBHOOK_BASE_URL has invalid format: $WEBHOOK_BASE_URL"
    exit 1
fi
if echo "$WEBHOOK_BASE_URL" | grep -q '["{}]'; then
    log "ERROR: WEBHOOK_BASE_URL contains invalid characters (quotes or braces)"
    exit 1
fi

# Force C locale for consistent date handling (FIXED)
day=$(LC_ALL=C date +%u)
hour=$(LC_ALL=C date +%H)
minute=$(LC_ALL=C date +%M)
current_time="$hour$minute"

# FIXED v2.0.2: Validate time format before arithmetic operations
if ! [[ "$current_time" =~ ^[0-9]{4}$ ]]; then
    log "ERROR: Invalid time format: '$current_time' (expected HHMM)"
    exit 1
fi
if ! [[ "$day" =~ ^[0-9]$ ]]; then
    log "ERROR: Invalid day format: '$day' (expected 1-7)"
    exit 1
fi

# Sunday check (using shared library function)
if is_sunday; then
    log "INFO: Sunday detected, no reminders"
    exit 0
fi

# Calculate sides (using shared library function)
read CURRENT DESTINATION <<< "$(calculate_parking_sides)"

# Check if auth is configured (FIXED v2.0.2: proper quoting to prevent argument injection)
USE_AUTH=false
if [ -n "${NTFY_AUTH_USER:-}" ] && [ -n "${NTFY_AUTH_PASS:-}" ]; then
    USE_AUTH=true
fi

# has_ack() function now provided by parking-lib.sh

# Determine notification based on time and state
# FIXED: Use arithmetic comparison to handle times correctly
# FIXED v2.0.3: Corrected time windows to be precise (not 2 minutes early)
if [ $((10#$current_time)) -ge 1745 ] && [ $((10#$current_time)) -le 1747 ]; then
    # 5:45pm - First warning
    log "INFO: 5:45pm reminder window (current time: $current_time)"
    # Skip if user clicked "Got it!" or "Not home"
    if has_ack "nothome" || has_ack "gotit"; then
        log "INFO: User already acknowledged 5:45pm reminder, skipping"
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

elif [ $((10#$current_time)) -ge 1800 ] && [ $((10#$current_time)) -le 1802 ]; then
    # 6:00pm - Urgent
    log "INFO: 6:00pm reminder window (current time: $current_time)"
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

elif [ $((10#$current_time)) -ge 1845 ] && [ $((10#$current_time)) -le 1847 ]; then
    # 6:45pm - Last call
    log "INFO: 6:45pm reminder window (current time: $current_time)"
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
    # FIXED v2.0.2: Conditional auth to prevent argument injection from unquoted variables
    if [ "$USE_AUTH" = "true" ]; then
        CURL_RESULT=$(curl -f -m 10 --user "${NTFY_AUTH_USER}:${NTFY_AUTH_PASS}" \
             -H "Priority: $PRIORITY" \
             -H "Title: Parking Reminder" \
             -H "Tags: $TAGS" \
             -H "Actions: $ACTIONS" \
             -d "$MSG" \
             "$NTFY_SERVER/$NTFY_TOPIC" 2>&1)
    else
        CURL_RESULT=$(curl -f -m 10 \
             -H "Priority: $PRIORITY" \
             -H "Title: Parking Reminder" \
             -H "Tags: $TAGS" \
             -H "Actions: $ACTIONS" \
             -d "$MSG" \
             "$NTFY_SERVER/$NTFY_TOPIC" 2>&1)
    fi

    if [ $? -eq 0 ]; then
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
