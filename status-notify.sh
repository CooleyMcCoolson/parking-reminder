#!/bin/bash
# Parking Reminder v2.0 - On-Demand Status Notification (FIXED)
# Sends parking side status to ntfy on demand
# Version: 2.0.1 - Security fixes

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

# Build auth for curl (FIXED: was vulnerable to command injection)
CURL_AUTH=""
if [ -n "${NTFY_AUTH_USER:-}" ] && [ -n "${NTFY_AUTH_PASS:-}" ]; then
    CURL_AUTH="--user ${NTFY_AUTH_USER}:${NTFY_AUTH_PASS}"
fi

log "INFO: Sending on-demand status notification (Current: $CURRENT, Destination: $DESTINATION)"

# Send notification with proper auth handling
if curl -f -m 10 $CURL_AUTH \
     -H "Priority: default" \
     -H "Title: Parking Status" \
     -H "Tags: information_source,car" \
     -d "$MSG" \
     "$NTFY_SERVER/$NTFY_TOPIC" > /dev/null 2>&1; then
    log "SUCCESS: On-demand status notification sent"
    exit 0
else
    log "ERROR: Failed to send on-demand status notification"
    exit 1
fi
