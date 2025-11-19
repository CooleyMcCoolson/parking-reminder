#!/bin/bash
# Vacation Mode Library with Auto-Expiration
# v2.3.0 - Prevents forgotten vacation mode → parking ticket

set -euo pipefail

# Vacation mode with expiration support
# File format: EXPIRY_TIMESTAMP (Unix timestamp)
# If file is empty or missing timestamp, assume infinite (backward compatible)

is_vacation_mode() {
    local vacation_file="${PARKING_VACATION_FILE:-/var/lib/parking-reminder/vacation-mode}"

    if [ ! -f "$vacation_file" ]; then
        return 1  # Not in vacation mode
    fi

    # Read expiry timestamp (if exists)
    local expiry_timestamp
    if expiry_timestamp=$(cat "$vacation_file" 2>/dev/null) && [ -n "$expiry_timestamp" ]; then
        # Validate timestamp is numeric
        if [[ "$expiry_timestamp" =~ ^[0-9]+$ ]]; then
            local current_timestamp=$(date +%s)

            if [ "$current_timestamp" -gt "$expiry_timestamp" ]; then
                # Vacation mode expired - remove file and log
                if declare -f log >/dev/null 2>&1; then
                    log "INFO: Vacation mode expired (was until $(date -d @$expiry_timestamp)), resuming reminders"
                fi
                rm -f "$vacation_file"
                return 1  # Expired, not in vacation mode
            else
                # Still valid
                if declare -f log >/dev/null 2>&1; then
                    log "INFO: Vacation mode active until $(date -d @$expiry_timestamp)"
                fi
                return 0  # In vacation mode
            fi
        fi
    fi

    # File exists but no valid timestamp - assume infinite (backward compatible)
    if declare -f log >/dev/null 2>&1; then
        log "INFO: Vacation mode active (no expiration)"
    fi
    return 0
}

enable_vacation_mode() {
    local duration_days="${1:-7}"  # Default 7 days
    local vacation_file="${PARKING_VACATION_FILE:-/var/lib/parking-reminder/vacation-mode}"

    local expiry_timestamp=$(($(date +%s) + (duration_days * 86400)))
    echo "$expiry_timestamp" > "$vacation_file"

    echo "✓ Vacation mode enabled until $(date -d @$expiry_timestamp '+%Y-%m-%d %H:%M')"
}

disable_vacation_mode() {
    local vacation_file="${PARKING_VACATION_FILE:-/var/lib/parking-reminder/vacation-mode}"
    rm -f "$vacation_file"
    echo "✓ Vacation mode disabled"
}

vacation_status() {
    local vacation_file="${PARKING_VACATION_FILE:-/var/lib/parking-reminder/vacation-mode}"

    if [ ! -f "$vacation_file" ]; then
        echo "Vacation mode: DISABLED"
        return 1
    fi

    local expiry_timestamp
    if expiry_timestamp=$(cat "$vacation_file" 2>/dev/null) && [ -n "$expiry_timestamp" ]; then
        if [[ "$expiry_timestamp" =~ ^[0-9]+$ ]]; then
            local current_timestamp=$(date +%s)
            if [ "$current_timestamp" -gt "$expiry_timestamp" ]; then
                echo "Vacation mode: EXPIRED (was until $(date -d @$expiry_timestamp))"
                return 1
            else
                local remaining=$((expiry_timestamp - current_timestamp))
                local days=$((remaining / 86400))
                echo "Vacation mode: ENABLED until $(date -d @$expiry_timestamp '+%Y-%m-%d %H:%M') ($days days remaining)"
                return 0
            fi
        fi
    fi

    echo "Vacation mode: ENABLED (no expiration)"
    return 0
}
