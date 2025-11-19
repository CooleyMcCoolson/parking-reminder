# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Parking Reminder v2.3.0** - Automated street parking notification system to prevent parking tickets. Sends smart reminders for daily parking side alternation (6-7pm window) with acknowledgment buttons, vacation mode with auto-expiration, and ntfy priority escalation.

**Architecture**: Hybrid bash/Python (v2.3.0 - production-ready)
- Bash scripts for notification logic and scheduling (with shared library for code reuse)
- Python HTTP server for webhook endpoints
- Docker container with Alpine Linux + cron
- File-based state management with timestamp-based expiration
- ntfy for push notifications with priority-based escalation
- Twilio SMS/phone escalation **archived** (optional, see `archive/README.md` for restoration)

**Why hybrid?** Bash excels at cron integration and simple scripting. Python provides robust HTTP handling and security. This architecture is committed long-term - no rewrite planned.

**v2.3.0 Changes** (Expert Code Review - 2025-11-19): Major reliability and observability improvements based on 6-expert security review. **Critical fixes for "ack responses sometimes don't work"**: Atomic ack file creation with O_CREAT|O_EXCL (eliminates race conditions), fsync for crash-safe persistence, comprehensive error handling with client IP logging. **Race condition fixes**: Double-check pattern eliminates HTTP→Bash race (500ms→10ms window), vacation mode TOCTOU fixed with missing_ok=True, status button rate limiter prevents double-clicks. **Logging improvements**: Comprehensive has_ack() logging shows every decision (success/expired/not found), separated ack checks log which type triggered skip, metrics logging for ack creation/notification success/failure. **Architecture improvements**: Constants centralized in parking-lib.sh (eliminated 14 duplicates), vacation mode auto-expiration prevents forgotten disable→parking ticket (default 7 days), vacation-lib.sh with backward compatibility. **Testing & Monitoring**: Clock drift detection in healthcheck (detects NTP failures), 44-test comprehensive test suite, metrics analysis script, volume mount verification in entrypoint, enhanced cleanup logging. **No breaking changes** - fully backward compatible with v2.2.0 deployments.

**v2.2.0 Changes**: Replaced Twilio SMS/phone escalation with ntfy priority-based escalation. At 6:55pm, sends single max-priority (5) notification. At 7:00pm, sends triple rapid-fire barrage (30 seconds apart) to wake user from deep sleep. Twilio scripts archived with restoration docs. Simpler architecture, no external APIs required.

**v2.1.2 Changes**: Fixed "Got it!" button acknowledgment logic. The 5:45pm reminder now properly checks for "gotit" acknowledgments to prevent duplicate notifications while still allowing 6pm and 6:45pm reminders to fire. Bug fix only.

**v2.1.1 Changes**: Added time-aware messaging to `status-notify.sh`. The "Where Do I Park?" button now shows context-specific messages based on time: before window (shows future move), during window (urgent instruction), after window (confirmation). Pure UX improvement.

**v2.1.0 Changes**: Refactored bash scripts to use shared library (`parking-lib.sh`) for common functions. Parking side calculation logic now in ONE place instead of duplicated across 4 files. No functional changes - pure code quality improvement.

## Build and Deployment

### Build Container Image

```bash
docker build -t parking-reminder:2.3.0 .
```

### Deploy on Server

The production deployment is on your server at `${YOUR_SERVER_IP}` under `${DEPLOYMENT_PATH}`.

```bash
# SSH to server
ssh root@${YOUR_SERVER_IP}

# Navigate to project directory
cd ${DEPLOYMENT_PATH}

# Build image
docker build -t parking-reminder:2.3.0 .

# Run container (using environment variables from .env)
# Note: TWILIO_* vars removed in v2.2.0 (not needed for ntfy escalation)
cd ${DEPLOYMENT_PATH} && source .env && docker run -d \
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
  -e UPTIME_KUMA_PUSH_URL="$UPTIME_KUMA_PUSH_URL" \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  parking-reminder:2.3.0
```

### Restart Container After Changes

```bash
ssh root@${YOUR_SERVER_IP} "docker stop parking-reminder && docker rm parking-reminder"
# Then run the docker run command above
```

## Testing and Debugging

### Manual Testing

```bash
# Test notification manually
ssh root@${YOUR_SERVER_IP} "docker exec parking-reminder /usr/local/bin/reminder.sh"

# Test on-demand status
curl -X POST http://${YOUR_SERVER_IP}:8085/status

# Test vacation mode
ssh root@${YOUR_SERVER_IP} "docker exec parking-reminder /usr/local/bin/vacation.sh on"
ssh root@${YOUR_SERVER_IP} "docker exec parking-reminder /usr/local/bin/vacation.sh status"
ssh root@${YOUR_SERVER_IP} "docker exec parking-reminder /usr/local/bin/vacation.sh off"

# Test escalation (v2.2.0: ntfy priority escalation)
ssh root@${YOUR_SERVER_IP} "docker exec parking-reminder /usr/local/bin/escalation-1-urgent.sh"
ssh root@${YOUR_SERVER_IP} "docker exec parking-reminder /usr/local/bin/escalation-2-nuclear.sh"

# Test ntfy authentication
curl -u ${NTFY_USER}:${NTFY_PASSWORD} -d "Test" https://${YOUR_NTFY_SERVER}/${YOUR_TOPIC}

# Check healthcheck
curl http://${YOUR_SERVER_IP}:8085/health
```

### View Logs

```bash
# Container logs
ssh root@${YOUR_SERVER_IP} "docker logs -f parking-reminder"

# Application log (reminder.sh output)
ssh root@${YOUR_SERVER_IP} "docker exec parking-reminder tail -f /var/log/parking-reminder/reminder.log"

# Or from host
ssh root@${YOUR_SERVER_IP} "tail -f ${DEPLOYMENT_PATH}/logs/reminder.log"
```

### Check State Files

```bash
# View current acknowledgments
ssh root@${YOUR_SERVER_IP} "docker exec parking-reminder ls -la /var/lib/parking-reminder/"

# Check vacation mode
ssh root@${YOUR_SERVER_IP} "docker exec parking-reminder cat /var/lib/parking-reminder/vacation-mode"
```

### Debug ntfy Issues

```bash
# Check ntfy user exists and has permissions
ssh root@${YOUR_SERVER_IP} "docker exec ntfy-server ntfy user list"

# Verify credentials in container
ssh root@${YOUR_SERVER_IP} "docker exec parking-reminder env | grep NTFY"

# Test ntfy send from container
ssh root@${YOUR_SERVER_IP} "docker exec parking-reminder sh -c 'curl -u \$NTFY_AUTH_USER:\$NTFY_AUTH_PASS -d \"Test\" \$NTFY_SERVER/\$NTFY_TOPIC'"
```

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│  parking-reminder Container (Alpine Linux)                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────────────────┐         │
│  │ cron daemon  │───▶│  reminder.sh             │         │
│  │              │    │  (5:45pm, 6pm, 6:45pm)   │         │
│  │              │    └──────────────────────────┘         │
│  │              │                                           │
│  │              │    ┌──────────────────────────────────┐ │
│  │              │───▶│  escalation-1-urgent.sh (v2.2.0) │ │
│  │              │    │  (6:55pm - priority 5 ntfy)      │ │
│  │              │    └──────────────────────────────────┘ │
│  │              │                                           │
│  │              │    ┌──────────────────────────────────┐ │
│  │              │───▶│  escalation-2-nuclear.sh (v2.2.0)│ │
│  └──────────────┘    │  (7:00pm - 3x ntfy barrage)      │ │
│                      └──────────────────────────────────┘ │
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
         │
         ▼
   ┌──────────┐
   │   ntfy   │  (Priority-based escalation)
   │  Server  │  (Twilio archived - see archive/README.md)
   └──────────┘
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
- **escalation-1-urgent.sh** (v2.2.0): Urgent ntfy escalation at 6:55pm (priority 5) - sources parking-lib.sh
- **escalation-2-nuclear.sh** (v2.2.0): Nuclear ntfy barrage at 7:00pm (3x rapid-fire) - sources parking-lib.sh
- **ack-server.py**: Python HTTP server for webhooks and web UI
- **vacation.sh**: CLI helper for vacation mode
- **cleanup-acks.sh**: Daily cleanup of stale acknowledgment files (3am)
- **status.html**: Mobile web UI (served by ack-server.py)
- **archive/escalation-sms.sh** (archived): Old Twilio SMS escalation (see archive/README.md for restoration)
- **archive/escalation-call.sh** (archived): Old Twilio phone call escalation (see archive/README.md for restoration)

### State Management

State files are created with timestamps in filename: `ack-gotit.1730419200`

Expiration is checked by file age (mtime) rather than deletion at 5:44pm. This prevents race conditions.

## Important Environment Variables

**Required:**
- `NTFY_SERVER`: ntfy server URL (e.g., `https://ntfy.example.com`)
- `NTFY_TOPIC`: ntfy topic name (e.g., `parking`)
- `WEBHOOK_BASE_URL`: Base URL for action buttons (e.g., `http://${YOUR_SERVER_IP}:8085`)

**Authentication (recommended):**
- `NTFY_AUTH_USER`: ntfy username
- `NTFY_AUTH_PASS`: ntfy password

**Optional:**
- `NTFY_FAILSAFE_TOPIC`: Backup topic on cloud ntfy.sh if self-hosted fails
- `UPTIME_KUMA_PUSH_URL`: Heartbeat monitoring

**Archived (v2.2.0 - no longer used):**
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_PHONE`, `TWILIO_TO_PHONE`: Twilio SMS/call escalation (see archive/README.md for restoration)

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
- **6:55pm**: Urgent escalation (priority 5 ntfy notification - if no acknowledgment)
- **7:00pm**: Nuclear escalation (3x rapid-fire ntfy barrage - if still no acknowledgment)

**Smart Acknowledgment Logic:**
- "Got it!" (5:45pm) - Acknowledges warning but keeps 6pm and 6:45pm backups
- "Not home" - Stops ALL notifications (car is with you)
- "I moved it" (6pm) - Stops ALL notifications (task complete)
- "Done!" (6:45pm) - Stops escalation only (already moved)

## Common Issues and Fixes

### Issue: Notifications Not Sending

**Check:**
1. ntfy server is running: `ssh root@${YOUR_SERVER_IP} "docker ps | grep ntfy"`
2. Credentials are correct: Check `NTFY_AUTH_USER` and `NTFY_AUTH_PASS` in `.env`
3. User has topic permissions: `ssh root@${YOUR_SERVER_IP} "docker exec ntfy-server ntfy user list"`
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

### Issue: ntfy Container Fails with "error mounting server.yml"

**Error message**: `Error response from daemon: error mounting server.yml: Are you trying to mount a directory onto a file`

**Cause**: The `server.yml` file was incorrectly created as a directory instead of a file, preventing ntfy-server from starting. This can happen if directory creation commands are run in the wrong order or with incorrect paths.

**Impact**:
- ntfy-server container fails to start
- All parking reminder notifications stop working
- User database may be lost (requires recreation)

**Recovery steps**:

1. **Stop and remove broken container**:
   ```bash
   ssh root@${YOUR_SERVER_IP} "docker stop ntfy-server && docker rm ntfy-server"
   ```

2. **Fix the server.yml file**:
   ```bash
   # Remove the directory
   ssh root@${YOUR_SERVER_IP} "rm -rf ${NTFY_CONFIG_PATH}/server.yml"

   # Recreate as a proper file
   ssh root@${YOUR_SERVER_IP} "cat > ${NTFY_CONFIG_PATH}/server.yml <<'EOF'
   base-url: https://${YOUR_NTFY_DOMAIN}
   listen-http: :80
   cache-file: /var/cache/ntfy/cache.db
   auth-file: /var/cache/ntfy/user.db
   auth-default-access: deny-all
   behind-proxy: true
   EOF"
   ```

3. **Restart ntfy container** (adjust your docker run command as needed):
   ```bash
   ssh root@${YOUR_SERVER_IP} "docker run -d \
     --name ntfy-server \
     --restart unless-stopped \
     -v ${NTFY_CONFIG_PATH}/cache:/var/cache/ntfy \
     -v ${NTFY_CONFIG_PATH}/server.yml:/etc/ntfy/server.yml:ro \
     -p ${NTFY_PORT}:80 \
     binwiederhier/ntfy:latest serve"
   ```

4. **Recreate ntfy users** (if database was lost):
   ```bash
   # Create user account
   ssh root@${YOUR_SERVER_IP} "docker exec ntfy-server ntfy user add ${NTFY_USERNAME}"
   # Enter password when prompted

   # Grant permissions to parking topic
   ssh root@${YOUR_SERVER_IP} "docker exec ntfy-server ntfy access ${NTFY_USERNAME} ${NTFY_TOPIC} rw"

   # Verify user exists
   ssh root@${YOUR_SERVER_IP} "docker exec ntfy-server ntfy user list"
   ```

5. **Test notification system**:
   ```bash
   # Test from container
   ssh root@${YOUR_SERVER_IP} "docker exec parking-reminder sh -c 'curl -u \$NTFY_AUTH_USER:\$NTFY_AUTH_PASS -d \"Test after recovery\" \$NTFY_SERVER/\$NTFY_TOPIC'"

   # Or test directly
   curl -u ${NTFY_USERNAME}:${NTFY_PASSWORD} -d "Test" https://${YOUR_NTFY_DOMAIN}/${NTFY_TOPIC}
   ```

**Prevention**:
- Always verify directory structure before creating configuration files
- Use `ls -la` to check if paths exist and are correct type (file vs directory)
- Back up working configuration before making changes
- Document the correct docker run command for ntfy container

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
- Configure ntfy authentication in `.env` file
- Twilio SMS/Voice escalation: Optional (requires Twilio account)

**Important**: `.env` file contains credentials - never commit to git!

## Deployment URLs

**Production:**
- Web UI: https://parking.${YOUR_DOMAIN} (Optional: Authelia SSO protected)
- Webhook Base: http://${YOUR_SERVER_IP}:8085 (internal)
- ntfy Server: https://ntfy.${YOUR_DOMAIN}

**Authentication (if using Authelia):**
- Authelia: one_factor (password only, no 2FA)
- Session cookie domain: `${YOUR_DOMAIN}`
- Auth URL: https://auth.${YOUR_DOMAIN}

## Development Workflow

**Production deployment can use Git for easy updates.**

### Quick Deploy Workflow

1. Make changes locally in your project directory
2. Commit and push to GitHub:
   ```bash
   git add .
   git commit -m "Description of changes"
   git push
   ```
3. Deploy to production (one command):
   ```bash
   ssh root@${YOUR_SERVER_IP} "cd ${DEPLOYMENT_PATH} && \
     git pull && \
     docker build -t parking-reminder:2.2.0 . && \
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
       -e UPTIME_KUMA_PUSH_URL=\"\$UPTIME_KUMA_PUSH_URL\" \
       --log-opt max-size=10m \
       --log-opt max-file=3 \
       parking-reminder:2.2.0"
   ```

### Git Setup Details

- **Server directory**: `${DEPLOYMENT_PATH}` can be a git clone
- **Remote**: Your GitHub repository
- **Branch**: `master`

### Important Notes

- `.env` file is **not** in git (contains secrets)
- `state/` and `logs/` directories are **not** in git (runtime data)
- These are preserved across git pulls via `.gitignore`
- To verify git status on server: `ssh root@${YOUR_SERVER_IP} "cd ${DEPLOYMENT_PATH} && git status"`

## Known Issues & Future Improvements

**Verified Production Status:**
- ✅ All pre-flight checks pass
- ✅ Container running v2.0.2+ with correct environment variables
- ✅ Cron daemon running, timezone correct (America/New_York)
- ✅ ntfy authentication working, notifications delivering
- ✅ Healthcheck comprehensive (tests cron, directories, env vars)

**v2.3.0 Improvements (Completed):**

✅ **All Critical Issues Resolved**
- Atomic ack file creation with O_CREAT|O_EXCL flags
- fsync for persistence guarantees
- Comprehensive error handling and logging
- HTTP→Bash race condition eliminated (double-check pattern)
- Vacation mode TOCTOU fixed
- Status button double-click prevention
- Clock drift detection in healthcheck
- Comprehensive test suite (44 test cases)
- Constants centralized in parking-lib.sh
- Vacation mode auto-expiration implemented
- Metrics logging for observability

**Remaining Technical Debt (Low Priority):**

1. **Failsafe Notification Limited**
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

## Disaster Recovery & Backup Strategy

**Critical Files to Backup:**

1. **ntfy Server Configuration** (Priority: HIGH)
   - Location: `${NTFY_CONFIG_PATH}` (e.g., `/path/to/ntfy-server/`)
   - Files:
     - `server.yml` - Server configuration
     - `cache/user.db` - User accounts and permissions
     - `cache/cache.db` - Message cache (optional, can be recreated)
   - Backup command:
     ```bash
     ssh root@${YOUR_SERVER_IP} "tar -czf ${BACKUP_PATH}/ntfy-backup-$(date +%Y%m%d).tar.gz \
       ${NTFY_CONFIG_PATH}/server.yml \
       ${NTFY_CONFIG_PATH}/cache/user.db"
     ```

2. **Parking Reminder State** (Priority: MEDIUM)
   - Location: `${DEPLOYMENT_PATH}/state/`
   - Files:
     - `ack-*` files - Acknowledgment state (expire daily)
     - `vacation-mode` - Vacation status (if enabled)
   - Note: State files are ephemeral and reset daily. Loss is not critical.

3. **Environment Variables** (Priority: HIGH)
   - Location: `${DEPLOYMENT_PATH}/.env`
   - Contains:
     - ntfy credentials
     - Twilio API keys
     - Webhook URLs
   - **DO NOT** commit to git (contains secrets)
   - Backup to secure location (password manager, encrypted USB)
   - Example secure backup:
     ```bash
     # Copy to encrypted location (example)
     ssh root@${YOUR_SERVER_IP} "cat ${DEPLOYMENT_PATH}/.env" > ~/secure-backup/.env.parking-reminder
     ```

4. **Docker Run Commands** (Priority: HIGH)
   - Document exact `docker run` commands for both containers
   - Store in CLAUDE.local.md file (private, not committed)
   - Needed for quick recreation after failure

**Recovery Procedures:**

### Scenario 1: ntfy Container Lost (Database Intact)

If container is removed but files remain:

```bash
# Recreate container using documented docker run command
ssh root@${YOUR_SERVER_IP} "docker run -d \
  --name ntfy-server \
  --restart unless-stopped \
  -v ${NTFY_CONFIG_PATH}/cache:/var/cache/ntfy \
  -v ${NTFY_CONFIG_PATH}/server.yml:/etc/ntfy/server.yml:ro \
  -p ${NTFY_PORT}:80 \
  binwiederhier/ntfy:latest serve"

# Verify users preserved
ssh root@${YOUR_SERVER_IP} "docker exec ntfy-server ntfy user list"
```

### Scenario 2: ntfy Database Lost (see "Issue: ntfy Container Fails" above)

Complete recovery steps documented in Common Issues section.

### Scenario 3: Parking Reminder Container Lost

```bash
# Pull latest code
ssh root@${YOUR_SERVER_IP} "cd ${DEPLOYMENT_PATH} && git pull"

# Rebuild and run (see "Deploy on Server" section for full command)
ssh root@${YOUR_SERVER_IP} "cd ${DEPLOYMENT_PATH} && docker build -t parking-reminder:2.2.0 ."
# Then run the documented docker run command
```

### Scenario 4: Complete Server Failure

1. Restore from server backup (if configured)
2. Or rebuild from scratch:
   - Clone Git repo to `${DEPLOYMENT_PATH}`
   - Restore `.env` from secure backup
   - Restore ntfy `server.yml` and `user.db` from backup
   - Run docker commands to recreate containers

**Backup Automation (Optional):**

Create a cron job to backup critical files weekly:

```bash
# Add to server crontab
0 3 * * 0 tar -czf ${BACKUP_PATH}/parking-reminder-backup-$(date +\%Y\%m\%d).tar.gz \
  ${NTFY_CONFIG_PATH}/server.yml \
  ${NTFY_CONFIG_PATH}/cache/user.db \
  ${DEPLOYMENT_PATH}/.env
```

**Testing Recovery:**

Periodically test recovery process (quarterly):

1. Stop containers
2. Rename data directories (backup)
3. Attempt full recovery from backups
4. Verify notifications work
5. Restore or clean up test environment

**Last Verified**: 2025-11-10 (after ntfy server.yml incident)

## Roadmap / Future Enhancements

### Context-Aware Status Notifications ✅ **IMPLEMENTED in v2.1.1**
**Status:** ✅ **COMPLETE** - Deployed in v2.1.1
**Priority:** Medium (UX improvement)
**Complexity:** Low
**File:** `status-notify.sh`

**Original Problem:**
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

---

### Progressive Web App (PWA) Enhancement
**Priority:** Medium (family adoption + polish)
**Complexity:** Low-Medium (4-5 hours on a day off)
**Files:** `status.html`, new `manifest.json`, new `service-worker.js`

**Motivation:**
Currently a "developer's tool" - functional but not polished for family use. PWA would make it look/feel like a real app, making it more appealing for others to adopt.

**What It Adds:**
1. **Installable app** - "Add to Home Screen" creates app icon on Android/iOS
2. **Fullscreen experience** - No browser chrome, looks native
3. **Better mobile UI**:
   - Larger touch targets (easier thumb access)
   - Improved visual design (modern, clean)
   - Dark mode support
   - Pull-to-refresh
   - Loading states and animations
   - Haptic feedback on button presses
4. **Offline support** - Service worker caches UI (backend still requires connection)
5. **Progressive enhancement** - Works as regular website OR installed app

**Implementation Plan:**

1. **Enhance status.html** (2 hours):
   ```html
   <!-- Add PWA meta tags -->
   <meta name="viewport" content="width=device-width, initial-scale=1">
   <meta name="theme-color" content="#2196F3">
   <link rel="manifest" href="/manifest.json">
   <link rel="apple-touch-icon" href="/icon-192.png">

   <!-- Better CSS -->
   - Card-based layout
   - Material Design principles
   - Bigger buttons (min 48x48dp touch targets)
   - Better spacing and typography
   - Dark mode with prefers-color-scheme
   ```

2. **Create manifest.json** (15 minutes):
   ```json
   {
     "name": "Parking Reminder",
     "short_name": "Parking",
     "description": "Never get a parking ticket again",
     "start_url": "/",
     "display": "standalone",
     "background_color": "#ffffff",
     "theme_color": "#2196F3",
     "icons": [
       {
         "src": "/icon-192.png",
         "sizes": "192x192",
         "type": "image/png"
       },
       {
         "src": "/icon-512.png",
         "sizes": "512x512",
         "type": "image/png"
       }
     ]
   }
   ```

3. **Add service-worker.js** (1 hour):
   ```javascript
   // Cache UI assets for offline viewing
   const CACHE_NAME = 'parking-reminder-v1';
   const urlsToCache = ['/', '/status.html', '/manifest.json'];

   self.addEventListener('install', event => {
     event.waitUntil(
       caches.open(CACHE_NAME)
         .then(cache => cache.addAll(urlsToCache))
     );
   });

   self.addEventListener('fetch', event => {
     event.respondWith(
       caches.match(event.request)
         .then(response => response || fetch(event.request))
     );
   });
   ```

4. **Add JavaScript interactivity** (1-2 hours):
   ```javascript
   // Auto-refresh status every 30 seconds
   // Smooth animations on button press
   // Toast notifications for success/error
   // Haptic feedback (if supported)
   // Loading states
   ```

5. **Create app icons** (30 minutes):
   - Design simple parking icon (or use emoji-based: 🚗)
   - Export as 192x192 and 512x512 PNG
   - Add to project

6. **Update ack-server.py** (30 minutes):
   - Serve manifest.json
   - Serve service-worker.js
   - Serve icon files
   - Add proper MIME types

**Testing:**
1. Load status.html on Android Chrome
2. Menu → "Add to Home Screen"
3. Verify icon appears on launcher
4. Tap icon → opens fullscreen (no browser UI)
5. Test all buttons work
6. Enable airplane mode → verify UI still loads (backend calls fail gracefully)

**Benefits:**
- ✅ Looks like a "real app" (family more likely to use it)
- ✅ Easy to access (home screen icon, not buried in bookmarks)
- ✅ Works on Android AND iOS (one codebase)
- ✅ No app store approval needed
- ✅ All backend logic stays unchanged (bash/Python on server)
- ✅ Quick project (one afternoon/evening)
- ✅ Good learning opportunity (PWA is a useful skill)

**Trade-offs:**
- ❌ Still requires internet (not fully offline)
- ❌ Not a "native" app (but 99% of users won't notice)
- ❌ Limited background capabilities (can't replace cron-based reminders)

**Use Case:**
- Primary user continues using ntfy notifications + web UI
- Family members can install PWA on their phones
- Each user subscribes to ntfy topic on their device
- Everyone gets reminders, can acknowledge from their phone
- Multi-user support already works (ntfy is broadcast, ack files are shared)

**Future Extensions:**
- User accounts (if family wants separate cars/schedules)
- Push notifications via service worker (supplement ntfy)
- Geofencing (detect when you're near home)
- Integration with calendar (auto-vacation mode)

**Decision:** Wait until v2.2.0 or later. Current system works well for single user. Revisit when family adoption becomes priority.
