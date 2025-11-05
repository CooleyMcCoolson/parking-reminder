#!/bin/bash
# Parking Reminder v2.0.4 - On-Demand Status Notification (FIXED)
# Sends parking side status to ntfy on demand
# Version: 2.0.4 - Fixed critical error checking bug ($? was checking assignment, not curl)

set -euo pipefail

LOG=/var/log/parking-reminder/reminder.log

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

# Force C locale for consistent date handling (FIXED)
day=$(LC_ALL=C date +%u)

# Sunday special case
if [ "$day" -eq 7 ]; then
    MSG="📅 It's Sunday! No parking moves needed today."
    CURRENT="N/A"
    DESTINATION="N/A"
else
    # Calculate sides based on day of week
    if [ "$day" -eq 1 ] || [ "$day" -eq 3 ] || [ "$day" -eq 5 ]; then
        CURRENT="AWAY"
        DESTINATION="HOUSE"
    else
        CURRENT="HOUSE"
        DESTINATION="AWAY"
    fi

    MSG="📍 Currently parked on: $CURRENT side
🎯 Move to: $DESTINATION side (6-7pm window)"
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
