# Documentation Drift

This file lists inconsistencies found during the discovery pass. It intentionally does not fix them, because this branch is documentation/planning only.

## README Version Drift

- `README.md` title says `Parking Reminder v2.2.0`, but live files include later versions:
  - `ack-server.py` says v2.4.0 with PWA support.
  - `status.html` footer says v2.4.0.
  - `entrypoint.sh` says v2.3.0.
  - `vacation-lib.sh` says v2.3.0.
  - `FEATURES.md` lists v2.4.0 PWA implementation as complete.
- `README.md` "What's New" still centers v2.2.0 even though the current tree includes v2.3.0 and v2.4.0 behavior.
- `README.md` roadmap says context-aware status notifications are planned, but `status-notify.sh` already implements time-aware status messages and `FEATURES.md` marks them complete.

## README Twilio Drift

Current active runtime is ntfy-only for escalation. Twilio scripts are archived and not scheduled.

Stale or conflicting README items:

- Problem summary says the system "escalates to SMS/phone calls if needed."
- Feature list says `SMS/Phone Escalation: Twilio integration for 6:55pm SMS, 7:00pm call`.
- Architecture diagram includes a live `Twilio API (SMS + Voice)` box.
- Prerequisites say Twilio account is optional for SMS/phone escalation.
- Deployment section asks for optional Twilio configuration.
- File structure lists `escalation-sms.sh` and `escalation-call.sh` at repo root, but they are under `archive/`.
- Notification schedule says `6:55pm - SMS escalation` and `7:00pm - Phone call`; current cron runs ntfy urgent and ntfy nuclear escalation.
- Troubleshooting "Escalation Not Triggering" tells the user to verify Twilio credentials and run `/usr/local/bin/escalation.sh`; current active scripts are `escalation-1-urgent.sh` and `escalation-2-nuclear.sh`.
- Security considerations still mention Twilio credentials.
- Failsafe list says `Escalation Chain: SMS -> Phone call if no acknowledgment`; current chain is ntfy urgent -> ntfy three-message barrage.
- Credits still list Twilio as an active SMS/Voice dependency.

Notes:

- `archive/README.md` correctly explains that Twilio scripts were archived and can be restored.
- `docker-compose.yml` and `.env.example` still expose `TWILIO_*` variables even though active scripts do not consume them.
- `requirements.txt` still includes `twilio==8.10.0`, but the Dockerfile does not install `requirements.txt` and the active runtime does not import Twilio.

## README Schedule Drift

- `README.md` says acknowledgment cleanup happens at 5:44pm; current `crontab` runs `cleanup-acks.sh` daily at 3:00am.
- `README.md` says "These files are automatically cleaned at 5:44pm daily"; current cleanup is 3:00am daily.
- `README.md` v1 history mentions four daily reminders including 4pm; current cron has no 4pm reminder, which is fine historically but can confuse readers when combined with current schedule text.
- `README.md` says Docker healthcheck runs every 5 minutes; current Dockerfile healthcheck interval is 30 seconds.
- `README.md` says the 7:00pm ntfy barrage is 20 seconds apart in the v2.2.0 section; current `escalation-2-nuclear.sh` sleeps 30 seconds between notifications.

## README State File Drift

- `README.md` lists ack files as `ack-gotit`, `ack-nothome`, `ack-moved`, and `ack-done`.
- Current ack files are timestamped: `ack-gotit.TIMESTAMP`, `ack-nothome.TIMESTAMP`, `ack-moved.TIMESTAMP`, and `ack-done.TIMESTAMP`.
- Current ack validity is based on the timestamp embedded in the filename.
- Current ack files expire after 4 hours and can include decimal microsecond timestamps.

## README Customization Drift

- `README.md` says parking side logic should be changed in `reminder.sh` and `status-notify.sh`.
- Current shared parking side logic lives in `parking-lib.sh`.
- Future docs should direct rule changes to `calculate_parking_sides()` in `parking-lib.sh` until the FastAPI rewrite exists.

## Requirements And App Package Drift

- `requirements.txt` lists Flask, APScheduler, requests, Twilio, python-dotenv, Flask-WTF, and gunicorn.
- Current Dockerfile does not install Python requirements.
- Current active Python server uses only the standard library.
- `app/config.py` appears to belong to an unused Flask-style app and still validates Twilio configuration.
- `app/config.py` includes `DATABASE_PATH=/var/lib/parking-reminder/parking.db`, but the current runtime has no active database.

## FEATURES.md Drift

- `FEATURES.md` says testing includes a "44-test comprehensive suite."
- The visible test file is `tests/test-ack-system.sh`, whose header says 42 test cases.
- Some test assertions in `tests/test-ack-system.sh` appear stale relative to current function signatures:
  - It calls `calculate_parking_sides` but asserts `CURRENT_SIDE` and `DESTINATION_SIDE`, while the current function prints two words and does not set those variables.
  - It expects some dotted timestamp forms to be rejected that the current `has_ack()` implementation may parse differently because it cuts on `.` and supports decimals.
- This branch did not run or fix tests because the requested scope is documentation/planning only.

## Version Notes Across Files

Observed version labels are inconsistent:

- `README.md`: v2.2.0.
- `reminder.sh`: v2.1.2.
- `status-notify.sh`: v2.1.1.
- `escalation-1-urgent.sh`: v2.2.0.
- `escalation-2-nuclear.sh`: v2.2.0.
- `entrypoint.sh`: v2.3.0.
- `vacation-lib.sh`: v2.3.0.
- `ack-server.py`: v2.4.0.
- `status.html`: v2.4.0 footer.
- `.env.example`: v2.0.1.
- `FEATURES.md`: generated from v2.3.0 but includes v2.4.0 complete.

Recommendation for the eventual rewrite:

- Replace per-file version banners with one project version source.
- Keep behavior docs separate from changelog/version history.
- Treat archived Twilio behavior as historical, not active production behavior.
