# Archived Twilio Escalation Scripts

**Archive Date:** 2025-11-11
**Version:** v2.2.0
**Reason:** Replaced Twilio SMS/call with ntfy priority escalation (simpler, no external API)

## What's Archived

- `escalation-sms.sh` - Sent SMS at 6:55pm via Twilio
- `escalation-call.sh` - Made phone call at 7:00pm via Twilio

These scripts have been **replaced** with:
- `escalation-1-urgent.sh` - Sends max-priority ntfy notification (6:55pm)
- `escalation-2-nuclear.sh` - Sends triple rapid-fire ntfy barrage (7:00pm)

## Why the Change?

**Problems with Twilio:**
- Requires external API account and credentials
- Verification challenges (Twilio treats everyone like scammers)
- Additional complexity and maintenance
- SMS/call costs (minimal but annoying)

**Benefits of ntfy Priority Escalation:**
- No external dependencies (self-hosted)
- Priority 5 notifications bypass silent mode on Android
- Triple barrage forces multiple alert cycles (hard to ignore)
- Free, simple, already part of infrastructure
- Easier to test and debug

## How to Restore Twilio (If Needed)

If ntfy escalation doesn't work well and you want to bring back SMS/phone calls:

### Step 1: Copy Scripts Back

```bash
cp archive/escalation-sms.sh .
cp archive/escalation-call.sh .
```

### Step 2: Update Dockerfile

Edit `Dockerfile` and add these lines after `parking-lib.sh`:

```dockerfile
COPY escalation-sms.sh /usr/local/bin/escalation-sms.sh
COPY escalation-call.sh /usr/local/bin/escalation-call.sh
```

### Step 3: Update Crontab

Edit `crontab` and **uncomment** the archived lines:

```cron
# Restore these lines:
55 18 * * 1-6 /usr/local/bin/escalation-sms.sh   # 6:55pm SMS
0  19 * * 1-6 /usr/local/bin/escalation-call.sh  # 7:00pm phone call

# Comment out or remove:
# 55 18 * * 1-6 /usr/local/bin/escalation-1-urgent.sh
# 0  19 * * 1-6 /usr/local/bin/escalation-2-nuclear.sh
```

### Step 4: Add Twilio Environment Variables

In your `.env` file, ensure these are set:

```bash
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_PHONE=+1234567890
TWILIO_TO_PHONE=+1234567890
```

### Step 5: Update Docker Run Command

Add Twilio variables back to docker run command:

```bash
-e TWILIO_ACCOUNT_SID="$TWILIO_ACCOUNT_SID" \
-e TWILIO_AUTH_TOKEN="$TWILIO_AUTH_TOKEN" \
-e TWILIO_FROM_PHONE="$TWILIO_FROM_PHONE" \
-e TWILIO_TO_PHONE="$TWILIO_TO_PHONE" \
```

### Step 6: Rebuild and Deploy

```bash
docker build -t parking-reminder:2.2.0 .
docker stop parking-reminder && docker rm parking-reminder
# Run your docker run command with Twilio env vars
```

## Hybrid Option

You can run **both** ntfy and Twilio escalation if you want redundancy:

1. Keep both sets of scripts in Dockerfile
2. Stagger cron times to avoid duplicate alerts:
   ```cron
   55 18 * * 1-6 /usr/local/bin/escalation-1-urgent.sh  # 6:55pm ntfy
   57 18 * * 1-6 /usr/local/bin/escalation-sms.sh       # 6:57pm SMS
   0  19 * * 1-6 /usr/local/bin/escalation-2-nuclear.sh # 7:00pm ntfy barrage
   2  19 * * 1-6 /usr/local/bin/escalation-call.sh      # 7:02pm phone call
   ```

This gives you 4 escalation stages over 7 minutes (overkill but bulletproof).

## Testing Before Committing

After restoring, test manually:

```bash
# Test SMS
docker exec parking-reminder /usr/local/bin/escalation-sms.sh

# Test phone call
docker exec parking-reminder /usr/local/bin/escalation-call.sh
```

## Version History

- **v2.2.0** (2025-11-11): Archived Twilio, switched to ntfy priority escalation
- **v2.1.2** (2025-11-04): Twilio scripts active and working
- **v2.0.2** (2025-11-01): Twilio scripts added with retry logic

---

**Note:** These scripts are fully functional and tested. They were removed for simplicity, not because of bugs or issues.
