#!/bin/bash
# Parking Reminder Shared Library v2.1.2
# Common functions used across all parking reminder scripts
# Eliminates code duplication and ensures consistency
#
# v2.1.2 changes:
# - FIXED: has_ack() now uses find instead of glob patterns (more reliable)
# - FIXED: Better logging to diagnose acknowledgment issues
# - FIXED: Directory existence check before searching for ack files
# - FIXED: More robust timestamp extraction using last field

# ============================================================================
# CONSTANTS
# ============================================================================

readonly PARKING_LOG=/var/log/parking-reminder/reminder.log
readonly PARKING_VACATION_FILE=/var/lib/parking-reminder/vacation-mode
readonly PARKING_ACK_DIR=/var/lib/parking-reminder
readonly PARKING_ACK_MAX_AGE=14400  # 4 hours in seconds

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

    # FIXED v2.1.2: Always log to help debugging
    if declare -f log >/dev/null 2>&1; then
        log "DEBUG: Checking for ack-$ack_type in $ack_dir"
    fi

    # FIXED v2.1.2: Verify directory exists and is readable
    if [ ! -d "$ack_dir" ]; then
        if declare -f log >/dev/null 2>&1; then
            log "ERROR: Ack directory does not exist: $ack_dir"
        fi
        return 1
    fi

    # FIXED v2.1.2: Use explicit find with proper error handling
    # This is more reliable than glob patterns in edge cases
    while IFS= read -r -d '' ack_file; do
        found_files=$((found_files + 1))

        # Extract timestamp from filename - use LAST field for robustness
        # Format: ack-TYPE.TIMESTAMP (e.g., ack-moved.1730419200)
        local filename=$(basename "$ack_file")
        local file_timestamp=$(echo "$filename" | rev | cut -d. -f1 | rev)

        # Validate timestamp is a number
        if ! [[ "$file_timestamp" =~ ^[0-9]+$ ]]; then
            if declare -f log >/dev/null 2>&1; then
                log "WARNING: Invalid ack file format (bad timestamp): $filename"
            fi
            continue
        fi

        # Check if timestamp is within max age
        local age=$((current_timestamp - file_timestamp))
        if [ "$age" -le "$PARKING_ACK_MAX_AGE" ] && [ "$age" -ge 0 ]; then
            if declare -f log >/dev/null 2>&1; then
                log "INFO: Found valid ack-$ack_type (file: $filename, age: ${age}s)"
            fi
            return 0  # Found valid acknowledgment
        else
            if declare -f log >/dev/null 2>&1; then
                log "DEBUG: Found expired ack-$ack_type (file: $filename, age: ${age}s)"
            fi
        fi
    done < <(find "$ack_dir" -maxdepth 1 -type f -name "ack-${ack_type}.*" -print0 2>/dev/null)

    if [ "$found_files" -eq 0 ]; then
        if declare -f log >/dev/null 2>&1; then
            log "INFO: No ack-$ack_type files found (notifications will continue)"
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
