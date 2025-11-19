#!/bin/bash
# Parking Reminder v2.0 - Vacation Mode Helper (Host Script)
# Optional convenience script for CLI vacation mode control

set -euo pipefail

CONTAINER_NAME="parking-reminder"
VACATION_FILE="/var/lib/parking-reminder/vacation-mode"

show_usage() {
    cat << EOF
Parking Reminder - Vacation Mode Control (v2.3.0)

Usage: $0 [on [days]|off|status]

Commands:
  on [days]   Enable vacation mode with auto-expiration (default: 7 days)
  off         Disable vacation mode (resume reminders)
  status      Show current vacation mode status

Examples:
  $0 on           # Enable vacation mode for 7 days (default)
  $0 on 14        # Enable vacation mode for 14 days
  $0 off          # Disable vacation mode
  $0 status       # Check current status and expiration

New in v2.3.0:
  - Auto-expiration prevents forgotten vacation mode → parking ticket
  - Duration parameter allows custom vacation length
  - Backward compatible with infinite vacation mode (empty file)

Note: This script requires Docker and the parking-reminder container to be running.
      Alternatively, use the web UI at http://YOUR_SERVER_IP:8085/
EOF
}

check_container() {
    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "ERROR: Container '$CONTAINER_NAME' is not running"
        echo "Start it with: docker-compose up -d"
        exit 1
    fi
}

vacation_on() {
    local days="${1:-7}"  # Default 7 days if not specified
    check_container

    # Validate days is a positive number
    if ! [[ "$days" =~ ^[0-9]+$ ]] || [ "$days" -le 0 ]; then
        echo "ERROR: Days must be a positive number (got: '$days')"
        exit 1
    fi

    # Use vacation library function via docker exec
    docker exec "$CONTAINER_NAME" sh -c ". /usr/local/bin/vacation-lib.sh && enable_vacation_mode $days"
}

vacation_off() {
    check_container
    # Use vacation library function via docker exec
    docker exec "$CONTAINER_NAME" sh -c ". /usr/local/bin/vacation-lib.sh && disable_vacation_mode"
}

vacation_status() {
    check_container
    # Use vacation library function via docker exec
    docker exec "$CONTAINER_NAME" sh -c ". /usr/local/bin/vacation-lib.sh && vacation_status"
}

# Main script
case "${1:-}" in
    on)
        vacation_on "${2:-7}"  # Pass duration (default 7 days)
        ;;
    off)
        vacation_off
        ;;
    status)
        vacation_status
        ;;
    -h|--help|help)
        show_usage
        ;;
    *)
        echo "ERROR: Invalid command"
        echo ""
        show_usage
        exit 1
        ;;
esac
