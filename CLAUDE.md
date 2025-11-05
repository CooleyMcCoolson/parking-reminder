# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Parking Reminder v2.1.0** - Automated street parking notification system to prevent parking tickets. Sends smart reminders for daily parking side alternation (6-7pm window) with acknowledgment buttons, vacation mode, and SMS/phone escalation.

**Architecture**: Hybrid bash/Python (v2.1.0 - production-ready)
- Bash scripts for notification logic and scheduling (with shared library for code reuse)
- Python HTTP server for webhook endpoints
- Docker container with Alpine Linux + cron
- File-based state management with timestamp-based expiration
- ntfy for push notifications
- Twilio for SMS/phone escalation (optional)

**Why hybrid?** Bash excels at cron integration and simple scripting. Python provides robust HTTP handling and security. This architecture is committed long-term - no rewrite planned.

**v2.1.0 Changes**: Refactored bash scripts to use shared library (`parking-lib.sh`) for common functions. Parking side calculation logic now in ONE place instead of duplicated across 4 files. No functional changes - pure code quality improvement.

## Build and Deployment

### Build Container Image

```bash
docker build -t parking-reminder:2.1.0 .
```

### Deploy on Unraid Server

The production deployment is on Unraid server at `10.27.27.157` under `/cache_nvme/appdata/parking-reminder/`.

```bash
# SSH to Unraid
ssh root@10.27.27.157

# Navigate to project directory
cd /cache_nvme/appdata/parking-reminder

# Build image
docker build -t parking-reminder:2.1.0 .

# Run container (using environment variables from .env)
cd /cache_nvme/appdata/parking-reminder && source .env && docker run -d \
  --name parking-reminder \
  --restart unless-stopped \
  -v ./logs:/var/log/parking-reminder \
  -v ./state:/var/lib/parking-reminder \
  -p 8085:8085 \
  -e TZ=America/New_York \
  -e WEBHOOK_BASE_URL="$WEBHOOK_BASE_URL" \
  -e WEBHOOK_PORT=8085 \
  -e NTFY_SERVER="$NTFY_SERVER" \
  -e NTFY_TOPIC="$NTFY_TOPIC" \
  -e NTFY_AUTH_USER="$NTFY_AUTH_USER" \
  -e NTFY_AUTH_PASS="$NTFY_AUTH_PASS" \
  -e NTFY_FAILSAFE_TOPIC="$NTFY_FAILSAFE_TOPIC" \
  -e TWILIO_ACCOUNT_SID="$TWILIO_ACCOUNT_SID" \
  -e TWILIO_AUTH_TOKEN="$TWILIO_AUTH_TOKEN" \
  -e TWILIO_FROM_PHONE="$TWILIO_FROM_PHONE" \
  -e TWILIO_TO_PHONE="$TWILIO_TO_PHONE" \
  -e UPTIME_KUMA_PUSH_URL="$UPTIME_KUMA_PUSH_URL" \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  parking-reminder:2.1.0
```

### Restart Container After Changes

```bash
ssh root@10.27.27.157 "docker stop parking-reminder && docker rm parking-reminder"
# Then run the docker run command above
```

## Testing and Debugging

### Manual Testing

```bash
# Test notification manually
ssh root@10.27.27.157 "docker exec parking-reminder /usr/local/bin/reminder.sh"

# Test on-demand status
curl -X POST http://10.27.27.157:8085/status

# Test vacation mode
ssh root@10.27.27.157 "docker exec parking-reminder /usr/local/bin/vacation.sh on"
ssh root@10.27.27.157 "docker exec parking-reminder /usr/local/bin/vacation.sh status"
ssh root@10.27.27.157 "docker exec parking-reminder /usr/local/bin/vacation.sh off"

# Test ntfy authentication
curl -u USERNAME:PASSWORD -d "Test" https://ntfy.mccoolson.com/parking

# Check healthcheck
curl http://10.27.27.157:8085/health
```

### View Logs

```bash
# Container logs
ssh root@10.27.27.157 "docker logs -f parking-reminder"

# Application log (reminder.sh output)
ssh root@10.27.27.157 "docker exec parking-reminder tail -f /var/log/parking-reminder/reminder.log"

# Or from host
ssh root@10.27.27.157 "tail -f /cache_nvme/appdata/parking-reminder/logs/reminder.log"
```

### Check State Files

```bash
# View current acknowledgments
ssh root@10.27.27.157 "docker exec parking-reminder ls -la /var/lib/parking-reminder/"

# Check vacation mode
ssh root@10.27.27.157 "docker exec parking-reminder cat /var/lib/parking-reminder/vacation-mode"
```

### Debug ntfy Issues

```bash
# Check ntfy user exists and has permissions
ssh root@10.27.27.157 "docker exec ntfy-server ntfy user list"

# Verify credentials in container
ssh root@10.27.27.157 "docker exec parking-reminder env | grep NTFY"

# Test ntfy send from container
ssh root@10.27.27.157 "docker exec parking-reminder sh -c 'curl -u \$NTFY_AUTH_USER:\$NTFY_AUTH_PASS -d \"Test\" \$NTFY_SERVER/\$NTFY_TOPIC'"
```

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────┐
│  parking-reminder Container (Alpine Linux)             │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐    ┌──────────────────────┐         │
│  │ cron daemon  │───▶│  reminder.sh         │         │
│  │              │    │  (5:45pm, 6pm, 6:45pm)│         │
│  │              │    └──────────────────────┘         │
│  │              │                                       │
│  │              │    ┌──────────────────────┐         │
│  │              │───▶│  escalation-sms.sh   │         │
│  │              │    │  (6:55pm)             │         │
│  │              │    └──────────────────────┘         │
│  │              │                                       │
│  │              │    ┌──────────────────────┐         │
│  │              │───▶│  escalation-call.sh  │         │
│  └──────────────┘    │  (7:00pm)             │         │
│                      └──────────────────────┘         │
│                                                         │
│  ┌──────────────────────────────────────────┐         │
│  │  ack-server.py (Python HTTP Server)      │         │
│  │  - Port 8085                              │         │
│  │  - Serves status.html                     │         │
│  │  - Handles /ack/* webhooks                │         │
│  │  - Handles /status, /vacation/* endpoints │         │
│  └──────────────────────────────────────────┘         │
│                                                         │
│  State: /var/lib/parking-reminder/                     │
│  - ack-gotit.<timestamp>                               │
│  - ack-nothome.<timestamp>                             │
│  - ack-moved.<timestamp>                               │
│  - ack-done.<timestamp>                                │
│  - vacation-mode                                        │
└─────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
   ┌──────────┐                 ┌──────────────┐
   │   ntfy   │                 │    Twilio    │
   │  Server  │                 │ (SMS + Voice)│
   └──────────┘                 └──────────────┘
```

### Key Files

- **parking-lib.sh**: Shared function library (v2.1.0) - common functions for all scripts
  - `calculate_parking_sides()` - determines CURRENT/DESTINATION based on day
  - `is_sunday()` - Sunday check
  - `has_ack()` - acknowledgment file validation
  - `get_day_of_week()` - returns 1-7 for Mon-Sun
- **entrypoint.sh**: Container startup, launches cron and webhook server
- **crontab**: Cron schedule for reminders and escalation
- **reminder.sh**: Main notification logic (5:45pm, 6pm, 6:45pm) - sources parking-lib.sh
- **status-notify.sh**: On-demand status notification (via web UI button) - sources parking-lib.sh
- **escalation-sms.sh**: SMS escalation at 6:55pm - sources parking-lib.sh
- **escalation-call.sh**: Phone call escalation at 7:00pm - sources parking-lib.sh
- **ack-server.py**: Python HTTP server for webhooks and web UI
- **vacation.sh**: CLI helper for vacation mode
- **cleanup-acks.sh**: Daily cleanup of stale acknowledgment files (3am)
- **status.html**: Mobile web UI (served by ack-server.py)

### State Management

State files are created with timestamps in filename: `ack-gotit.1730419200`

Expiration is checked by file age (mtime) rather than deletion at 5:44pm. This prevents race conditions.

## Important Environment Variables

**Required:**
- `NTFY_SERVER`: ntfy server URL (e.g., `https://ntfy.mccoolson.com`)
- `NTFY_TOPIC`: ntfy topic name (e.g., `parking`)
- `WEBHOOK_BASE_URL`: Base URL for action buttons (e.g., `http://10.27.27.157:8085`)

**Authentication (recommended):**
- `NTFY_AUTH_USER`: ntfy username
- `NTFY_AUTH_PASS`: ntfy password

**Optional:**
- `NTFY_FAILSAFE_TOPIC`: Backup topic on cloud ntfy.sh if self-hosted fails
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_PHONE`, `TWILIO_TO_PHONE`: For SMS/call escalation
- `UPTIME_KUMA_PUSH_URL`: Heartbeat monitoring

## Parking Logic

**Days and Sides:**
- **Mon/Wed/Fri**: Park on AWAY side → Move to HOUSE side
- **Tue/Thu/Sat**: Park on HOUSE side → Move to AWAY side
- **Sunday**: No move required

**Notification Schedule (Mon-Sat only):**
- **5:45pm**: First warning (15 min before window)
  - Buttons: "Got it!" (keeps later reminders), "Not home" (stops all)
- **6:00pm**: Urgent reminder
  - Buttons: "I moved it" (stops all), "Not home" (stops all)
- **6:45pm**: Last call (15 min remaining)
  - Buttons: "Done!" (stops escalation only), "Not home" (stops all)
- **6:55pm**: SMS escalation (if no acknowledgment)
- **7:00pm**: Phone call escalation (if still no acknowledgment)

**Smart Acknowledgment Logic:**
- "Got it!" (5:45pm) - Acknowledges warning but keeps 6pm and 6:45pm backups
- "Not home" - Stops ALL notifications (car is with you)
- "I moved it" (6pm) - Stops ALL notifications (task complete)
- "Done!" (6:45pm) - Stops escalation only (already moved)

## Common Issues and Fixes

### Issue: Notifications Not Sending

**Check:**
1. ntfy server is running: `ssh root@10.27.27.157 "docker ps | grep ntfy"`
2. Credentials are correct: Check `NTFY_AUTH_USER` and `NTFY_AUTH_PASS` in `.env`
3. User has topic permissions: `ssh root@10.27.27.157 "docker exec ntfy-server ntfy user list"`
4. Test manually: `docker exec parking-reminder /usr/local/bin/reminder.sh`

**Common fix**: Reset ntfy user password and update `.env`

### Issue: Bash Script "Exec format error"

**Cause**: Incorrect shebang (e.g., `#\!/bin/bash` instead of `#!/bin/bash`)

**Fix**: Ensure first line of all `.sh` files is exactly `#!/bin/bash` without escaping

### Issue: Variable Substitution Errors

**Example**: `bad substitution: ${!var:-}`

**Cause**: Escaped special characters from heredoc rewrites

**Fix**: Use the files from git repo instead of rewriting via SSH heredoc

### Issue: Web UI Shows 500 Error

**Check logs**: `docker exec parking-reminder tail -20 /var/log/parking-reminder/reminder.log`

**Common causes**:
- Script syntax error (check shebang, variable escaping)
- Missing environment variables
- Permission issues on scripts

## Security Notes

**v2.0.1** fixed **34 critical security issues** from v2.0.
**v2.0.2** addressed **6 additional major vulnerabilities** found in security audit.

See `FIXES.md` for v2.0.1 details.

**Key Security Improvements (v2.0.1):**
- ✅ Replaced insecure `nc -e /bin/bash` with Python HTTP server
- ✅ Fixed command injection in curl authentication (now uses `--user` flag)
- ✅ Dynamic webhook URLs (no hardcoded IPs in code)
- ✅ Atomic lock files using `mkdir` instead of `touch`
- ✅ Fixed race conditions with timestamp-based expiration
- ✅ XML escaping for TwiML
- ✅ Environment variable validation in entrypoint
- ✅ Arithmetic time comparison (not string)

**Additional Fixes (v2.0.2):**
- ✅ Path traversal protection (proper URL parsing with `urlparse`)
- ✅ Argument injection fix (conditional curl auth instead of unquoted variables)
- ✅ Stale lock cleanup (PID-based with timeout detection)
- ✅ Timestamp-based ack file validation (parse filename, not mtime)
- ✅ Zombie process reaping (SIGCHLD handler in Python server)
- ✅ Rate limiting (10 req/min per IP on all endpoints)
- ✅ Busybox compatibility (replaced `find -delete` with explicit `rm`)
- ✅ Notification priority fix (status-notify.sh uses "high" priority for Android alerts)

**Production Configuration:**
- ntfy authentication: Username `cooley`, password `parking2024`
- Twilio SMS/Voice escalation: Configured and enabled (live account)

**Important**: `.env` file contains credentials - never commit to git!

## Deployment URLs

**Production:**
- Web UI: https://parking.mccoolson.com (Authelia SSO protected)
- Webhook Base: http://10.27.27.157:8085 (internal)
- ntfy Server: https://ntfy.mccoolson.com

**Authentication:**
- Authelia: one_factor (password only, no 2FA)
- Session cookie domain: `mccoolson.com`
- Auth URL: https://auth.mccoolson.com

## Development Workflow

**Production deployment on Unraid is now a Git repository!** (Set up 2025-11-04)

### Quick Deploy Workflow

1. Make changes locally in `/home/cooley/projects/eatit_roc/parking-reminder/`
2. Commit and push to GitHub:
   ```bash
   git add .
   git commit -m "Description of changes"
   git push
   ```
3. Deploy to production (one command):
   ```bash
   ssh root@10.27.27.157 "cd /cache_nvme/appdata/parking-reminder && \
     git pull && \
     docker build -t parking-reminder:2.1.0 . && \
     docker stop parking-reminder && docker rm parking-reminder && \
     source .env && docker run -d \
       --name parking-reminder \
       --restart unless-stopped \
       -v ./logs:/var/log/parking-reminder \
       -v ./state:/var/lib/parking-reminder \
       -p 8085:8085 \
       -e TZ=America/New_York \
       -e WEBHOOK_BASE_URL=\"\$WEBHOOK_BASE_URL\" \
       -e WEBHOOK_PORT=8085 \
       -e NTFY_SERVER=\"\$NTFY_SERVER\" \
       -e NTFY_TOPIC=\"\$NTFY_TOPIC\" \
       -e NTFY_AUTH_USER=\"\$NTFY_AUTH_USER\" \
       -e NTFY_AUTH_PASS=\"\$NTFY_AUTH_PASS\" \
       -e NTFY_FAILSAFE_TOPIC=\"\$NTFY_FAILSAFE_TOPIC\" \
       -e TWILIO_ACCOUNT_SID=\"\$TWILIO_ACCOUNT_SID\" \
       -e TWILIO_AUTH_TOKEN=\"\$TWILIO_AUTH_TOKEN\" \
       -e TWILIO_FROM_PHONE=\"\$TWILIO_FROM_PHONE\" \
       -e TWILIO_TO_PHONE=\"\$TWILIO_TO_PHONE\" \
       -e UPTIME_KUMA_PUSH_URL=\"\$UPTIME_KUMA_PUSH_URL\" \
       --log-opt max-size=10m \
       --log-opt max-file=3 \
       parking-reminder:2.1.0"
   ```

### Git Setup Details

- **Unraid directory**: `/cache_nvme/appdata/parking-reminder/` is now a git clone
- **Remote**: `https://github.com/CooleyMcCoolson/parking-reminder.git`
- **Branch**: `master`
- **Backup**: Old non-git directory backed up to `parking-reminder.backup-20251104-214514/`

### Important Notes

- `.env` file is **not** in git (contains secrets)
- `state/` and `logs/` directories are **not** in git (runtime data)
- These are preserved across git pulls via `.gitignore`
- To verify git status on Unraid: `ssh root@10.27.27.157 "cd /cache_nvme/appdata/parking-reminder && git status"`

## Known Issues & Future Improvements

**Verified Production Status (as of 2025-11-01):**
- ✅ All pre-flight checks pass
- ✅ Container running v2.0.2 with correct environment variables
- ✅ Cron daemon running, timezone correct (America/New_York)
- ✅ ntfy authentication working, notifications delivering
- ✅ Healthcheck comprehensive (tests cron, directories, env vars)

**Technical Debt (Non-Critical, Fix Later):**

1. **Time Window Logic (reminder.sh lines 148, 166, 185)**
   - Current: Checks 1743-1747 (5:43-5:47pm) for 5:45pm reminder
   - Should: Check 1745-1747 (5:45-5:47pm) for exact window
   - Impact: Window is 2 minutes too wide, but cron fires at exact times so this doesn't affect production
   - Priority: Low (works correctly, just imprecise)

2. **Escalation Scripts Use Old Ack Logic**
   - `escalation-sms.sh` and `escalation-call.sh` use `find -mmin` instead of filename timestamp parsing
   - `reminder.sh` correctly parses timestamps from filenames
   - Impact: Escalation works but is inconsistent with main logic
   - Priority: Medium (fix for consistency)

3. **Vacation Mode Has No Auto-Expiration**
   - Once enabled, stays enabled forever until manually disabled
   - Risk: Forget to disable after vacation, miss reminders, get parking ticket
   - Recommendation: Add expiration timestamp to vacation-mode file
   - Priority: Medium (usability improvement)

4. **No Integration Tests**
   - Security fixes verified by manual testing only
   - No automated tests for ack file cleanup, time window logic, vacation mode, etc.
   - Priority: Medium (quality improvement)

5. **No Disaster Recovery Plan**
   - No documented backup strategy for `/var/lib/parking-reminder/` state directory
   - No migration plan for moving to new hardware
   - Environment variables in `.env` not backed up (correct for security, but need recovery plan)
   - Priority: Low (single-user deployment, can rebuild if needed)

6. **Failsafe Notification Limited**
   - Uses `|| true` so failures are silently ignored
   - Cloud ntfy.sh topic is unauthenticated (must be public)
   - If internet is down, both self-hosted and cloud fail with no alert
   - Priority: Low (self-hosted ntfy very reliable)

**What's Working Well:**
- Stale lock cleanup (PID-based with timeout)
- Comprehensive healthcheck (tests cron daemon, directories, env vars)
- Rate limiting with token bucket algorithm
- Security headers (X-Frame-Options, X-Content-Type-Options, X-XSS-Protection)
- Zombie process reaping with SIGCHLD handler
- Defensive programming (error handling, retries, validation)

## Roadmap / Future Enhancements

### Context-Aware Status Notifications
**Priority:** Medium (UX improvement)
**Complexity:** Low
**File:** `status-notify.sh`

**Problem:**
When user clicks "Where Do I Park?" button after 6pm, it shows:
```
📍 Currently parked on: HOUSE side
🎯 Move to: AWAY side (6-7pm window)
```

This message says "6-7pm window" even when checked at 6:30pm (window is already open), which is confusing.

**Solution:**
Make status notification time-aware with three states:

1. **Before Window (00:00 - 17:59)**
   ```
   📍 Currently parked on: HOUSE side
   🎯 Move to: AWAY side (6-7pm window)
   ```

2. **During Window (18:00 - 18:59)** ⭐ NEW
   ```
   🚨 Park on AWAY side (window closes at 7pm)
   ```

3. **After Window (19:00 - 23:59)** ⭐ NEW
   ```
   ✅ You should now be parked on AWAY side
   ```

**Implementation Notes:**
```bash
# In status-notify.sh, add time check:
hour=$(date +%H)

if [ "$hour" -lt 18 ]; then
    # Before window: show future move
    MSG="📍 Currently parked on: $CURRENT side\n🎯 Move to: $DESTINATION side (6-7pm window)"
elif [ "$hour" -eq 18 ]; then
    # During window: urgent instruction
    MSG="🚨 Park on $DESTINATION side (window closes at 7pm)"
else
    # After window: confirmation
    MSG="✅ You should now be parked on $DESTINATION side"
fi
```

**Scope:**
- ✅ Affects: `status-notify.sh` (on-demand "Where Do I Park?" button only)
- ❌ Does NOT affect: Scheduled reminders (5:45pm, 6pm, 6:45pm have context-appropriate messaging)

**Sunday Handling:**
Keep existing behavior: "📅 It's Sunday! No parking moves needed today."

**Benefits:**
- Users checking status while driving get clear, time-relevant information
- "Window is OPEN NOW" is more actionable than "6-7pm window" when it's 6:30pm
- After 7pm, confirmation message reduces anxiety about whether they parked correctly
