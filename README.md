# Parking Reminder v2.1.2

Automated parking reminder system to prevent street parking tickets. Never pay $50 for forgetting to move your car again!

## What's New in v2.1.2 (Bugfix Release)

This version fixes a critical bug in the "Got it!" acknowledgment button.

**Bug Fix:**
- ✅ **"Got it!" button now works correctly**: Fixed 5:45pm acknowledgment logic
  - Before: Clicking "Got it!" created the ack file but reminder.sh didn't check for it
  - After: 5:45pm reminder now checks for both "gotit" and "nothome" acknowledgments
  - Impact: Prevents duplicate 5:45pm notifications when "Got it!" is clicked

**Expected Behavior:**
- "Got it!" at 5:45pm → No more 5:45pm duplicates, but 6pm and 6:45pm reminders still fire
- "Not home" → Stops ALL notifications (unchanged)
- "I moved it" at 6pm → Stops 6pm and 6:45pm (unchanged)
- "Done!" at 6:45pm → Stops escalation SMS/call (unchanged)

**File Changed:**
- reminder.sh:122 - Added "gotit" check to 5:45pm acknowledgment logic

## What Was New in v2.1.1 (UX Enhancement)

This version adds time-aware status notifications for better user experience.

**UX Improvement:**
- ✅ **Context-aware "Where Do I Park?" button**: Message changes based on time of day
  - **Before 6pm**: Shows future parking side + "6-7pm window"
  - **6:00pm-6:59pm**: Urgent message "🚨 Park on X side (window closes at 7pm)"
  - **After 7pm**: Confirmation "✅ You should now be parked on X side"
- ✅ **More actionable information**: Users get time-relevant instructions instead of generic message
- ✅ **Reduces anxiety**: After 7pm, confirms correct parking side

**Impact:**
- Improves UX when checking status during the parking window
- Makes on-demand status button more helpful in real-world usage

## What Was New in v2.1.0 (Refactoring Release)

This version improves code maintainability through shared library extraction - **no functional changes**.

**Code Quality Improvements:**
- ✅ **Shared library**: Created `parking-lib.sh` with common functions
- ✅ **Code deduplication**: Parking side logic extracted from 4 files into ONE function
- ✅ **DRY principle**: `calculate_parking_sides()`, `is_sunday()`, `has_ack()` now reusable
- ✅ **Easier maintenance**: Rule changes now require updating only one file
- ✅ **Consistency**: All scripts use identical logic (no more drift between files)

**Impact:**
- Addresses High Priority Issue #1 from security analysis
- Reduces future bug risk from inconsistent implementations
- Makes adding new features easier (shared helper functions)

## What Was Fixed in v2.0.4 (Analysis & Critical Fix)

This version fixed a critical error handling bug and added code quality analysis.

**Critical Bug Fix:**
- ✅ **status-notify.sh error checking**: Fixed bug where `$?` checked assignment instead of curl exit code
  - Before: `CURL_RESULT=$(curl ...); if [ $? -eq 0 ]` (always returned 0)
  - After: `if CURL_RESULT=$(curl ...); then` (correctly checks curl)
  - Impact: On-demand status notifications now correctly report failures

**Analysis Added:**
- ✅ **OPTIMIZATION_ANALYSIS.md**: Comprehensive code review identifying 10 optimization opportunities
- ✅ **Code quality assessment**: 8/10 rating - functionally correct with minor improvements possible
- ✅ **Priority roadmap**: High/Medium/Low priority issues documented for future work

## What Was Fixed in v2.0.3 (Consistency & Precision)

This version fixed acknowledgment consistency and time window precision bugs.

**Critical Fixes:**
- ✅ **Acknowledgment consistency**: Escalation scripts now use filename timestamp parsing (not mtime)
  - Ensures acknowledgments work reliably across container restarts
  - Prevents edge cases where mtime differs from creation time
- ✅ **Time window precision**: Fixed ±2 minute window drift
  - 5:45pm window: 1745-1747 (was 1743-1747)
  - 6:00pm window: 1800-1802 (was 1758-1802)
  - 6:45pm window: 1845-1847 (was 1843-1847)
  - Eliminates race conditions with early notifications
- ✅ **Diagnostic logging**: Added comprehensive debug logs for acknowledgment file detection

**Impact:**
- High - addresses reported issues where notifications weren't sending or buttons didn't work

## What Was Fixed in v2.0.2 (Hardening Release)

This version addresses **7 additional critical vulnerabilities** found by security audit of v2.0.1, plus production fixes.

**New Fixes:**
- ✅ **Path traversal protection**: Proper URL parsing prevents query param bypass
- ✅ **Argument injection fix**: Conditional curl auth prevents credential parsing issues
- ✅ **Stale lock cleanup**: PID-based locks with timeout recovery (no more permanent deadlocks)
- ✅ **Timestamp validation**: Parse timestamps from filenames (immune to clock changes)
- ✅ **Zombie process reaping**: SIGCHLD handler prevents process table exhaustion
- ✅ **Rate limiting**: 10 req/min per IP prevents abuse
- ✅ **Comprehensive healthcheck**: Tests cron, file writes, env vars (not just HTTP)
- ✅ **Separate cleanup cron**: Daily 3am job prevents disk filling during vacations
- ✅ **Time validation**: Prevents crashes if date command fails
- ✅ **Re-validated URLs**: WEBHOOK_BASE_URL checked before JSON injection
- ✅ **Stderr logging**: Errors visible in docker logs when container fails to start
- ✅ **Notification priority fix**: Status notifications use "high" priority for Android alerts

## What Was Fixed in v2.0.1 (Security Release)

v2.0.1 fixed **34 critical security and reliability issues** from v2.0:
- ✅ Replaced insecure netcat (`nc -e /bin/bash`) with secure Python HTTP server
- ✅ Fixed unquoted variables in curl auth (command injection)
- ✅ Fixed acknowledgment logic: "Got it!" now correctly keeps backup notifications
- ✅ Atomic lock files, timestamp-based acknowledgment expiration (no race conditions)
- ✅ Split escalation into separate cron jobs (no blocking `sleep 300`)
- ✅ Fixed string vs arithmetic time comparisons
- ✅ TwiML properly escaped to prevent XML injection
- ✅ Environment validation (container won't start with missing config)
- ✅ Dynamic URLs (no hardcoded IPs in action buttons)

See [FIXES.md](FIXES.md) for complete v2.0.1 details.

## Problem Solved

Daily street parking alternates sides between 6-7pm window:
- **Mon/Wed/Fri**: AWAY side → HOUSE side
- **Tue/Thu/Sat**: HOUSE side → AWAY side
- **Sunday**: No move required

This system sends smart notifications, allows acknowledgment, and escalates to SMS/phone calls if needed.

## Features

### Core Functionality
- ✅ **Smart Notifications**: Three-stage reminders (5:45pm, 6:00pm, 6:45pm)
- ✅ **Acknowledgment Buttons**: Stop future notifications when you respond
- ✅ **On-Demand Status**: Web UI button to check parking status while driving
- ✅ **Vacation Mode**: Pause all reminders via web toggle
- ✅ **SMS/Phone Escalation**: Twilio integration for 6:55pm SMS, 7:00pm call
- ✅ **Self-Hosted ntfy**: Authenticated notification server with failsafe
- ✅ **Uptime Kuma Integration**: Push monitoring for reliability
- ✅ **Mobile Web UI**: Add to home screen for quick access

### Smart Button Logic
Different buttons trigger different behaviors:

**5:45pm Reminder** (15-minute warning)
- "Got it!" → Keeps 6:00pm and 6:45pm backups (acknowledged but not moved yet)
- "Not home" → Stops ALL reminders (car is with you)

**6:00pm Reminder** (urgent)
- "I moved it" → Stops ALL reminders (task complete)
- "Not home" → Stops ALL reminders

**6:45pm Reminder** (last call)
- "Done!" → Stops escalation only (already moved)
- "Not home" → Stops ALL reminders

## Architecture

```
┌─────────────────┐
│  Self-Hosted    │
│  ntfy Server    │◄────┐
│ (Traefik + SSL) │     │
└─────────────────┘     │
                        │
┌─────────────────┐     │
│    Parking      │     │
│   Reminder      │─────┤
│   Container     │     │
│                 │     │
│ - Cron Jobs     │     │
│ - Webhook UI    │     ├──► Mobile Device
│ - Escalation    │     │    (Notifications)
└─────────────────┘     │
                        │
┌─────────────────┐     │
│  Twilio API     │◄────┘
│  (SMS + Voice)  │
└─────────────────┘
```

## Installation

### Prerequisites

- Docker and Docker Compose
- Unraid server or any Docker host
- Domain name with Traefik reverse proxy (for ntfy)
- Optional: Twilio account for SMS/phone escalation
- Optional: Uptime Kuma for monitoring

### Step 1: Deploy Self-Hosted ntfy Server

```bash
cd ~
mkdir -p ntfy-server/config
cd ntfy-server
```

Create `docker-compose.yml` and `config/server.yml` (see files in project).

Deploy ntfy:
```bash
docker-compose up -d
```

Create ntfy user:
```bash
docker exec -it ntfy-server ntfy user add your_username
# Enter password when prompted
```

Verify: Visit https://ntfy.yourdomain.com

### Step 2: Deploy Parking Reminder

```bash
cd /path/to/parking-reminder
```

Edit `.env` file:
```bash
NTFY_SERVER=https://ntfy.yourdomain.com
NTFY_TOPIC=parking
NTFY_AUTH_USER=your_username
NTFY_AUTH_PASS=your_password_here
NTFY_FAILSAFE_TOPIC=parking_backup_RANDOMSTRING
```

Optional Twilio configuration:
```bash
TWILIO_ACCOUNT_SID=ACxxxxx
TWILIO_AUTH_TOKEN=your_token
TWILIO_FROM_PHONE=+15551234567
TWILIO_TO_PHONE=+15557654321
```

Optional Uptime Kuma:
```bash
UPTIME_KUMA_PUSH_URL=http://your-uptime-kuma:3001/api/push/xxxxx
```

Build and deploy:
```bash
docker-compose build
docker-compose up -d
```

### Step 3: Configure Mobile Device

1. Subscribe to ntfy topic:
   - Open https://ntfy.yourdomain.com
   - Subscribe to `parking` topic
   - Enter username/password
   - Install ntfy mobile app (iOS/Android)
   - Add subscription in app

2. Add web UI to home screen:
   - Visit http://YOUR_SERVER_IP:8085/
   - iOS: Safari → Share → Add to Home Screen
   - Android: Chrome → Menu → Add to Home Screen

### Step 4: Test the System

```bash
# Test notification manually
docker exec parking-reminder /usr/local/bin/reminder.sh

# Test on-demand status
curl -X POST http://YOUR_SERVER_IP:8085/status

# Test vacation mode
./vacation.sh on
./vacation.sh status
./vacation.sh off
```

## Configuration Files

### File Structure
```
parking-reminder/
├── Dockerfile              # Container definition (Python + bash)
├── docker-compose.yml      # Container orchestration
├── .env                    # Configuration (keep private!)
├── crontab                 # Schedule definitions
├── entrypoint.sh          # Container startup (FIXED)
├── parking-lib.sh         # Shared function library (v2.1.0)
├── reminder.sh            # Main notification logic (REFACTORED)
├── ack-server.py          # Secure Python HTTP server (NEW)
├── status.html            # Mobile web UI
├── status-notify.sh       # On-demand status (REFACTORED)
├── escalation-sms.sh      # SMS escalation only (REFACTORED)
├── escalation-call.sh     # Phone call escalation only (REFACTORED)
├── vacation.sh            # CLI vacation helper
├── cleanup-acks.sh        # Stale ack file cleanup (NEW v2.0.2)
├── .gitignore             # Git exclusions
├── FIXES.md               # Security fixes documentation (NEW)
├── OPTIMIZATION_ANALYSIS.md  # Code optimization review (v2.0.4)
└── README.md              # This file
```

### Notification Schedule (Mon-Sat)

```
5:44pm  - Clean acknowledgment state
5:45pm  - First warning (15 minutes)
6:00pm  - Urgent reminder (move now)
6:45pm  - Last call (15 minutes left)
6:55pm  - SMS escalation (if no ack)
7:00pm  - Phone call (if still no ack)
```

## Usage

### Daily Operation

1. **Normal day**: Receive notifications, click appropriate button
2. **Forgot while driving**: Open home screen icon → "Where Did I Park?"
3. **Going on vacation**: Open home screen icon → Toggle vacation mode ON
4. **Back from vacation**: Toggle vacation mode OFF

### Vacation Mode

**Via Web UI** (recommended):
- Visit http://YOUR_SERVER_IP:8085/
- Toggle "Vacation Mode" switch

**Via CLI**:
```bash
./vacation.sh on      # Enable vacation mode
./vacation.sh off     # Disable vacation mode
./vacation.sh status  # Check current status
```

### Acknowledgment State Files

Located in `/var/lib/parking-reminder/`:
- `ack-gotit` - User clicked "Got it!" (5:45pm)
- `ack-nothome` - User clicked "Not home"
- `ack-moved` - User clicked "I moved it" (6:00pm)
- `ack-done` - User clicked "Done!" (6:45pm)
- `vacation-mode` - Vacation mode enabled flag

These files are automatically cleaned at 5:44pm daily.

## Monitoring & Logs

### View Logs
```bash
# Container logs
docker logs -f parking-reminder

# Application log
docker exec parking-reminder tail -f /var/log/parking-reminder/reminder.log

# Or view on host
tail -f ./logs/reminder.log
```

### Uptime Kuma Integration

Create a "Push" monitor in Uptime Kuma:
1. Add new monitor → Type: Push
2. Copy the push URL
3. Add to `.env` as `UPTIME_KUMA_PUSH_URL`
4. Each successful reminder execution sends heartbeat

### Healthcheck

Docker healthcheck runs every 5 minutes:
```bash
docker ps  # Check STATUS column for "healthy"
```

Manual health check:
```bash
curl http://YOUR_SERVER_IP:8085/health
```

## Troubleshooting

### No Notifications Received

1. Check ntfy server is running:
   ```bash
   docker ps | grep ntfy
   curl https://ntfy.yourdomain.com/v1/health
   ```

2. Verify authentication:
   ```bash
   docker exec parking-reminder env | grep NTFY
   ```

3. Test notification manually:
   ```bash
   docker exec parking-reminder /usr/local/bin/reminder.sh
   ```

4. Check logs for errors:
   ```bash
   docker exec parking-reminder tail -f /var/log/parking-reminder/reminder.log
   ```

### Webhook UI Not Loading

1. Verify container is running:
   ```bash
   docker ps | grep parking-reminder
   ```

2. Check port mapping:
   ```bash
   docker port parking-reminder
   ```

3. Test webhook server:
   ```bash
   curl http://YOUR_SERVER_IP:8085/health
   ```

### Vacation Mode Not Working

1. Check vacation mode file:
   ```bash
   docker exec parking-reminder ls -la /var/lib/parking-reminder/vacation-mode
   ```

2. Check webhook server logs:
   ```bash
   docker logs parking-reminder | grep WEBHOOK
   ```

### Escalation Not Triggering

1. Verify Twilio credentials in `.env`
2. Check escalation.sh logs:
   ```bash
   docker exec parking-reminder tail -f /var/log/parking-reminder/reminder.log | grep ESCALATION
   ```

3. Manually trigger escalation:
   ```bash
   docker exec parking-reminder /usr/local/bin/escalation.sh
   ```

### Container Won't Start

1. Check Docker logs:
   ```bash
   docker logs parking-reminder
   ```

2. Verify .env file is properly formatted (no spaces around `=`)
3. Ensure required environment variables are set
4. Check file permissions:
   ```bash
   ls -la *.sh
   # All .sh files should be executable
   ```

## Security Considerations

- **Private Configuration**: Never commit `.env` file to git
- **ntfy Authentication**: Always use authentication on self-hosted ntfy
- **Twilio Credentials**: Store securely, rotate if compromised
- **Network Isolation**: Consider running on private Docker network
- **Firewall Rules**: Restrict port 8085 to local network only
- **HTTPS**: Use Traefik + Let's Encrypt for ntfy server

## Failsafe Mechanisms

1. **Cloud ntfy.sh Backup**: If self-hosted fails, notification sent to cloud
2. **Retry Logic**: 3 retry attempts with 2-second delays
3. **Lock Files**: Prevents duplicate executions
4. **Vacation Mode**: Manual override for extended absences
5. **Escalation Chain**: SMS → Phone call if no acknowledgment
6. **Uptime Monitoring**: External heartbeat tracking

## Development & Customization

### Changing Notification Times

Edit `crontab`:
```bash
# Example: Move first reminder to 5:30pm
30 17 * * 1-6 /usr/local/bin/reminder.sh
```

Rebuild container:
```bash
docker-compose up -d --build
```

### Changing Parking Sides

Edit `reminder.sh` and `status-notify.sh`:
```bash
# Lines 53-59 define the side calculation logic
if [ "$day" -eq 1 ] || [ "$day" -eq 3 ] || [ "$day" -eq 5 ]; then
    CURRENT="AWAY"
    DESTINATION="HOUSE"
else
    CURRENT="HOUSE"
    DESTINATION="AWAY"
fi
```

### Adding Custom Notifications

Follow the pattern in `reminder.sh`:
```bash
elif [ "$current_time" -ge HHMM ] && [ "$current_time" -le HHMM ]; then
    MSG="Your message"
    PRIORITY="high|urgent|default"
    TAGS="emoji,tags"
    ACTIONS='[...]'
    REMINDER_TYPE="custom-type"
```

## Backup & Restore

### Backup Configuration
```bash
tar -czf parking-reminder-backup.tar.gz \
    .env docker-compose.yml *.sh crontab status.html
```

### Restore Configuration
```bash
tar -xzf parking-reminder-backup.tar.gz
docker-compose up -d --build
```

## Upgrading

From v1.0 to v2.0:
1. Backup current configuration
2. Pull v2.0 files
3. Update `.env` with new variables
4. Rebuild container: `docker-compose up -d --build`
5. Test all features

## Version History

### v2.0.1 (Current - Security Release)
- ✅ **CRITICAL**: Replaced netcat with Python HTTP server (no more `nc -e` backdoor)
- ✅ **CRITICAL**: Fixed command injection in AUTH_HEADER
- ✅ **CRITICAL**: Fixed acknowledgment logic ("Got it!" now works correctly)
- ✅ **CRITICAL**: Fixed race conditions (atomic locks, timestamp-based expiration)
- ✅ **CRITICAL**: Fixed blocking operations (split escalation into separate jobs)
- ✅ Fixed time comparison bugs (arithmetic vs string)
- ✅ Fixed TwiML XML injection
- ✅ Added environment validation
- ✅ Dynamic webhook URLs (no hardcoded IPs)
- ✅ Improved healthcheck frequency (30s instead of 5min)
- ✅ All 34 security issues resolved

### v2.0 (Features)
- Smart acknowledgment buttons with context-aware logic
- On-demand status check via web UI
- Vacation mode toggle
- SMS and phone call escalation
- Self-hosted ntfy with authentication
- Uptime Kuma integration
- Mobile-optimized web interface
- Lock file mechanism
- Failsafe notifications

### v1.0 (Initial)
- Basic notifications via cloud ntfy.sh
- Four daily reminders (4pm, 5:45pm, 6pm, 6:45pm)
- No acknowledgment or escalation

## Roadmap

Planned enhancements for future versions:

### Context-Aware Status Notifications
**Status:** Planned
**Priority:** Medium

Make "Where Do I Park?" button show time-relevant messages:
- **Before 6pm**: "Move to X side (6-7pm window)" (current behavior)
- **During 6-7pm**: "🚨 Park on X side (window closes at 7pm)" (urgent, active)
- **After 7pm**: "✅ You should now be parked on X side" (confirmation)

This reduces confusion when checking status during the active parking window.

See [CLAUDE.md](CLAUDE.md#roadmap--future-enhancements) for detailed implementation notes.

## Credits

- Built with Docker, Alpine Linux, bash
- Notifications: [ntfy](https://ntfy.sh)
- SMS/Voice: [Twilio](https://www.twilio.com)
- Monitoring: [Uptime Kuma](https://github.com/louislam/uptime-kuma)
- Reverse Proxy: [Traefik](https://traefik.io)

## License

MIT License - Use at your own risk. Not responsible for parking tickets if system fails.

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review logs: `docker logs parking-reminder`
3. Test components individually
4. Create GitHub issue with logs

---

**Built to solve a real problem. Save money, reduce stress, never forget parking again.**
