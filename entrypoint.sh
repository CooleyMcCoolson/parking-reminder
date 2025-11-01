#!/bin/bash
# Parking Reminder v2.0.2 - Container Entrypoint (FIXED)
# Starts cron daemon and webhook server in parallel
# Version: 2.0.2 - Additional security hardening and stderr logging

set -euo pipefail

LOG=/var/log/parking-reminder/reminder.log

# Ensure log directory exists
mkdir -p /var/log/parking-reminder /var/lib/parking-reminder

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Parking Reminder v2.0.2" >> $LOG

# Validate required environment variables (FIXED: added validation)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Validating configuration..." >> $LOG
MISSING_VARS=()
for var in NTFY_SERVER NTFY_TOPIC WEBHOOK_BASE_URL; do
    if [ -z "${!var:-}" ]; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    # FIXED v2.0.2: Write errors to both log and stderr for better debugging
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Missing required environment variables: ${MISSING_VARS[*]}" | tee -a $LOG >&2
    exit 1
fi

# Validate WEBHOOK_BASE_URL format (FIXED v2.0.1: prevent JSON injection)
if ! echo "$WEBHOOK_BASE_URL" | grep -Eq '^https?://[a-zA-Z0-9.-]+(:[0-9]+)?$'; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: WEBHOOK_BASE_URL has invalid format: $WEBHOOK_BASE_URL" | tee -a $LOG >&2
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Must be http(s)://hostname:port with no trailing slash or special characters" | tee -a $LOG >&2
    exit 1
fi

# Check for JSON injection characters
if echo "$WEBHOOK_BASE_URL" | grep -q '["{}]'; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: WEBHOOK_BASE_URL contains invalid characters (quotes or braces)" | tee -a $LOG >&2
    exit 1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Configuration valid" >> $LOG

# Start crond in foreground mode (alpine uses busybox crond)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting cron daemon..." >> $LOG
crond -f -l 2 &
CRON_PID=$!

# Start webhook server (FIXED: now using Python instead of insecure netcat)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting webhook server on port ${WEBHOOK_PORT:-8085}..." >> $LOG
python3 /usr/local/bin/ack-server.py &
WEBHOOK_PID=$!

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Both services started (cron PID: $CRON_PID, webhook PID: $WEBHOOK_PID)" >> $LOG

# FIXED: Use trap instead of wait -n (not available in older bash)
trap "kill $CRON_PID $WEBHOOK_PID 2>/dev/null; exit" TERM INT

# Wait for any background process to exit
wait

# If we get here, one process died - log and exit (FIXED v2.0.2: write to stderr too)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: One of the background processes died, exiting" | tee -a $LOG >&2
exit 1
