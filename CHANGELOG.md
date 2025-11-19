# Changelog

All notable changes to the Parking Reminder project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.3.0] - 2025-11-19

Major reliability and observability improvements based on comprehensive 6-expert security review. This release fixes critical race conditions, improves logging, and adds comprehensive testing infrastructure.

### Added

- **Atomic acknowledgment file creation** with O_CREAT|O_EXCL flags to eliminate race conditions
- **fsync persistence guarantees** for crash-safe ack file creation
- **Comprehensive error handling** with client IP logging for all webhook operations
- **Metrics logging** for ack creation, notification success/failure tracking
- **Clock drift detection** in healthcheck to detect NTP failures
- **44-test comprehensive test suite** (`tests/test_parking_lib.sh`)
- **Metrics analysis script** for observability (`tests/analyze_metrics.sh`)
- **Vacation mode auto-expiration** (default: 7 days) to prevent forgotten disable→parking ticket
- **vacation-lib.sh** shared library with backward compatibility
- **Volume mount verification** in entrypoint to detect Docker misconfigurations
- **Enhanced cleanup logging** with metrics for stale file removal

### Changed

- **Constants centralized** in `parking-lib.sh` (eliminated 14 magic number duplicates)
- **HTTP→Bash race condition eliminated** using double-check pattern (500ms→10ms window)
- **Vacation mode TOCTOU fixed** with `missing_ok=True` parameter
- **Status button rate limiter** prevents double-click race conditions
- **Separated ack checks** now log which acknowledgment type triggered skip
- **has_ack() function enhanced** with comprehensive logging showing every decision path

### Fixed

- **CRITICAL: "Ack responses sometimes don't work"** - Root cause: non-atomic file creation and missing fsync
- **Race condition in vacation mode** file checking (TOCTOU vulnerability)
- **Double-click vulnerability** in status button handler
- **Inconsistent constant definitions** across multiple scripts

### Security

- **Atomic file operations** prevent race conditions in multi-process environment
- **Crash-safe persistence** ensures acks survive unexpected container restarts
- **Comprehensive audit trail** with IP logging for security investigations

## [2.2.0] - 2025-11-11

Architecture simplification release. Replaced Twilio SMS/phone escalation with ntfy priority-based escalation, eliminating external API dependencies.

### Added

- **escalation-1-urgent.sh** - Max-priority (5) ntfy notification at 6:55pm
- **escalation-2-nuclear.sh** - Triple rapid-fire ntfy barrage at 7:00pm (30 seconds apart)
- **archive/README.md** - Complete restoration guide for Twilio integration
- **Priority-based ntfy escalation** that bypasses silent mode on Android

### Changed

- **Replaced Twilio with ntfy** for all escalation notifications
- **Nuclear barrage timing** increased from 20s to 30s intervals between bursts
- **crontab** updated to use new ntfy-based escalation scripts
- **Dockerfile** now installs new escalation scripts instead of Twilio scripts

### Removed

- **Twilio SMS escalation** (archived to `archive/escalation-sms.sh`)
- **Twilio phone call escalation** (archived to `archive/escalation-call.sh`)
- **TWILIO_* environment variables** no longer required (optional for restoration)

## [2.1.2] - 2025-11-09

Bugfix release addressing "Got it!" button acknowledgment logic.

### Fixed

- **"Got it!" button acknowledgment** - 5:45pm reminder now properly checks for "gotit" acknowledgments
- **Duplicate 5:45pm notifications** prevented when "Got it!" is clicked
- **Acknowledgment logic consistency** - 5:45pm reminder now checks both "gotit" and "nothome" acks

## [2.1.1] - 2025-11-04

UX enhancement release adding time-aware messaging to status notifications.

### Added

- **Context-aware status messages** based on time of day:
  - **Before 6pm**: Shows future parking side + "6-7pm window"
  - **6:00pm-6:59pm**: Urgent instruction "🚨 Park on X side (window closes at 7pm)"
  - **After 7pm**: Confirmation "✅ You should now be parked on X side"
- **Time-relevant information** improves actionability when checking status while driving

### Changed

- **status-notify.sh** enhanced with hour-based message logic
- **status.html** version footer updated to v2.1.1

## [2.1.0] - 2025-11-04

Code quality improvement release. Major refactoring to eliminate code duplication through shared library extraction.

### Added

- **parking-lib.sh** - Shared function library for all bash scripts
  - `calculate_parking_sides()` - Determines CURRENT/DESTINATION based on day
  - `is_sunday()` - Sunday check function
  - `has_ack()` - Acknowledgment file validation with expiration
  - `get_day_of_week()` - Returns 1-7 for Mon-Sun

### Changed

- **Parking side calculation** consolidated from 4 files into ONE function
- **All bash scripts** refactored to source `parking-lib.sh`
- **Code duplication eliminated** - DRY principle applied throughout
- **Maintenance simplified** - Rule changes now require updating only one file

### Fixed

- **Consistency issues** - All scripts now use identical logic (no drift between files)

## [2.0.4] - 2025-11-05

Critical bug fix and code quality analysis release.

### Added

- **OPTIMIZATION_ANALYSIS.md** - Comprehensive code review identifying 10 optimization opportunities
- **Code quality assessment** - Documented 8/10 rating with improvement roadmap

### Fixed

- **CRITICAL: status-notify.sh error checking** - `$?` now correctly checks curl exit code
  - Before: `CURL_RESULT=$(curl ...); if [ $? -eq 0 ]` (always returned 0)
  - After: `if CURL_RESULT=$(curl ...); then` (correctly checks curl)
  - Impact: On-demand status notifications now correctly report failures

## [2.0.3] - 2025-11-05

Consistency and precision fixes for acknowledgment handling and time windows.

### Added

- **Comprehensive diagnostic logging** for acknowledgment file detection
- **Filename timestamp parsing** for reliable ack validation

### Changed

- **Time window precision improved** - Eliminated ±2 minute drift:
  - 5:45pm window: 1745-1747 (was 1743-1747)
  - 6:00pm window: 1800-1802 (was 1758-1802)
  - 6:45pm window: 1845-1847 (was 1843-1847)

### Fixed

- **Acknowledgment consistency** - Escalation scripts now parse timestamp from filename (not mtime)
- **Container restart reliability** - Acks work correctly across container restarts
- **Edge case handling** - Fixed cases where mtime differs from creation time
- **Race conditions eliminated** - Precise time windows prevent early notifications

## [2.0.2] - 2025-11-01

Security hardening release addressing 7 additional critical vulnerabilities found in security audit of v2.0.1.

### Added

- **Rate limiting** - 10 requests/minute per IP on all endpoints
- **Zombie process reaping** - SIGCHLD handler prevents process table exhaustion
- **Stale lock cleanup** - PID-based locks with timeout recovery (prevents permanent deadlocks)
- **Comprehensive healthcheck** - Tests cron daemon, file writes, environment variables
- **cleanup-acks.sh** - Separate daily 3am cron job for stale file cleanup
- **Notification priority fix** - Status notifications use "high" priority for Android alerts
- **Stderr logging** - Errors visible in docker logs when container fails to start

### Changed

- **Timestamp validation** - Parse timestamps from filenames (immune to clock changes)
- **Lock file mechanism** - PID-based with timeout detection instead of simple touch
- **Healthcheck frequency** - Comprehensive tests every 5 minutes

### Fixed

- **Path traversal protection** - Proper URL parsing prevents query parameter bypass
- **Argument injection** - Conditional curl auth prevents credential parsing issues
- **Time validation** - Prevents crashes if date command fails
- **URL re-validation** - WEBHOOK_BASE_URL checked before JSON injection

### Security

- **Path traversal vulnerability** eliminated with proper `urlparse` usage
- **Command injection** via unquoted curl arguments eliminated
- **Race condition in lock files** fixed with PID-based atomic operations
- **Clock manipulation attacks** mitigated with filename-based timestamp parsing
- **Resource exhaustion** prevented with zombie reaping and rate limiting
- **XSS protection headers** added (X-Frame-Options, X-Content-Type-Options, X-XSS-Protection)

## [2.0.1] - 2025-10-31

Major security release fixing 34 critical security and reliability issues identified in initial security audit.

### Added

- **ack-server.py** - Secure Python HTTP server replacing netcat
- **Environment variable validation** in entrypoint (container won't start with missing config)
- **Dynamic webhook URLs** using WEBHOOK_BASE_URL environment variable
- **Atomic lock files** using `mkdir` instead of `touch`
- **Timestamp-based acknowledgment expiration** to prevent race conditions
- **XML escaping for TwiML** to prevent injection attacks
- **FIXES.md** - Complete documentation of all 34 security fixes

### Changed

- **Acknowledgment file format** - Now includes timestamp: `ack-gotit.1730419200`
- **Escalation split** - Separate cron jobs instead of blocking `sleep 300`
- **Time comparisons** - Arithmetic comparison instead of string comparison
- **Healthcheck frequency** - Improved from 5 minutes to 30 seconds

### Removed

- **ack-server.sh** - Insecure netcat-based server completely removed
- **Hardcoded IP addresses** - All action button URLs now use environment variable

### Fixed

- **"Got it!" button logic** - Now correctly keeps 6pm and 6:45pm backup notifications
- **Race conditions** - Multiple fixes for file creation and cleanup timing
- **Blocking operations** - Escalation no longer blocks for 5 minutes

### Security

- **CRITICAL: Remote Code Execution** - Replaced `nc -e /bin/bash` backdoor with secure Python server
- **CRITICAL: Command Injection** - Fixed unquoted variables in curl authentication (now uses `--user` flag)
- **CRITICAL: No Input Validation** - Python server validates all paths against whitelist
- **CRITICAL: XML Injection** - TwiML output properly escaped
- **Race Conditions** - Multiple race condition vulnerabilities eliminated
- **Time-based attacks** - Arithmetic time comparison prevents manipulation

## [2.0.0] - 2025-10-31

Initial production release with complete feature set.

### Added

- **Smart notification system** - Three-stage reminders (5:45pm, 6:00pm, 6:45pm)
- **Acknowledgment buttons** with context-aware logic:
  - "Got it!" - Keeps 6pm and 6:45pm backups
  - "Not home" - Stops ALL notifications
  - "I moved it" - Stops ALL notifications
  - "Done!" - Stops escalation only
- **On-demand status check** via "Where Do I Park?" button
- **Vacation mode toggle** via web UI and CLI
- **Twilio SMS escalation** at 6:55pm (if no acknowledgment)
- **Twilio phone call escalation** at 7:00pm (if still no acknowledgment)
- **Self-hosted ntfy integration** with authentication
- **Failsafe notifications** to cloud ntfy.sh if self-hosted fails
- **Uptime Kuma integration** for heartbeat monitoring
- **Mobile-optimized web interface** (status.html)
- **Docker containerization** with Alpine Linux
- **Cron-based scheduling** for reliable execution
- **Lock file mechanism** to prevent duplicate executions
- **Parking side logic**:
  - Mon/Wed/Fri: AWAY side → HOUSE side
  - Tue/Thu/Sat: HOUSE side → AWAY side
  - Sunday: No move required

### Changed

- Complete rewrite from v1.0 cloud-only solution to self-hosted architecture

## [1.0.0] - 2025-10-30

Initial release with basic notification functionality.

### Added

- **Basic notifications** via cloud ntfy.sh
- **Four daily reminders** (4pm, 5:45pm, 6pm, 6:45pm)
- **Simple parking side calculation**
- **No acknowledgment or escalation** (notifications only)

---

## Version Comparison

- **v2.3.0**: Reliability & observability (atomic ops, comprehensive testing, auto-expiration)
- **v2.2.0**: Architecture simplification (ntfy priority escalation, Twilio archived)
- **v2.1.x**: UX & code quality improvements (time-aware messages, shared library)
- **v2.0.x**: Security hardening (34→41 total vulnerabilities fixed, Python server, validation)
- **v2.0.0**: Initial production release (full feature set, self-hosted)
- **v1.0.0**: Basic prototype (cloud notifications only)

## Breaking Changes

### v2.2.0

- **Twilio environment variables** no longer required (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_PHONE, TWILIO_TO_PHONE)
  - Migration: Optional - remove from .env or keep for archive restoration
  - Impact: No SMS/phone escalation unless Twilio scripts restored from archive/

### v2.0.0

- **Complete architectural change** from cloud-only to self-hosted
  - Migration: New deployment required, cannot upgrade in-place
  - Impact: All configuration must be recreated

## Upgrade Notes

### Upgrading to v2.3.0 from v2.2.0

- ✅ **Fully backward compatible** - No configuration changes required
- ✅ **Automatic migration** - Vacation mode auto-expiration applies to existing files
- ✅ **Enhanced logging** - Metrics logged to same file, no new log files
- Recommended: Review new metrics in logs for observability insights

### Upgrading to v2.2.0 from v2.1.x

1. **Optional**: Remove TWILIO_* environment variables from `.env` (not required)
2. Rebuild container: `docker-compose up -d --build`
3. Test ntfy priority escalation: `docker exec parking-reminder /usr/local/bin/escalation-1-urgent.sh`
4. **To restore Twilio**: See `archive/README.md` for step-by-step restoration guide

### Upgrading to v2.1.0 from v2.0.x

- ✅ **No breaking changes** - Pure refactoring, identical functionality
- Rebuild container: `docker-compose up -d --build`
- Verify parking side logic works correctly after refactor

### Upgrading to v2.0.2 from v2.0.1

- ✅ **No configuration changes** required
- Rebuild container for security fixes
- Stale acks cleaned automatically at 3am daily

### Upgrading to v2.0.1 from v2.0.0

1. **Critical**: Rebuild container immediately for security fixes
2. **No configuration changes** required
3. Test all acknowledgment buttons after upgrade
4. Verify escalation works (no longer blocks for 5 minutes)

## Support

- **Documentation**: See [README.md](README.md) for usage guide
- **Project Documentation**: See [CLAUDE.md](CLAUDE.md) for development guide
- **Security Fixes**: See [FIXES.md](FIXES.md) for v2.0.1 vulnerability details
- **Issues**: Create GitHub issue with logs from `docker logs parking-reminder`

---

**Never get a parking ticket again!** 🚗
