# Parking Reminder v2.0.1

Automated parking reminder system to prevent street parking tickets. Never pay $50 for forgetting to move your car again!

## What's New in v2.0.1 (Security Release)

This version fixes **34 critical security and reliability issues** found in v2.0. All bash scripts have been hardened.

**Critical Fixes:**
- ✅ **No more backdoor**: Replaced insecure netcat (`nc -e /bin/bash`) with secure Python HTTP server
- ✅ **No command injection**: Fixed unquoted variables in curl auth
- ✅ **Fixed acknowledgment logic**: "Got it!" now correctly keeps backup notifications
- ✅ **No race conditions**: Atomic lock files, timestamp-based acknowledgment expiration
- ✅ **No blocking operations**: Split escalation into separate cron jobs (no `sleep 300`)
- ✅ **Proper time handling**: Fixed string vs arithmetic comparison bugs
- ✅ **XML escaping**: TwiML properly escaped to prevent injection
- ✅ **Environment validation**: Container won't start with missing config
- ✅ **Dynamic URLs**: No hardcoded IPs in action buttons

See [FIXES.md](FIXES.md) for complete list of all 34 fixes.

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
NTFY_FAILSAFE_TOPIC=parking_cooley_RANDOM
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
├── reminder.sh            # Main notification logic (FIXED)
├── ack-server.py          # Secure Python HTTP server (NEW)
├── status.html            # Mobile web UI
├── status-notify.sh       # On-demand status (FIXED)
├── escalation-sms.sh      # SMS escalation only (NEW)
├── escalation-call.sh     # Phone call escalation only (NEW)
├── vacation.sh            # CLI vacation helper
├── .gitignore             # Git exclusions
├── FIXES.md               # Security fixes documentation (NEW)
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
