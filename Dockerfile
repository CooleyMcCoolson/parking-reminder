FROM alpine:latest

# Install required packages (FIXED: added Python 3, removed netcat)
RUN apk add --no-cache \
    curl \
    tzdata \
    bash \
    python3 \
    findutils

# Create directories
RUN mkdir -p /var/log/parking-reminder /var/lib/parking-reminder

# Copy scripts (FIXED: ack-server.py instead of ack-server.sh, split escalation)
COPY reminder.sh /usr/local/bin/reminder.sh
COPY escalation-sms.sh /usr/local/bin/escalation-sms.sh
COPY escalation-call.sh /usr/local/bin/escalation-call.sh
COPY status-notify.sh /usr/local/bin/status-notify.sh
COPY ack-server.py /usr/local/bin/ack-server.py
COPY status.html /usr/local/share/status.html
COPY crontab /etc/crontabs/root
COPY entrypoint.sh /entrypoint.sh

# Make scripts executable
RUN chmod +x /usr/local/bin/*.sh /usr/local/bin/*.py /entrypoint.sh

# Set default timezone (can be overridden by env var)
ENV TZ=America/New_York

# Healthcheck - verify webhook server is running (FIXED: 30s interval instead of 5m)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${WEBHOOK_PORT:-8085}/health || exit 1

# Run entrypoint (starts cron + webhook server)
CMD ["/entrypoint.sh"]
