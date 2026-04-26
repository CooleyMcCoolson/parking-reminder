# Rebuild Plan

This plan proposes a staged Python/FastAPI remake while preserving the behavior documented in `PRODUCT_BEHAVIOR_CONTRACT.md`. Each phase should be independently reviewable and should avoid changing production behavior until the migration phase explicitly switches traffic.

## Guiding Constraints

- Treat `PRODUCT_BEHAVIOR_CONTRACT.md` as the behavioral source of truth.
- Keep the existing Docker/Bash implementation runnable while the rewrite is built.
- Do not introduce behavior changes as incidental cleanup.
- Build deterministic, easily tested core logic before web routes, scheduling, or notification delivery.
- Prefer explicit compatibility adapters over implicit "close enough" behavior.
- Preserve file-based state initially, then decide later whether a database is worth the operational cost.

## Phase 1: Deterministic Rule Core

Goal: implement parking rules, reminder stages, ack suppression, and status-message decisions as pure Python functions.

Suggested module boundary:

- `app_core/rules.py`
- `app_core/models.py`
- `app_core/timezone.py`

Inputs:

- A timezone-aware datetime.
- A set of valid acknowledgment types.
- Vacation active/inactive state as an explicit boolean.

Outputs:

- Parking side decision: current side, destination side, or Sunday/no-move.
- Current reminder stage, if any.
- Whether a stage should send or be suppressed.
- Suppression reason when suppressed.
- Status button message variant.

Rules to preserve:

- Monday, Wednesday, Friday: `AWAY -> HOUSE`.
- Tuesday, Thursday, Saturday: `HOUSE -> AWAY`.
- Sunday: no scheduled move.
- 5:45pm reminder window is 17:45 through 17:47.
- 6:00pm reminder window is 18:00 through 18:02.
- 6:45pm reminder window is 18:45 through 18:47.
- 6:55pm urgent escalation and 7:00pm nuclear escalation are scheduler events, not broad time windows.
- `gotit` suppresses 5:45 and escalations, but not 6:00 or 6:45.
- `nothome` suppresses all reminder/escalation stages.
- `moved` suppresses 6:00, 6:45, and escalations.
- `done` suppresses 6:45 and escalations.

Acceptance checks:

- Unit tests cover all seven weekdays.
- Unit tests cover each reminder stage and non-stage times.
- Unit tests cover the complete suppression matrix.
- Unit tests cover Sunday status behavior.
- No file I/O, network I/O, FastAPI, ntfy, or scheduler code in this phase.

## Phase 2: State Handling

Goal: reproduce the current file-backed state semantics behind a Python interface.

Suggested module boundary:

- `app_core/state.py`
- `app_core/vacation.py`

State compatibility requirements:

- Use `/var/lib/parking-reminder` by default.
- Support existing ack filenames: `ack-TYPE.TIMESTAMP`.
- Support decimal microsecond timestamps.
- Treat filename timestamp as source of truth.
- Consider acks valid for 14,400 seconds.
- Accept ack timestamps up to 5 minutes in the future.
- Ignore expired or malformed ack files for behavior decisions.
- Cleanup deletes malformed ack files and acks older than 4 hours.
- Preserve vacation file path `/var/lib/parking-reminder/vacation-mode`.
- Treat missing vacation file as disabled.
- Treat empty or invalid vacation file as enabled indefinitely.
- Treat future integer timestamp as enabled until that time.
- Treat expired integer timestamp as disabled and remove the file.

Implementation notes:

- Create ack files atomically.
- Keep ack file contents empty for compatibility.
- Fsync created ack files and the parent directory if preserving crash-resistance exactly.
- Return structured state snapshots for UI and health routes.
- Keep all filesystem paths configurable for tests.

Acceptance checks:

- Tests operate in a temporary state directory.
- Existing sample ack filenames from the Bash implementation are parsed correctly.
- Cleanup behavior matches `cleanup-acks.sh`.
- Web-created indefinite vacation mode and CLI-created expiring vacation mode are both represented.

## Phase 3: ntfy Notifier

Goal: implement ntfy delivery as an injectable service without coupling it to route or scheduler logic.

Suggested module boundary:

- `app_core/notifications/ntfy.py`
- `app_core/notifications/messages.py`

Configuration:

- `NTFY_SERVER`
- `NTFY_TOPIC`
- optional `NTFY_AUTH_USER`
- optional `NTFY_AUTH_PASS`
- optional `NTFY_FAILSAFE_TOPIC`
- optional `WEBHOOK_BASE_URL`
- optional `UPTIME_KUMA_PUSH_URL`

Behavior to preserve:

- Normal reminders retry up to 3 times.
- Normal reminder attempts use a 10-second timeout.
- Failed normal reminder attempts sleep 2 seconds between tries.
- Normal reminder failure posts to cloud `https://ntfy.sh/$NTFY_FAILSAFE_TOPIC` when configured.
- Successful normal reminders push Uptime Kuma when configured.
- Status notification uses title `Parking Status`, priority `high`, and tags `information_source,car`.
- Normal reminder title is `Parking Reminder`.
- Reminder priorities and tags match the contract.
- Action buttons target the exact ack endpoints under `WEBHOOK_BASE_URL`.
- Escalation priority uses numeric `5`.
- Escalation action buttons create `/ack/done` or `/ack/nothome`.

Implementation notes:

- Use `httpx` or `requests`; standardize timeout and error handling.
- Keep message construction separate from transport.
- Allow a fake notifier in tests.
- Log structured event names that can map back to the current log metrics.

Acceptance checks:

- Tests assert outbound method, URL, headers, body, auth behavior, and action payloads.
- Tests cover failsafe behavior without hitting the network.
- Tests cover auth absent, auth partially configured, and auth fully configured.

## Phase 4: FastAPI Routes And UI

Goal: replace `ack-server.py` behavior with FastAPI while keeping routes compatible.

Suggested route surface:

- `GET /`
- `GET /health`
- `POST /status`
- `GET /vacation/status`
- `GET /api/vacation/status`
- `POST /vacation/toggle`
- `POST /api/vacation/toggle`
- `GET /ack/{ack_type}`
- `POST /ack/{ack_type}`
- `GET /manifest.json`
- `GET /service-worker.js`
- `GET /icons/icon.svg`
- `GET /icons/icon-192.png`
- `GET /icons/icon-512.png`

Compatibility requirements:

- GET and POST ack endpoints both create ack files.
- Valid ack types are exactly `gotit`, `nothome`, `moved`, and `done`.
- Ack response remains plain text in the form `Acknowledged: TYPE`.
- `/status` starts status notification work and redirects to `/`.
- `/status` rate limit remains 1 request per 5 seconds per client IP.
- General rate limit remains 10 requests per minute per client IP.
- Vacation status response remains `{"enabled": true|false}`.
- Web toggle keeps current behavior: create an empty, indefinite vacation file when enabling.
- Static file caching behavior remains compatible, especially no-cache for service worker.
- Security headers remain at least equivalent.

UI strategy:

- Initially serve the existing `status.html`, `manifest.json`, `service-worker.js`, and generated icons unchanged.
- Add template rendering only after route compatibility is locked down.
- Keep PWA behavior intact.

Acceptance checks:

- Route tests cover status codes, response content types, redirects, and state effects.
- Rate limit behavior is tested with a fake or controllable clock.
- Static routes return expected cache headers.
- Health route can be tested with injected health dependencies.

## Phase 5: Scheduler Replacement For Cron

Goal: replace cron with an in-process scheduler or a small scheduler process without altering event timing.

Options:

- APScheduler inside the FastAPI process.
- A separate Python scheduler process in the same container.
- A separate scheduler container that calls the FastAPI API.

Recommended path:

1. Implement scheduler jobs as Python functions that call the pure rule core, state layer, and notifier.
2. Run them manually from CLI commands first.
3. Add scheduler wiring only after manual commands match current scripts.
4. Keep scheduler timezone explicit: `America/New_York`.

Jobs to preserve:

- Daily cleanup at 3:00am.
- 5:45pm reminder Monday through Saturday.
- 6:00pm reminder Monday through Saturday.
- 6:45pm reminder Monday through Saturday.
- 6:55pm urgent escalation Monday through Saturday.
- 7:00pm nuclear escalation Monday through Saturday.

Nuclear escalation detail:

- It must send up to three notifications.
- It must wait 30 seconds after the first and second sends.
- It must re-check acks after each wait.
- It must stop if any ack type is present.

Acceptance checks:

- Tests verify job registration times and day-of-week filters.
- Tests verify manual command behavior without starting the scheduler.
- Tests use a fake clock and fake notifier for escalation sequencing.
- Existing cron remains the production scheduler until cutover.

## Phase 6: Docker Deployment

Goal: package the FastAPI implementation while preserving paths, ports, environment variables, and mounted state.

Compatibility requirements:

- Keep container port `8085`.
- Keep state path `/var/lib/parking-reminder`.
- Keep log path `/var/log/parking-reminder`.
- Keep `./state` and `./logs` host mounts in Compose or provide a compatible migration Compose file.
- Keep `TZ=America/New_York` default.
- Keep required env validation for `NTFY_SERVER`, `NTFY_TOPIC`, and `WEBHOOK_BASE_URL`.
- Keep Docker healthcheck pointed at `/health`.
- Preserve image generation or provide committed PNG icons.

Recommended packaging:

- Use a Python slim image or Alpine only if native dependency friction stays low.
- Run with `uvicorn`.
- If scheduler runs in-process, document that one process owns both API and scheduled jobs.
- If scheduler is separate, use a small supervisor or separate Compose services with clear health checks.

Acceptance checks:

- `docker compose up` exposes the UI at port 8085.
- Restart preserves ack and vacation files.
- Healthcheck goes healthy only when state, logs, scheduler, and required env are valid.
- Existing `.env.example` is updated only when the rewrite branch intentionally changes deployment docs.

## Phase 7: Migration And Archive Strategy

Goal: switch from the Bash/Python hybrid to FastAPI without losing state or the ability to roll back.

Migration steps:

1. Freeze the current behavior contract.
2. Build the FastAPI app beside the existing scripts.
3. Run both implementations in test mode against copied state fixtures.
4. Compare outputs for representative dates, times, ack states, and vacation states.
5. Deploy FastAPI with the same mounted `./state` and `./logs`.
6. Stop cron/Bash jobs only at the final cutover.
7. Keep old scripts in an archive directory for at least one release.

State migration:

- No required data migration if the new app reads existing ack and vacation files.
- Existing ack files naturally expire within 4 hours.
- Existing indefinite vacation files must remain enabled.
- Existing timestamped vacation files must preserve their expiration behavior.

Rollback:

- Because paths and state format remain compatible, rollback should be restoring the old image or Compose service.
- Do not alter or delete `./state` during cutover.
- Do not rewrite vacation files into a new format until rollback is no longer required.

Archive strategy:

- Move old Bash scripts only after the FastAPI runtime is live and verified.
- Keep `archive/` docs clear about old Twilio scripts versus old Bash runtime scripts.
- Mark stale docs rather than deleting them during discovery/spec branches.

Final acceptance for the remake:

- Contract tests derived from `PRODUCT_BEHAVIOR_CONTRACT.md` pass.
- Manual route checks match current ack, vacation, status, and health behavior.
- A dry-run scheduler log shows the same jobs at the same times.
- Docker deployment uses the same public URL, state path, log path, and port.
- Rollback has been tested at least once with preserved state.
