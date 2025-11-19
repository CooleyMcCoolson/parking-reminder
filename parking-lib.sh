#!/bin/bash
# Parking Reminder Shared Library v2.1.0
# Common functions used across all parking reminder scripts
# Eliminates code duplication and ensures consistency

# ============================================================================
# CONSTANTS
# ============================================================================

readonly PARKING_LOG=/var/log/parking-reminder/reminder.log
readonly PARKING_VACATION_FILE=/var/lib/parking-reminder/vacation-mode
readonly PARKING_ACK_DIR=/var/lib/parking-reminder
readonly PARKING_ACK_MAX_AGE=14400  # 4 hours in seconds
readonly PARKING_LOCK_DIR=/var/run/parking-reminder-lock

# ============================================================================
# LOGGING
# ============================================================================

# Base logging function
# Usage: parking_log "MESSAGE" ["PREFIX"]
parking_log() {
    local message="$1"
    local prefix="${2:-}"

    if [ -n "$prefix" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] $prefix: $message" >> "$PARKING_LOG"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] $message" >> "$PARKING_LOG"
    fi
}

# ============================================================================
# DATE/TIME HELPERS
# ============================================================================

# Check if today is Sunday (no parking moves required)
# Returns: 0 if Sunday, 1 otherwise
is_sunday() {
    local day=$(LC_ALL=C date +%u)
    [ "$day" -eq 7 ]
}

# Get day of week (1=Monday, 7=Sunday)
# Returns: Day number 1-7
get_day_of_week() {
    LC_ALL=C date +%u
}

# ============================================================================
# PARKING LOGIC
# ============================================================================

# Calculate parking sides based on day of week
# Mon/Wed/Fri: AWAY -> HOUSE
# Tue/Thu/Sat: HOUSE -> AWAY
# Sunday: No move required
#
# Returns: "CURRENT DESTINATION" (space-separated)
# Example: "AWAY HOUSE" or "HOUSE AWAY"
calculate_parking_sides() {
    local day=$(get_day_of_week)

    if [ "$day" -eq 1 ] || [ "$day" -eq 3 ] || [ "$day" -eq 5 ]; then
        # Monday, Wednesday, Friday
        echo "AWAY HOUSE"
    else
        # Tuesday, Thursday, Saturday
        echo "HOUSE AWAY"
    fi
}

# ============================================================================
# ACKNOWLEDGMENT HANDLING
# ============================================================================

# Check if a valid acknowledgment file exists for given type
# Uses filename timestamp parsing for reliability across container restarts
#
# Args:
#   $1 - Acknowledgment type (gotit, nothome, moved, done)
#
# Returns: 0 if valid ack exists, 1 otherwise
#
# Note: Uses $ACK_DIR if set, otherwise $PARKING_ACK_DIR
has_ack() {
    local ack_type="$1"
    local ack_dir="${ACK_DIR:-$PARKING_ACK_DIR}"
    local current_timestamp=$(date +%s)
    local found_files=0
    local checked_files=0

    # Always log (use parking_log if available, fallback to direct logging)
    local log_prefix="HAS_ACK"

    if declare -f parking_log >/dev/null 2>&1; then
        parking_log "ACK CHECK START: type=$ack_type, current_time=$current_timestamp" "$log_prefix"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] $log_prefix: ACK CHECK START: type=$ack_type, current_time=$current_timestamp" >> "$PARKING_LOG"
    fi

    # Check if directory is readable
    if [ ! -d "$ack_dir" ]; then
        if declare -f parking_log >/dev/null 2>&1; then
            parking_log "ACK CHECK FAILED: Directory does not exist: $ack_dir" "$log_prefix"
        else
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] $log_prefix: ACK CHECK FAILED: Directory does not exist: $ack_dir" >> "$PARKING_LOG"
        fi
        return 1
    fi

    if [ ! -r "$ack_dir" ]; then
        if declare -f parking_log >/dev/null 2>&1; then
            parking_log "ACK CHECK FAILED: Directory not readable: $ack_dir" "$log_prefix"
        else
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] $log_prefix: ACK CHECK FAILED: Directory not readable: $ack_dir" >> "$PARKING_LOG"
        fi
        return 1
    fi

    # Find all ack files for this type
    for ack_file in "$ack_dir"/ack-${ack_type}.*; do
        [ -f "$ack_file" ] || continue
        found_files=$((found_files + 1))
        checked_files=$((checked_files + 1))

        # Extract timestamp from filename (format: ack-TYPE.TIMESTAMP)
        local file_timestamp=$(basename "$ack_file" | cut -d. -f2)

        # Validate timestamp is a number (allow decimal for v2.3.0+ microseconds)
        if ! [[ "$file_timestamp" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
            if declare -f parking_log >/dev/null 2>&1; then
                parking_log "ACK CHECK SKIP: Invalid format: $(basename $ack_file)" "$log_prefix"
            else
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] $log_prefix: ACK CHECK SKIP: Invalid format: $(basename $ack_file)" >> "$PARKING_LOG"
            fi
            continue
        fi

        # Handle decimal timestamps (microseconds from v2.3.0)
        local file_timestamp_int=${file_timestamp%.*}

        # Check if timestamp is within max age
        local age=$((current_timestamp - file_timestamp_int))

        # Allow 5 minutes clock skew into the future
        if [ "$age" -ge -300 ] && [ "$age" -le "$PARKING_ACK_MAX_AGE" ]; then
            # FOUND VALID ACK
            if [ "$age" -lt 0 ]; then
                if declare -f parking_log >/dev/null 2>&1; then
                    parking_log "ACK CHECK SUCCESS: type=$ack_type, file=$(basename $ack_file), age=${age}s (FUTURE - clock skew), max_age=${PARKING_ACK_MAX_AGE}s" "$log_prefix"
                else
                    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $log_prefix: ACK CHECK SUCCESS: type=$ack_type, file=$(basename $ack_file), age=${age}s (FUTURE - clock skew), max_age=${PARKING_ACK_MAX_AGE}s" >> "$PARKING_LOG"
                fi
            else
                if declare -f parking_log >/dev/null 2>&1; then
                    parking_log "ACK CHECK SUCCESS: type=$ack_type, file=$(basename $ack_file), age=${age}s ($((age/60))m), max_age=${PARKING_ACK_MAX_AGE}s" "$log_prefix"
                else
                    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $log_prefix: ACK CHECK SUCCESS: type=$ack_type, file=$(basename $ack_file), age=${age}s ($((age/60))m), max_age=${PARKING_ACK_MAX_AGE}s" >> "$PARKING_LOG"
                fi
            fi
            return 0  # Found valid acknowledgment
        else
            # FOUND EXPIRED ACK
            if declare -f parking_log >/dev/null 2>&1; then
                parking_log "ACK CHECK EXPIRED: type=$ack_type, file=$(basename $ack_file), age=${age}s ($((age/3600))h), max_age=${PARKING_ACK_MAX_AGE}s" "$log_prefix"
            else
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] $log_prefix: ACK CHECK EXPIRED: type=$ack_type, file=$(basename $ack_file), age=${age}s ($((age/3600))h), max_age=${PARKING_ACK_MAX_AGE}s" >> "$PARKING_LOG"
            fi
        fi
    done

    # No valid ack found
    if [ "$found_files" -eq 0 ]; then
        if declare -f parking_log >/dev/null 2>&1; then
            parking_log "ACK CHECK NOT FOUND: type=$ack_type, no files in $ack_dir" "$log_prefix"
        else
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] $log_prefix: ACK CHECK NOT FOUND: type=$ack_type, no files in $ack_dir" >> "$PARKING_LOG"
        fi
    else
        if declare -f parking_log >/dev/null 2>&1; then
            parking_log "ACK CHECK FAILED: type=$ack_type, checked=$checked_files files, all expired or invalid" "$log_prefix"
        else
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] $log_prefix: ACK CHECK FAILED: type=$ack_type, checked=$checked_files files, all expired or invalid" >> "$PARKING_LOG"
        fi
    fi

    return 1  # No valid acknowledgment found
}

# Check if vacation mode is enabled
# Returns: 0 if vacation mode is on, 1 otherwise
is_vacation_mode() {
    [ -f "$PARKING_VACATION_FILE" ]
}

# ============================================================================
# VALIDATION
# ============================================================================

# Validate day of week is in expected format (1-7)
# Args:
#   $1 - Day number to validate
# Returns: 0 if valid, 1 otherwise
validate_day() {
    local day="$1"
    [[ "$day" =~ ^[1-7]$ ]]
}
