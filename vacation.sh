#!/bin/bash
# Parking Reminder v2.0 - Vacation Mode Helper (Host Script)
# Optional convenience script for CLI vacation mode control

set -euo pipefail

CONTAINER_NAME="parking-reminder"
VACATION_FILE="/var/lib/parking-reminder/vacation-mode"

show_usage() {
    cat << EOF
Parking Reminder - Vacation Mode Control

Usage: $0 [on|off|status]

Commands:
  on      Enable vacation mode (pause all reminders)
  off     Disable vacation mode (resume reminders)
  status  Show current vacation mode status

Examples:
  $0 on      # Enable vacation mode
  $0 off     # Disable vacation mode
  $0 status  # Check current status

Note: This script requires Docker and the parking-reminder container to be running.
      Alternatively, use the web UI at http://10.27.27.157:8085/
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
    check_container
    docker exec "$CONTAINER_NAME" touch "$VACATION_FILE"
    echo "✅ Vacation mode ENABLED"
    echo "   All parking reminders are now paused"
}

vacation_off() {
    check_container
    docker exec "$CONTAINER_NAME" rm -f "$VACATION_FILE"
    echo "🔔 Vacation mode DISABLED"
    echo "   Parking reminders will resume as scheduled"
}

vacation_status() {
    check_container
    if docker exec "$CONTAINER_NAME" test -f "$VACATION_FILE" 2>/dev/null; then
        echo "Status: 🏖️  VACATION MODE ENABLED"
        echo "        All reminders are paused"
    else
        echo "Status: 🔔 NORMAL MODE"
        echo "        Reminders are active"
    fi
}

# Main script
case "${1:-}" in
    on)
        vacation_on
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
