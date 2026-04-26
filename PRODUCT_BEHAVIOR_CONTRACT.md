# Product Behavior Contract

This document captures the behavior shipped by the current Docker/Bash/Python implementation. It is a contract for a future rewrite: preserve these externally visible behaviors unless a later product decision explicitly changes them.

## Current Runtime Shape

The app is a self-hosted parking reminder service packaged as one Docker container.

- Cron runs scheduled Bash jobs.
- `reminder.sh` sends normal evening reminders.
- `escalation-1-urgent.sh` and `escalation-2-nuclear.sh` send ntfy-only escalations.
- `ack-server.py` serves the small web UI, acknowledgment endpoints, vacation endpoints, static PWA files, and `/health`.
- `parking-lib.sh` owns shared parking side calculation, Sunday detection, ack lookup, and constants.
- `vacation-lib.sh` adds vacation auto-expiration for Bash jobs and the CLI helper.
- State is file-based under `/var/lib/parking-reminder`.
- Logs are appended under `/var/log/parking-reminder`.

## Parking Side Rules

Parking alternates by weekday. The app describes the side where the car is currently expected to be parked and the side it must move to during the 6-7pm window.

| Day | Current side | Destination side |
| --- | --- | --- |
| Monday | AWAY | HOUSE |
| Tuesday | HOUSE | AWAY |
| Wednesday | AWAY | HOUSE |
| Thursday | HOUSE | AWAY |
| Friday | AWAY | HOUSE |
| Saturday | HOUSE | AWAY |
| Sunday | No move required | No move required |

Implementation notes:

- `calculate_parking_sides()` returns `AWAY HOUSE` for Monday, Wednesday, and Friday.
- `calculate_parking_sides()` returns `HOUSE AWAY` for all other numeric days unless the caller performs a Sunday guard first.
- Scheduled reminders and escalations are cron-limited to Monday through Saturday.
- `reminder.sh` also exits early on Sunday.
- `status-notify.sh` has a Sunday-specific message.
- Escalation scripts do not contain their own Sunday guard; they rely on cron for normal operation.

## Sunday Behavior

Sunday is a no-move day.

- Scheduled reminders do not run on Sunday because the reminder cron entries use day-of-week `1-6`.
- If `reminder.sh` is run manually on Sunday, it logs that Sunday was detected and exits without sending a notification.
- If the status button is pressed on Sunday, `status-notify.sh` sends a ntfy status message saying no parking moves are needed.
- Cleanup still runs on Sunday at 3:00am because stale ack cleanup is daily.
- Vacation mode is still visible and toggleable on Sunday.

## Reminder Schedule

All scheduled move reminders and escalations are intended for the America/New_York timezone. The Dockerfile sets `TZ=America/New_York`, and Docker Compose also provides that default.

Current crontab:

| Time | Days | Script | Behavior |
| --- | --- | --- | --- |
| 3:00am | Daily | `cleanup-acks.sh` | Deletes stale or malformed acknowledgment files. |
| 5:45pm | Mon-Sat | `reminder.sh` | First warning. |
| 6:00pm | Mon-Sat | `reminder.sh` | Urgent move-now reminder. |
| 6:45pm | Mon-Sat | `reminder.sh` | Last-call reminder. |
| 6:55pm | Mon-Sat | `escalation-1-urgent.sh` | Max-priority ntfy escalation if no valid ack exists. |
| 7:00pm | Mon-Sat | `escalation-2-nuclear.sh` | Three max-priority ntfy notifications if no valid ack exists. |

`reminder.sh` uses small time windows, not exact-minute equality:

- 5:45pm reminder window: `17:45` through `17:47`.
- 6:00pm reminder window: `18:00` through `18:02`.
- 6:45pm reminder window: `18:45` through `18:47`.
- Outside those windows, `reminder.sh` logs that the current time is not scheduled and exits.

The old 4:00pm reminder is not in the current crontab. It has been replaced by the on-demand status button.

## Acknowledgment Types And Semantics

Acknowledgments are represented by timestamped files in `/var/lib/parking-reminder`.

| Ack type | Created by | User meaning | File pattern |
| --- | --- | --- | --- |
| `gotit` | 5:45pm "Got it!" button | User saw the warning but has not necessarily moved the car. | `ack-gotit.TIMESTAMP` |
| `nothome` | Any "Not home" button | User is not home or car is with them; stop reminders/escalations. | `ack-nothome.TIMESTAMP` |
| `moved` | 6:00pm "I moved it" button | User moved the car; stop later reminders/escalations. | `ack-moved.TIMESTAMP` |
| `done` | 6:45pm and escalation "Done"/"I moved it" buttons | User indicates the task is complete; suppress last-call/escalation flows. | `ack-done.TIMESTAMP` |

Acknowledgment endpoints:

- `GET /ack/gotit` and `POST /ack/gotit`
- `GET /ack/nothome` and `POST /ack/nothome`
- `GET /ack/moved` and `POST /ack/moved`
- `GET /ack/done` and `POST /ack/done`

Endpoint behavior:

- Both GET and POST create ack files.
- ntfy action buttons use GET and are supported directly.
- The server responds with plain text: `Acknowledged: TYPE`.
- Acks are created atomically with `O_CREAT|O_EXCL`.
- Ack filenames use `datetime.now().timestamp()` and may contain decimal microseconds.
- If there is a timestamp collision, `time.time_ns()` is used as a fallback.
- Ack file contents are empty; the filename is the source of truth.

Ack validity:

- A valid ack file must match `ack-TYPE.TIMESTAMP`.
- Timestamp may be an integer or decimal number.
- The timestamp is parsed from the filename, not file mtime.
- Acks are valid for 14,400 seconds, which is 4 hours.
- Acks up to 5 minutes in the future are accepted to tolerate clock skew.
- Expired or malformed files do not count.
- `cleanup-acks.sh` deletes files older than 4 hours and deletes malformed ack files.

## Suppression Matrix

The current app intentionally treats ack types differently at different stages.

| Stage | `gotit` | `nothome` | `moved` | `done` |
| --- | --- | --- | --- | --- |
| 5:45pm reminder | Suppresses | Suppresses | Not checked | Not checked |
| 6:00pm reminder | Does not suppress | Suppresses | Suppresses | Not checked |
| 6:45pm reminder | Does not suppress | Suppresses | Suppresses | Suppresses |
| 6:55pm urgent escalation | Suppresses | Suppresses | Suppresses | Suppresses |
| 7:00pm nuclear escalation | Suppresses | Suppresses | Suppresses | Suppresses |
| Status button | No effect | No effect | No effect | No effect |

Additional race-reduction behavior:

- Before each normal reminder sends, `reminder.sh` checks the relevant ack files.
- After constructing the message and action payload, it checks the same relevant ack files again immediately before sending.
- `escalation-2-nuclear.sh` checks for all ack types before starting, then again after the first notification and after the second notification. Any valid ack stops the remaining barrage.

Important behavior to preserve:

- `gotit` suppresses duplicate 5:45pm warnings and suppresses escalations, but it does not suppress the 6:00pm or 6:45pm reminders.
- `nothome` is the broadest user-driven stop signal.
- `moved` stops 6:00pm, 6:45pm, and escalations.
- `done` stops 6:45pm and escalations, but is not checked by the 6:00pm reminder.

## Vacation Mode

Vacation mode pauses scheduled reminders and escalations.

State file:

- `/var/lib/parking-reminder/vacation-mode`

Bash behavior:

- `reminder.sh`, `escalation-1-urgent.sh`, and `escalation-2-nuclear.sh` source `vacation-lib.sh`.
- If vacation mode is active, those scripts exit before sending notifications.
- Cleanup still runs while vacation mode is enabled.

Vacation file contents:

- If the file is missing, vacation mode is disabled.
- If the file exists and contains no valid timestamp, vacation mode is treated as enabled indefinitely.
- If the file contains a Unix timestamp in the future, vacation mode is enabled until that timestamp.
- If the file contains a Unix timestamp in the past, `vacation-lib.sh` removes the file and treats vacation mode as disabled.

CLI behavior:

- `./vacation.sh on` enables vacation mode for 7 days by default.
- `./vacation.sh on DAYS` enables vacation mode for a positive integer number of days.
- `./vacation.sh off` disables vacation mode.
- `./vacation.sh status` reports disabled, enabled until a timestamp, expired, or enabled indefinitely.
- The CLI requires a running Docker container named `parking-reminder` and runs commands through `docker exec`.

Web UI behavior:

- `GET /vacation/status` and `GET /api/vacation/status` return JSON `{"enabled": true|false}` based only on whether the vacation file exists.
- `POST /vacation/toggle` and `POST /api/vacation/toggle` toggle the file on or off.
- The Python web toggle creates an empty vacation file with no expiration, so web-enabled vacation mode is indefinite until toggled off.
- The Python status endpoint does not evaluate expiration timestamps; expiration is enforced when Bash jobs source `vacation-lib.sh`.

## Status Button Behavior

The home page has a `Where Do I Park?` form that posts to `/status`.

Server behavior:

- `POST /status` starts `/usr/local/bin/status-notify.sh` in the background.
- The request redirects back to `/`.
- A status-specific rate limiter allows 1 status request per 5 seconds per client IP.
- General request rate limiting also applies.

Notification behavior:

- On Sunday, the status notification says no parking moves are needed.
- Before 6:00pm on non-Sunday days, it sends the current side and destination side with the 6-7pm window.
- From 6:00pm through 6:59pm, it sends an urgent instruction to park on the destination side before the 7pm close.
- At 7:00pm and later, it sends a confirmation-style message saying the car should now be on the destination side.
- The status notification uses ntfy title `Parking Status`, priority `high`, and tags `information_source,car`.
- Status notifications require `NTFY_SERVER` and `NTFY_TOPIC`.
- If both `NTFY_AUTH_USER` and `NTFY_AUTH_PASS` are present, status notifications use basic auth.

## ntfy Notification Behavior

All active user notifications are sent through ntfy via `curl`.

Required for normal operation:

- `NTFY_SERVER`
- `NTFY_TOPIC`

Optional:

- `NTFY_AUTH_USER` and `NTFY_AUTH_PASS` enable basic auth when both are set.
- `NTFY_FAILSAFE_TOPIC` enables selected backup messages to cloud `https://ntfy.sh`.
- `UPTIME_KUMA_PUSH_URL` enables a push heartbeat after successful normal reminder sends.

Normal reminder messages:

| Stage | Title | Priority | Tags | Actions |
| --- | --- | --- | --- | --- |
| 5:45pm | `Parking Reminder` | `high` | `warning,car` | `Got it!` -> `/ack/gotit`; `Not home` -> `/ack/nothome` |
| 6:00pm | `Parking Reminder` | `urgent` | `rotating_light,car` | `I moved it` -> `/ack/moved`; `Not home` -> `/ack/nothome` |
| 6:45pm | `Parking Reminder` | `urgent` | `rotating_light,sos` | `Done!` -> `/ack/done`; `Not home` -> `/ack/nothome` |

Normal reminder delivery:

- `reminder.sh` retries up to 3 times.
- Each attempt has a 10-second curl timeout.
- There is a 2-second sleep between failed attempts.
- If all attempts fail and `NTFY_FAILSAFE_TOPIC` is set, the script posts a backup alert to `https://ntfy.sh/$NTFY_FAILSAFE_TOPIC`.
- If a normal reminder sends successfully and `UPTIME_KUMA_PUSH_URL` is set, the script calls that URL with `status=up` and the reminder type.

Webhook action URL behavior:

- Normal reminders require `WEBHOOK_BASE_URL`.
- `WEBHOOK_BASE_URL` must match `http://host[:port]` or `https://host[:port]`.
- No trailing slash is expected.
- Quotes and braces are rejected to avoid JSON/action injection.

## Escalation Behavior

Current escalation is ntfy-only. Twilio SMS and phone scripts exist only under `archive/` and are not copied into the image or scheduled by current cron.

### 6:55pm Urgent Escalation

`escalation-1-urgent.sh` runs at 6:55pm Monday through Saturday.

Behavior:

- Exits if vacation mode is active.
- Exits if any valid ack exists for `nothome`, `gotit`, `moved`, or `done`.
- Calculates current and destination side.
- Requires `NTFY_SERVER` and `NTFY_TOPIC`.
- Uses `WEBHOOK_BASE_URL` if set, otherwise falls back to `http://localhost:8085`.
- Sends one ntfy notification with priority `5`.
- Title: `PARKING EMERGENCY - 5 MIN LEFT` with leading alert emoji in the live script.
- Tags: `rotating_light,alarm,warning`.
- Actions: "I'M MOVING IT NOW" -> `/ack/done`; "Not home" -> `/ack/nothome`.
- Retries up to 3 times, 10-second curl timeout, 2-second sleep between failed attempts.
- If successful and `NTFY_FAILSAFE_TOPIC` is set, posts an informational backup message to cloud ntfy.

### 7:00pm Nuclear Escalation

`escalation-2-nuclear.sh` runs at 7:00pm Monday through Saturday.

Behavior:

- Exits if vacation mode is active.
- Exits if any valid ack exists for `nothome`, `gotit`, `moved`, or `done`.
- Calculates current and destination side.
- Requires `NTFY_SERVER` and `NTFY_TOPIC`.
- Sends up to 3 max-priority ntfy notifications.
- Each notification uses priority `5`, tags `rotating_light,fire,sos,warning`, and actions for `/ack/done` and `/ack/nothome`.
- There is a 30-second sleep after the first notification and after the second notification.
- After each of those sleeps, it checks all ack types again and stops if any valid ack exists.
- After the final notification, it sends a cloud ntfy failsafe summary if `NTFY_FAILSAFE_TOPIC` is set.
- Exit code is `0` if all or some notifications sent successfully, `1` only if all three sends failed.

## Healthcheck Behavior

Docker healthcheck:

- Runs every 30 seconds.
- Timeout is 5 seconds.
- Start period is 10 seconds.
- Retries 3 times.
- Command: `curl -f http://localhost:${WEBHOOK_PORT:-8085}/health || exit 1`.

`GET /health` performs these checks:

- Ack directory `/var/lib/parking-reminder` is writable.
- A clock test file can be created, inspected, and removed with less than 2 seconds drift.
- `TZ` is `America/New_York`; a mismatch is reported as a warning in the text but does not make the endpoint unhealthy.
- Log directory `/var/log/parking-reminder` is writable.
- `crond` is running.
- Required environment variables `NTFY_SERVER`, `NTFY_TOPIC`, and `WEBHOOK_BASE_URL` are set.

Response:

- HTTP 200 with text starting `HEALTHY` when required checks pass.
- HTTP 503 with text starting `UNHEALTHY` when required checks fail.

## Web Server Behavior

`ack-server.py` uses Python `ThreadingHTTPServer`.

General behavior:

- Listens on `WEBHOOK_PORT`, default `8085`.
- Serves `status.html` at `/` and paths beginning with `/?`.
- Serves PWA files at `/manifest.json`, `/service-worker.js`, `/icons/icon.svg`, `/icons/icon-192.png`, and `/icons/icon-512.png`.
- Whitelists allowed paths and returns 404 for others.
- Parses URL path and ignores query string and fragment for routing.
- Applies a general rate limit of 10 requests per minute per client IP.
- Sends basic security headers on HTML, JSON, text, and static responses.
- Logs to `/var/log/parking-reminder/reminder.log` and stderr.
- Installs a SIGCHLD handler to reap child processes.

PWA/static behavior:

- `manifest.json` and icons are cacheable for 24 hours.
- `service-worker.js` is served with `Cache-Control: no-cache`.
- The service worker caches `/`, manifest, and icon assets.
- The service worker uses network-first behavior for `/status`, `/vacation`, `/ack`, and `/health`.

## Persistent State Files And Directories

Container paths:

| Path | Purpose |
| --- | --- |
| `/var/lib/parking-reminder` | Persistent state directory. |
| `/var/lib/parking-reminder/ack-TYPE.TIMESTAMP` | Timestamped ack files. |
| `/var/lib/parking-reminder/vacation-mode` | Vacation mode flag and optional expiry timestamp. |
| `/var/log/parking-reminder/reminder.log` | App log written by Bash and Python components. |
| `/var/run/parking-reminder-lock` | Runtime lock directory for `reminder.sh`; not persistent. |

Host paths in Docker Compose:

| Host path | Container path |
| --- | --- |
| `./state` | `/var/lib/parking-reminder` |
| `./logs` | `/var/log/parking-reminder` |

Startup behavior:

- `entrypoint.sh` creates state and log directories if missing.
- It warns if `/var/lib/parking-reminder` or `/var/log/parking-reminder` is not a mount point.
- It exits if either directory is not writable.

## Required And Optional Environment Variables

Required at container startup:

- `NTFY_SERVER`
- `NTFY_TOPIC`
- `WEBHOOK_BASE_URL`

Required by scheduled reminders:

- `NTFY_SERVER`
- `NTFY_TOPIC`
- `WEBHOOK_BASE_URL`

Required by status notification:

- `NTFY_SERVER`
- `NTFY_TOPIC`

Optional:

- `TZ`: defaults to `America/New_York`.
- `WEBHOOK_PORT`: defaults to `8085`; Compose sets it to `8085`.
- `NTFY_AUTH_USER`: used only when paired with `NTFY_AUTH_PASS`.
- `NTFY_AUTH_PASS`: used only when paired with `NTFY_AUTH_USER`.
- `NTFY_FAILSAFE_TOPIC`: enables selected cloud ntfy backup messages.
- `UPTIME_KUMA_PUSH_URL`: enables heartbeat after successful normal reminders.
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_PHONE`, `TWILIO_TO_PHONE`: present in Compose and `.env.example` but unused by the current active runtime.

## Docker And Deployment Assumptions

Docker image:

- Base image is `alpine:latest`.
- Installs `curl`, `tzdata`, `bash`, `python3`, `findutils`, and `rsvg-convert`.
- Copies Bash scripts, Python server, status HTML, PWA files, icon SVG, crontab, and entrypoint into the image.
- Generates 192px and 512px PNG icons from `icons/icon.svg` during build.
- Sets executable bits for scripts and entrypoint.
- Sets default `TZ=America/New_York`.

Docker Compose:

- Service name is `parking-reminder`.
- Container name is `parking-reminder`.
- Restart policy is `unless-stopped`.
- Port `8085` is published as `8085`.
- `./logs` and `./state` are expected to persist logs and state.
- JSON-file Docker logging is capped at 10 MB x 3 files.

Runtime process model:

- `entrypoint.sh` starts `crond -f -l 2` in the background.
- `entrypoint.sh` starts `python3 /usr/local/bin/ack-server.py` in the background.
- The container exits if the wait on background processes returns.
- A TERM or INT signal kills both child processes.

Networking assumptions:

- Mobile ntfy action buttons must be able to reach `WEBHOOK_BASE_URL`.
- The web UI must be reachable at the published port or via reverse proxy.
- Self-hosted ntfy may require basic auth; cloud failsafe ntfy uses a public topic URL.
