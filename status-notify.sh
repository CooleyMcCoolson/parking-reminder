#!/bin/bash
# Parking Reminder v2.1.1 - On-Demand Status Notification (TIME-AWARE)
# Sends parking side status to ntfy on demand
# Version: 2.1.1 - Context-aware messaging based on time of day

set -euo pipefail

# Source shared library
. /usr/local/bin/parking-lib.sh

# Use constants from shared library
LOG="$PARKING_LOG"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> $LOG
}

# Validation
for var in NTFY_SERVER NTFY_TOPIC; do
    if [ -z "${!var:-}" ]; then
        log "ERROR: $var environment variable not set"
        exit 1
    fi
done

# Sunday special case (using shared library function)
if is_sunday; then
    MSG="📅 It's Sunday! No parking moves needed today."
    CURRENT="N/A"
    DESTINATION="N/A"
else
    # Calculate sides based on day of week (using shared library function)
    read CURRENT DESTINATION <<< "$(calculate_parking_sides)"

    # Get current hour for time-aware messaging
    hour=$(date +%H)

    if [ "$hour" -lt 18 ]; then
        # Before window (midnight - 5:59pm): show future move
        MSG="📍 Currently parked on: $CURRENT side
🎯 Move to: $DESTINATION side (6-7pm window)"
    elif [ "$hour" -eq 18 ]; then
        # During window (6:00pm - 6:59pm): urgent instruction
        MSG="🚨 Park on $DESTINATION side (window closes at 7pm)"
    else
        # After window (7:00pm onwards): confirmation
        MSG="✅ You should now be parked on $DESTINATION side"
    fi
fi

# Check if auth is configured (FIXED v2.0.2: proper quoting to prevent argument injection)
USE_AUTH=false
if [ -n "${NTFY_AUTH_USER:-}" ] && [ -n "${NTFY_AUTH_PASS:-}" ]; then
    USE_AUTH=true
fi

log "INFO: Sending on-demand status notification (Current: $CURRENT, Destination: $DESTINATION)"

# Send notification with proper auth handling (FIXED v2.0.2: conditional auth to prevent argument injection)
# FIXED v2.0.4: Corrected error checking (was checking assignment, not curl exit code)
if [ "$USE_AUTH" = "true" ]; then
    if CURL_RESULT=$(curl -f -m 10 --user "${NTFY_AUTH_USER}:${NTFY_AUTH_PASS}" \
         -H "Priority: high" \
         -H "Title: Parking Status" \
         -H "Tags: information_source,car" \
         -d "$MSG" \
         "$NTFY_SERVER/$NTFY_TOPIC" 2>&1); then
        log "SUCCESS: On-demand status notification sent"
        exit 0
    else
        log "ERROR: Failed to send on-demand status notification: $CURL_RESULT"
        exit 1
    fi
else
    if CURL_RESULT=$(curl -f -m 10 \
         -H "Priority: high" \
         -H "Title: Parking Status" \
         -H "Tags: information_source,car" \
         -d "$MSG" \
         "$NTFY_SERVER/$NTFY_TOPIC" 2>&1); then
        log "SUCCESS: On-demand status notification sent"
        exit 0
    else
        log "ERROR: Failed to send on-demand status notification: $CURL_RESULT"
        exit 1
    fi
fi
