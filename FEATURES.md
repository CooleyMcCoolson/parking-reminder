# Parking Reminder - Feature List

> Generated: 2025-11-27 (bootstrapped from existing v2.3.0 project)
> This is the project roadmap. Update as features are completed.

## Status Legend
- `[ ]` Not started
- `[~]` In progress
- `[x]` Complete
- `[!]` Blocked

---

## Core Features (v2.x - COMPLETE)

### Notification System
- [x] Smart notifications at 5:45pm, 6:00pm, 6:45pm
- [x] Parking side calculation (Mon/Wed/Fri vs Tue/Thu/Sat)
- [x] Sunday skip logic
- [x] Self-hosted ntfy integration with authentication
- [x] Failsafe to cloud ntfy.sh if self-hosted fails

### Acknowledgment System
- [x] "Got it!" button (5:45pm) - keeps backup reminders
- [x] "Not home" button - stops all reminders
- [x] "I moved it" button (6:00pm) - task complete
- [x] "Done!" button (6:45pm) - stops escalation
- [x] Timestamp-based ack file expiration
- [x] Atomic file creation (v2.3.0)

### Escalation (v2.2.0 - ntfy-based)
- [x] 6:55pm urgent notification (priority 5)
- [x] 7:00pm nuclear barrage (3x rapid-fire)
- [x] Twilio SMS/phone archived (restorable)

### Vacation Mode
- [x] Web UI toggle
- [x] CLI helper (vacation.sh)
- [x] Auto-expiration after 7 days (v2.3.0)

### Web UI
- [x] Mobile-optimized status.html
- [x] "Where Do I Park?" on-demand status
- [x] Time-aware status messages (v2.1.1)
- [x] Add to home screen support

### Infrastructure
- [x] Docker container (Alpine + Python + bash)
- [x] Cron-based scheduling
- [x] Python HTTP server (ack-server.py)
- [x] Shared function library (parking-lib.sh)
- [x] Comprehensive healthcheck
- [x] Rate limiting (10 req/min per IP)
- [x] Uptime Kuma integration

### Security (v2.0.1 + v2.0.2)
- [x] Replaced nc -e /bin/bash with Python server
- [x] Fixed command injection vulnerabilities
- [x] Path traversal protection
- [x] Atomic lock files
- [x] Zombie process reaping
- [x] Input validation
- [x] Security headers

### Testing (v2.3.0)
- [x] 44-test comprehensive suite
- [x] Race condition fixes verified

---

## Future Enhancements (Planned)

### PWA Enhancement (v2.4.0 - COMPLETE)
- [x] Full PWA manifest for better mobile install
- [x] Service worker for offline status page
- [x] App icon and splash screen

### Geofencing
- [ ] Automatic "not home" detection via location
- [ ] Requires mobile app or Tasker integration

### Calendar Integration
- [ ] Auto-enable vacation mode from calendar
- [ ] Google Calendar or iCal sync

### Observability
- [ ] Metrics export (Prometheus format)
- [ ] Grafana dashboard template
- [ ] Alert on missed acknowledgments

---

## Technical Debt (Low Priority)

- [ ] Failsafe notification error handling (currently `|| true`)
- [ ] Cloud ntfy.sh topic requires public access (no auth)

---

## Progress Summary

| Category           | Total | Done | In Progress | Blocked |
|--------------------|-------|------|-------------|---------|
| Core Features      | 25    | 25   | 0           | 0       |
| Future Enhancements| 4     | 3    | 0           | 0       |
| Technical Debt     | 2     | 0    | 0           | 0       |
| **Total**          | **31**| **28**| **0**      | **0**   |

**Overall Progress:** 90% (core features 100% complete, PWA enhancement complete)

---

## Notes

### Architectural Decisions
- **Hybrid bash/Python**: Bash for cron/scripting, Python for HTTP server - committed long-term
- **File-based state**: Simple, reliable, no database needed
- **ntfy over Twilio**: Simpler, self-contained, no external API dependencies (v2.2.0)
- **Shared library**: parking-lib.sh prevents code drift between scripts (v2.1.0)

### Version History
- v1.0: Basic notifications
- v2.0: Smart acknowledgments, vacation mode, escalation
- v2.0.1: 34 security fixes
- v2.0.2: 6 additional security fixes
- v2.1.0: Code deduplication
- v2.1.1: Time-aware status messages
- v2.1.2: "Got it!" button bugfix
- v2.2.0: Twilio → ntfy escalation
- v2.3.0: Atomic operations, race fixes, 44 tests
- v2.4.0: PWA implementation, Traefik bypass for ack buttons, mobile data fix

---

*Last Updated: 2025-11-27 (Session 1)*
*Update this file with session-closer or manually as features complete.*
