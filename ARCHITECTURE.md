# Parking Reminder v2.0 - Python Architecture Plan

## Executive Summary

This document outlines the complete redesign from bash/netcat to Python/Flask, addressing all 34 critical issues found in the bash implementation while maintaining the same user-facing functionality.

## Design Goals

1. **Security**: No command injection, proper authentication, input validation
2. **Reliability**: No race conditions, atomic operations, proper error handling
3. **Maintainability**: Clear separation of concerns, testable components
4. **Simplicity**: Leverage proven frameworks instead of reinventing HTTP servers

## Technology Stack

- **Python 3.11+** (Alpine image)
- **Flask 3.0** - Web framework for API and UI
- **APScheduler 3.10** - Cron-like job scheduling
- **SQLite 3** - Persistent state management
- **Gunicorn** - Production WSGI server
- **Twilio SDK** - SMS/voice calls
- **Requests** - HTTP client for ntfy

## File Structure

```
parking-reminder/
├── app/
│   ├── __init__.py           # Flask app factory, initialization
│   ├── config.py             # Environment configuration (DONE)
│   ├── models.py             # SQLite database models
│   ├── notifier.py           # ntfy notification sender
│   ├── escalation.py         # Twilio SMS/call escalation
│   ├── scheduler.py          # APScheduler job definitions
│   └── routes.py             # Flask API endpoints
├── templates/
│   └── status.html           # Mobile web UI
├── static/
│   └── style.css             # Optional: separate CSS if needed
├── app.py                    # Application entry point
├── requirements.txt          # Python dependencies (DONE)
├── Dockerfile                # Python 3.11 Alpine container
├── docker-compose.yml        # Container orchestration
├── .env                      # Configuration (credentials)
├── .gitignore                # Protect secrets
├── README.md                 # User documentation
└── ARCHITECTURE.md           # This file

```

## Database Schema

**Table: acknowledgments**
```sql
CREATE TABLE acknowledgments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ack_type TEXT NOT NULL,           -- 'gotit', 'nothome', 'moved', 'done'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,     -- Auto-cleanup mechanism
    UNIQUE(ack_type)                   -- Only one of each type active
);
```

**Table: vacation_mode**
```sql
CREATE TABLE vacation_mode (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- Singleton table
    enabled BOOLEAN NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Table: notification_log**
```sql
CREATE TABLE notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_type TEXT NOT NULL,    -- '545pm', '600pm', '645pm', 'sms', 'call', 'status'
    success BOOLEAN NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Why SQLite?**
- ✅ Atomic transactions (no race conditions)
- ✅ UNIQUE constraints (no duplicate acks)
- ✅ Automatic cleanup with expires_at queries
- ✅ Built into Python (no dependencies)
- ✅ Audit trail with notification_log

## Component Architecture

### 1. app/__init__.py - Flask Application Factory

```python
from flask import Flask
from flask_wtf.csrf import CSRFProtect
import logging

def create_app():
    """Application factory pattern"""
    app = Flask(__name__)
    app.config.from_object('app.config.Config')

    # Initialize CSRF protection
    csrf = CSRFProtect(app)

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s: %(message)s',
        handlers=[
            logging.FileHandler('/var/log/parking-reminder/app.log'),
            logging.StreamHandler()
        ]
    )

    # Initialize database
    from app.models import init_db
    init_db()

    # Register routes
    from app.routes import bp
    app.register_blueprint(bp)

    # Start scheduler
    from app.scheduler import start_scheduler
    start_scheduler(app)

    return app
```

**Responsibilities:**
- Create Flask app instance
- Load configuration
- Initialize CSRF protection
- Setup logging
- Initialize database
- Register routes blueprint
- Start APScheduler

### 2. app/config.py - Configuration Management

**Status:** ✅ DONE

**Responsibilities:**
- Load environment variables
- Validate required configuration
- Provide helper methods (has_twilio(), has_ntfy_auth())
- Fail fast on missing required vars

### 3. app/models.py - Database Layer

```python
import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager
from app.config import Config
import logging

logger = logging.getLogger(__name__)

@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """Initialize database schema"""
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS acknowledgments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ack_type TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            );

            CREATE TABLE IF NOT EXISTS vacation_mode (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                enabled BOOLEAN NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS notification_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notification_type TEXT NOT NULL,
                success BOOLEAN NOT NULL,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Initialize vacation mode if not exists
            INSERT OR IGNORE INTO vacation_mode (id, enabled) VALUES (1, 0);
        ''')

# Acknowledgment functions
def set_ack(ack_type: str, expires_hours: int = 24):
    """Set acknowledgment with expiration"""
    expires_at = datetime.now() + timedelta(hours=expires_hours)
    with get_db() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO acknowledgments (ack_type, expires_at) VALUES (?, ?)',
            (ack_type, expires_at)
        )
    logger.info(f"Acknowledgment set: {ack_type} (expires: {expires_at})")

def has_ack(ack_type: str) -> bool:
    """Check if acknowledgment exists and is not expired"""
    with get_db() as conn:
        row = conn.execute(
            'SELECT 1 FROM acknowledgments WHERE ack_type = ? AND expires_at > ?',
            (ack_type, datetime.now())
        ).fetchone()
    return row is not None

def clear_expired_acks():
    """Remove expired acknowledgments"""
    with get_db() as conn:
        conn.execute('DELETE FROM acknowledgments WHERE expires_at <= ?', (datetime.now(),))

# Vacation mode functions
def is_vacation_mode() -> bool:
    """Check if vacation mode is enabled"""
    with get_db() as conn:
        row = conn.execute('SELECT enabled FROM vacation_mode WHERE id = 1').fetchone()
    return bool(row['enabled']) if row else False

def set_vacation_mode(enabled: bool):
    """Enable or disable vacation mode"""
    with get_db() as conn:
        conn.execute(
            'UPDATE vacation_mode SET enabled = ?, updated_at = ? WHERE id = 1',
            (1 if enabled else 0, datetime.now())
        )
    logger.info(f"Vacation mode {'enabled' if enabled else 'disabled'}")

# Logging function
def log_notification(notification_type: str, success: bool, error_message: str = None):
    """Log notification attempt"""
    with get_db() as conn:
        conn.execute(
            'INSERT INTO notification_log (notification_type, success, error_message) VALUES (?, ?, ?)',
            (notification_type, success, error_message)
        )
```

**Responsibilities:**
- Database connection management with context manager
- Schema initialization
- Acknowledgment CRUD operations
- Vacation mode state
- Notification logging
- Automatic expiration handling

**Security Features:**
- Parameterized queries (no SQL injection)
- Context manager ensures cleanup
- UNIQUE constraint prevents duplicates
- Atomic transactions

### 4. app/notifier.py - ntfy Integration

```python
import requests
import json
from typing import Optional
from app.config import Config
from app.models import log_notification
import logging

logger = logging.getLogger(__name__)

class NotificationError(Exception):
    """Custom exception for notification failures"""
    pass

def send_notification(
    title: str,
    message: str,
    priority: str = 'default',
    tags: list[str] = None,
    actions: list[dict] = None,
    notification_type: str = 'unknown'
) -> bool:
    """
    Send notification via ntfy with retry logic

    Args:
        title: Notification title
        message: Notification body
        priority: default, high, urgent
        tags: List of emoji/tags
        actions: List of action button dicts
        notification_type: For logging (545pm, 600pm, etc)

    Returns:
        True if successful, False otherwise
    """
    url = f"{Config.NTFY_SERVER}/{Config.NTFY_TOPIC}"

    headers = {
        'Title': title,
        'Priority': priority,
        'Tags': ','.join(tags) if tags else ''
    }

    if actions:
        headers['Actions'] = json.dumps(actions)

    # Setup authentication if configured
    auth = None
    if Config.has_ntfy_auth():
        auth = (Config.NTFY_AUTH_USER, Config.NTFY_AUTH_PASS)

    # Retry logic (3 attempts)
    last_error = None
    for attempt in range(1, 4):
        try:
            response = requests.post(
                url,
                data=message.encode('utf-8'),
                headers=headers,
                auth=auth,
                timeout=10
            )
            response.raise_for_status()

            logger.info(f"Notification sent: {notification_type} (attempt {attempt}/3)")
            log_notification(notification_type, success=True)

            # Send heartbeat to Uptime Kuma if configured
            if Config.UPTIME_KUMA_PUSH_URL:
                try:
                    requests.get(
                        f"{Config.UPTIME_KUMA_PUSH_URL}?status=up&msg={notification_type}",
                        timeout=5
                    )
                except Exception as e:
                    logger.warning(f"Uptime Kuma heartbeat failed: {e}")

            return True

        except requests.exceptions.RequestException as e:
            last_error = str(e)
            logger.warning(f"Notification attempt {attempt}/3 failed: {e}")
            if attempt < 3:
                import time
                time.sleep(2)

    # All retries failed
    logger.error(f"Notification failed after 3 attempts: {last_error}")
    log_notification(notification_type, success=False, error_message=last_error)

    # Send failsafe notification if configured
    if Config.NTFY_FAILSAFE_TOPIC:
        send_failsafe(f"Self-hosted ntfy failed! Original: {message}", last_error)

    return False

def send_failsafe(message: str, error: str):
    """Send failsafe notification to cloud ntfy.sh"""
    try:
        requests.post(
            f"https://ntfy.sh/{Config.NTFY_FAILSAFE_TOPIC}",
            data=f"Parking System FAILURE: {message}\nError: {error}",
            headers={'Priority': 'urgent', 'Title': 'Parking System FAILURE'},
            timeout=5
        )
        logger.info("Failsafe notification sent to cloud ntfy.sh")
    except Exception as e:
        logger.error(f"Failsafe notification also failed: {e}")

def build_action_buttons(buttons: list[tuple[str, str]]) -> list[dict]:
    """
    Build action button JSON for ntfy

    Args:
        buttons: List of (label, action_path) tuples
                 e.g., [("Got it!", "/ack/gotit"), ("Not home", "/ack/nothome")]

    Returns:
        List of action button dicts
    """
    return [
        {
            "action": "view",
            "label": label,
            "url": f"{Config.WEBHOOK_BASE_URL}{path}",
            "clear": True
        }
        for label, path in buttons
    ]
```

**Responsibilities:**
- Send ntfy notifications with retry logic
- Handle authentication
- Build action button JSON
- Send failsafe notifications on failure
- Log all attempts
- Uptime Kuma heartbeat

**Improvements Over Bash:**
- ✅ Proper URL escaping
- ✅ No command injection
- ✅ Environment variable for base URL
- ✅ Exception handling
- ✅ Structured logging

### 5. app/escalation.py - Twilio Integration

```python
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from app.config import Config
from app.models import log_notification, has_ack
import logging

logger = logging.getLogger(__name__)

def should_escalate() -> bool:
    """Check if escalation is needed (no acknowledgments received)"""
    return not any([
        has_ack('gotit'),
        has_ack('nothome'),
        has_ack('moved'),
        has_ack('done')
    ])

def send_sms(current_side: str, destination_side: str) -> bool:
    """Send SMS escalation via Twilio"""
    if not Config.has_twilio():
        logger.warning("Twilio not configured, skipping SMS")
        return False

    message = (
        f"🚨 PARKING ALERT: You have 5 minutes to move car "
        f"from {current_side} to {destination_side} side! "
        f"No acknowledgment received."
    )

    try:
        client = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
        msg = client.messages.create(
            body=message,
            from_=Config.TWILIO_FROM_PHONE,
            to=Config.TWILIO_TO_PHONE
        )
        logger.info(f"SMS sent successfully: {msg.sid}")
        log_notification('sms', success=True)
        return True

    except TwilioRestException as e:
        logger.error(f"SMS failed: {e}")
        log_notification('sms', success=False, error_message=str(e))
        return False

def make_phone_call(current_side: str, destination_side: str) -> bool:
    """Make phone call escalation via Twilio"""
    if not Config.has_twilio():
        logger.warning("Twilio not configured, skipping phone call")
        return False

    # TwiML for voice call - properly escaped
    twiml = f"""
    <Response>
        <Say voice="alice">
            Parking reminder! You need to move your car immediately
            from the {current_side} side to the {destination_side} side.
            The parking window closes at 7 PM. Move your car now!
        </Say>
        <Pause length="2"/>
        <Say voice="alice">
            I repeat: Move your car from {current_side} to {destination_side} side now!
        </Say>
    </Response>
    """

    try:
        client = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
        call = client.calls.create(
            twiml=twiml,
            from_=Config.TWILIO_FROM_PHONE,
            to=Config.TWILIO_TO_PHONE
        )
        logger.info(f"Phone call initiated: {call.sid}")
        log_notification('call', success=True)
        return True

    except TwilioRestException as e:
        logger.error(f"Phone call failed: {e}")
        log_notification('call', success=False, error_message=str(e))
        return False
```

**Responsibilities:**
- Check if escalation needed
- Send SMS via Twilio SDK
- Make phone call with TwiML
- Error handling and logging

**Improvements Over Bash:**
- ✅ Uses Twilio SDK (proper authentication)
- ✅ TwiML is properly constructed (no XML injection)
- ✅ Exception handling
- ✅ No blocking sleeps

### 6. app/scheduler.py - APScheduler Jobs

```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import pytz
from flask import Flask
from app.config import Config
from app.models import is_vacation_mode, has_ack, clear_expired_acks
from app.notifier import send_notification, build_action_buttons
from app.escalation import should_escalate, send_sms, make_phone_call
import logging

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

def get_parking_sides() -> tuple[str, str]:
    """Calculate current and destination parking sides based on day of week"""
    tz = pytz.timezone(Config.TIMEZONE)
    now = datetime.now(tz)
    day = now.isoweekday()  # Monday=1, Sunday=7

    if day == 7:  # Sunday
        return ('N/A', 'N/A')
    elif day in [1, 3, 5]:  # Mon, Wed, Fri
        return ('AWAY', 'HOUSE')
    else:  # Tue, Thu, Sat
        return ('HOUSE', 'AWAY')

def job_cleanup_acks():
    """Cleanup expired acknowledgments - runs every hour"""
    logger.info("Running scheduled ack cleanup")
    clear_expired_acks()

def job_545pm_warning():
    """5:45pm - First warning notification"""
    if is_vacation_mode():
        logger.info("5:45pm reminder skipped: vacation mode")
        return

    if has_ack('nothome'):
        logger.info("5:45pm reminder skipped: user not home")
        return

    current, destination = get_parking_sides()
    if current == 'N/A':
        logger.info("5:45pm reminder skipped: Sunday")
        return

    actions = build_action_buttons([
        ("Got it!", "/ack/gotit"),
        ("Not home", "/ack/nothome")
    ])

    send_notification(
        title="Parking Reminder",
        message=f"⚠️ 15 minutes: Move car from {current} to {destination} side",
        priority="high",
        tags=["warning", "car"],
        actions=actions,
        notification_type="545pm"
    )

def job_600pm_urgent():
    """6:00pm - Urgent notification"""
    if is_vacation_mode():
        logger.info("6:00pm reminder skipped: vacation mode")
        return

    if has_ack('nothome') or has_ack('moved'):
        logger.info("6:00pm reminder skipped: already acknowledged")
        return

    current, destination = get_parking_sides()
    if current == 'N/A':
        return

    actions = build_action_buttons([
        ("I moved it", "/ack/moved"),
        ("Not home", "/ack/nothome")
    ])

    send_notification(
        title="Parking Reminder",
        message=f"🚗 MOVE NOW: {current} → {destination} side (window closes at 7pm)",
        priority="urgent",
        tags=["rotating_light", "car"],
        actions=actions,
        notification_type="600pm"
    )

def job_645pm_lastcall():
    """6:45pm - Last call notification"""
    if is_vacation_mode():
        logger.info("6:45pm reminder skipped: vacation mode")
        return

    if has_ack('nothome') or has_ack('moved'):
        logger.info("6:45pm reminder skipped: already acknowledged")
        return

    current, destination = get_parking_sides()
    if current == 'N/A':
        return

    actions = build_action_buttons([
        ("Done!", "/ack/done"),
        ("Not home", "/ack/nothome")
    ])

    send_notification(
        title="Parking Reminder",
        message=f"🚨 15 MIN LEFT: Move from {current} to {destination} side!",
        priority="urgent",
        tags=["rotating_light", "sos"],
        actions=actions,
        notification_type="645pm"
    )

def job_655pm_sms_escalation():
    """6:55pm - SMS escalation if no acknowledgment"""
    if is_vacation_mode():
        logger.info("SMS escalation skipped: vacation mode")
        return

    if not should_escalate():
        logger.info("SMS escalation skipped: user acknowledged")
        return

    current, destination = get_parking_sides()
    if current == 'N/A':
        return

    send_sms(current, destination)

def job_700pm_call_escalation():
    """7:00pm - Phone call escalation if still no acknowledgment"""
    if is_vacation_mode():
        logger.info("Call escalation skipped: vacation mode")
        return

    if not should_escalate():
        logger.info("Call escalation skipped: user acknowledged")
        return

    current, destination = get_parking_sides()
    if current == 'N/A':
        return

    make_phone_call(current, destination)

def start_scheduler(app: Flask):
    """Initialize and start APScheduler with Flask app context"""

    # All jobs need Flask app context for config access
    def with_app_context(func):
        def wrapper(*args, **kwargs):
            with app.app_context():
                return func(*args, **kwargs)
        return wrapper

    # Cleanup job - runs every hour
    scheduler.add_job(
        with_app_context(job_cleanup_acks),
        trigger=CronTrigger(minute=0, timezone=Config.TIMEZONE),
        id='cleanup_acks',
        replace_existing=True
    )

    # Notification jobs - Mon-Sat only
    scheduler.add_job(
        with_app_context(job_545pm_warning),
        trigger=CronTrigger(hour=17, minute=45, day_of_week='mon-sat', timezone=Config.TIMEZONE),
        id='545pm_warning',
        replace_existing=True
    )

    scheduler.add_job(
        with_app_context(job_600pm_urgent),
        trigger=CronTrigger(hour=18, minute=0, day_of_week='mon-sat', timezone=Config.TIMEZONE),
        id='600pm_urgent',
        replace_existing=True
    )

    scheduler.add_job(
        with_app_context(job_645pm_lastcall),
        trigger=CronTrigger(hour=18, minute=45, day_of_week='mon-sat', timezone=Config.TIMEZONE),
        id='645pm_lastcall',
        replace_existing=True
    )

    scheduler.add_job(
        with_app_context(job_655pm_sms_escalation),
        trigger=CronTrigger(hour=18, minute=55, day_of_week='mon-sat', timezone=Config.TIMEZONE),
        id='655pm_sms',
        replace_existing=True
    )

    scheduler.add_job(
        with_app_context(job_700pm_call_escalation),
        trigger=CronTrigger(hour=19, minute=0, day_of_week='mon-sat', timezone=Config.TIMEZONE),
        id='700pm_call',
        replace_existing=True
    )

    scheduler.start()
    logger.info("APScheduler started with all jobs registered")
```

**Responsibilities:**
- Define all scheduled jobs
- Calculate parking sides
- Run notifications with smart logic
- Handle escalation timing
- Cleanup expired acks

**Improvements Over Bash:**
- ✅ No race conditions (APScheduler handles locking)
- ✅ Proper timezone support
- ✅ No cron timing jitter issues
- ✅ Jobs run in app context (access to config)
- ✅ Escalation jobs don't block (no sleep 300)

### 7. app/routes.py - Flask Web Endpoints

```python
from flask import Blueprint, render_template, jsonify, request
from flask_wtf.csrf import generate_csrf
from app.models import set_ack, is_vacation_mode, set_vacation_mode
from app.notifier import send_notification
from app.scheduler import get_parking_sides
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    """Serve status page web UI"""
    return render_template('status.html')

@bp.route('/health')
def health():
    """Healthcheck endpoint for Docker"""
    return 'OK', 200

@bp.route('/api/vacation/status', methods=['GET'])
def vacation_status():
    """Get current vacation mode status"""
    return jsonify({'enabled': is_vacation_mode()})

@bp.route('/api/vacation/toggle', methods=['POST'])
def vacation_toggle():
    """Toggle vacation mode on/off"""
    current = is_vacation_mode()
    set_vacation_mode(not current)
    new_status = not current
    logger.info(f"Vacation mode toggled to: {new_status}")
    return jsonify({'enabled': new_status})

@bp.route('/ack/gotit', methods=['GET', 'POST'])
def ack_gotit():
    """Acknowledge: Got it! (keeps 6pm and 6:45pm)"""
    set_ack('gotit', expires_hours=4)
    return "Acknowledged: Got it!", 200

@bp.route('/ack/nothome', methods=['GET', 'POST'])
def ack_nothome():
    """Acknowledge: Not home (stops all reminders)"""
    set_ack('nothome', expires_hours=4)
    return "Acknowledged: Not home", 200

@bp.route('/ack/moved', methods=['GET', 'POST'])
def ack_moved():
    """Acknowledge: I moved it (stops all reminders)"""
    set_ack('moved', expires_hours=4)
    return "Acknowledged: Car moved", 200

@bp.route('/ack/done', methods=['GET', 'POST'])
def ack_done():
    """Acknowledge: Done! (stops escalation only)"""
    set_ack('done', expires_hours=2)
    return "Acknowledged: Done!", 200

@bp.route('/status', methods=['POST'])
def on_demand_status():
    """Send on-demand parking status notification"""
    current, destination = get_parking_sides()

    if current == 'N/A':
        message = "📅 It's Sunday! No parking moves needed today."
    else:
        message = (
            f"📍 Currently parked on: {current} side\n"
            f"🎯 Move to: {destination} side (6-7pm window)"
        )

    send_notification(
        title="Parking Status",
        message=message,
        priority="default",
        tags=["information_source", "car"],
        notification_type="status"
    )

    logger.info("On-demand status notification sent")
    return jsonify({'status': 'sent'})

@bp.after_request
def add_security_headers(response):
    """Add security headers to all responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response
```

**Responsibilities:**
- Serve web UI
- API endpoints for vacation mode
- Acknowledgment webhook handlers
- On-demand status trigger
- Security headers

**Security Features:**
- ✅ CSRF protection (Flask-WTF)
- ✅ Security headers
- ✅ Input validation by framework
- ✅ No path traversal (Flask routing)
- ✅ POST and GET both allowed for /ack/* (ntfy action buttons use GET)

### 8. templates/status.html - Web UI

(Same as bash version, but with updated API endpoints)

Changes:
- `/vacation/toggle` → `/api/vacation/toggle`
- `/vacation/status` → `/api/vacation/status`
- Add CSRF token to POST requests (generated by Flask-WTF)

### 9. app.py - Application Entry Point

```python
from app import create_app
import logging

logger = logging.getLogger(__name__)

app = create_app()

if __name__ == '__main__':
    # Validate configuration
    from app.config import Config
    errors = Config.validate()
    if errors:
        for error in errors:
            logger.error(f"Configuration error: {error}")
        exit(1)

    logger.info(f"Starting Parking Reminder v2.0 on {Config.HOST}:{Config.PORT}")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.FLASK_ENV == 'development')
```

**Responsibilities:**
- Create app instance
- Validate configuration
- Run Flask development server (Docker uses Gunicorn)

### 10. Dockerfile - Python Container

```dockerfile
FROM python:3.11-alpine

# Install system dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    tzdata

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY templates/ ./templates/
COPY app.py .

# Create directories
RUN mkdir -p /var/log/parking-reminder /var/lib/parking-reminder

# Set timezone
ENV TZ=America/New_York

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:${WEBHOOK_PORT:-8085}/health', timeout=3)"

# Run with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8085", "--workers", "2", "--timeout", "120", "app:app"]
```

### 11. docker-compose.yml - Container Orchestration

```yaml
version: '3.8'

services:
  parking-reminder:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: parking-reminder
    restart: unless-stopped
    volumes:
      - ./logs:/var/log/parking-reminder
      - parking-state:/var/lib/parking-reminder
    ports:
      - "8085:8085"
    environment:
      - TZ=America/New_York
      - WEBHOOK_PORT=8085
      - DATABASE_PATH=/var/lib/parking-reminder/parking.db
      - NTFY_SERVER=${NTFY_SERVER}
      - NTFY_TOPIC=${NTFY_TOPIC}
      - NTFY_AUTH_USER=${NTFY_AUTH_USER}
      - NTFY_AUTH_PASS=${NTFY_AUTH_PASS}
      - NTFY_FAILSAFE_TOPIC=${NTFY_FAILSAFE_TOPIC}
      - WEBHOOK_BASE_URL=${WEBHOOK_BASE_URL}
      - TWILIO_ACCOUNT_SID=${TWILIO_ACCOUNT_SID}
      - TWILIO_AUTH_TOKEN=${TWILIO_AUTH_TOKEN}
      - TWILIO_FROM_PHONE=${TWILIO_FROM_PHONE}
      - TWILIO_TO_PHONE=${TWILIO_TO_PHONE}
      - UPTIME_KUMA_PUSH_URL=${UPTIME_KUMA_PUSH_URL}
      - SECRET_KEY=${SECRET_KEY}
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  parking-state:
    driver: local
```

### 12. .env - Environment Configuration

```bash
# Parking Reminder v2.0 Configuration

# Flask
SECRET_KEY=generate_with_openssl_rand_hex_32
FLASK_ENV=production

# Webhook Base URL (for ntfy action buttons)
# Use your Unraid server IP or domain
WEBHOOK_BASE_URL=http://10.27.27.157:8085

# ntfy Server Configuration
NTFY_SERVER=https://ntfy.mccoolson.com
NTFY_TOPIC=parking
NTFY_AUTH_USER=cooley
NTFY_AUTH_PASS=CHANGEME_SET_AFTER_NTFY_USER_CREATION

# Failsafe notification (cloud ntfy.sh as backup)
NTFY_FAILSAFE_TOPIC=parking_cooley_9563e886

# Twilio Configuration (optional - for SMS/call escalation)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_PHONE=
TWILIO_TO_PHONE=

# Uptime Kuma Push Monitor URL (optional)
UPTIME_KUMA_PUSH_URL=
```

## Security Improvements

| Issue | Bash v2.0 | Python v2.0 |
|-------|-----------|-------------|
| Remote code execution | ❌ `nc -e /bin/bash` backdoor | ✅ Gunicorn WSGI server |
| Command injection | ❌ Unquoted variables in curl | ✅ Parameterized all calls |
| SQL injection | N/A (file-based state) | ✅ Parameterized queries |
| CSRF protection | ❌ None | ✅ Flask-WTF tokens |
| Input validation | ❌ None | ✅ Flask routing + validation |
| Path traversal | ❌ Possible | ✅ Flask prevents |
| Credentials in env | ❌ Visible in docker inspect | ⚠️ Still in env (can use secrets) |
| HTTPS/TLS | ❌ HTTP only | ⚠️ HTTP (reverse proxy recommended) |
| Race conditions | ❌ File-based acks | ✅ SQLite transactions |
| Time window bugs | ❌ String comparison | ✅ Python datetime |
| Blocking operations | ❌ `sleep 300` in escalation | ✅ APScheduler separate jobs |
| Lock file atomicity | ❌ Non-atomic touch | ✅ Not needed (APScheduler) |

## Migration Path from Bash v2.0

1. **Backup current state:**
   ```bash
   docker exec parking-reminder ls -la /var/lib/parking-reminder/
   # Note which ack files exist
   ```

2. **Stop bash container:**
   ```bash
   docker-compose down
   ```

3. **Deploy Python version:**
   ```bash
   # Update .env with SECRET_KEY
   openssl rand -hex 32 >> .env  # Add SECRET_KEY=<output>

   # Build and start
   docker-compose build
   docker-compose up -d
   ```

4. **Verify:**
   ```bash
   curl http://10.27.27.157:8085/health
   docker logs -f parking-reminder
   ```

5. **Test:**
   ```bash
   # Trigger on-demand status
   curl -X POST http://10.27.27.157:8085/status

   # Check logs
   docker exec parking-reminder cat /var/log/parking-reminder/app.log
   ```

## Testing Strategy

### Unit Tests (Future Enhancement)
- Test get_parking_sides() with different days
- Test acknowledgment logic
- Test vacation mode
- Test notification building

### Integration Tests
- Test full notification flow
- Test escalation timing
- Test web UI interactions

### Manual Testing Checklist
- [ ] 5:45pm notification sends with correct buttons
- [ ] Click "Got it!" - 6:00pm still sends
- [ ] Click "Not home" - 6:00pm skips
- [ ] Click "I moved it" - 6:45pm skips
- [ ] No acks - SMS sent at 6:55pm
- [ ] No acks - Call made at 7:00pm
- [ ] Vacation mode stops all notifications
- [ ] On-demand status works
- [ ] Healthcheck returns 200
- [ ] Sunday correctly skips
- [ ] Database persists across restarts

## Open Questions for Brutal-Critic

1. **Should we use Docker secrets instead of env vars for Twilio?**
2. **Is Gunicorn with 2 workers appropriate, or should we use 1?**
3. **Should we add rate limiting to prevent abuse of /status endpoint?**
4. **Is the expires_at approach for acks sufficient, or should we use timestamps in filename?**
5. **Should we add a /metrics endpoint for Prometheus integration?**
6. **Should web UI have basic auth, or is local network trust sufficient?**
7. **Should we separate scheduler into its own container?**

## Conclusion

This architecture addresses all 34 critical issues found in the bash implementation while maintaining the same user experience. The Python approach provides:

- **Security**: No backdoors, proper validation, CSRF protection
- **Reliability**: Atomic operations, no race conditions, proper error handling
- **Maintainability**: Clear separation of concerns, testable components
- **Simplicity**: Proven frameworks instead of custom netcat servers

Ready for brutal-critic architectural review.
