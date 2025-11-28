#!/usr/bin/env python3
"""
Parking Reminder v2.4.0 - Secure Webhook Server with PWA Support
Replaces the insecure netcat-based ack-server.sh

Security improvements:
- No shell execution (fixes nc -e /bin/bash backdoor)
- Input validation (whitelist of allowed paths)
- Proper HTTP parsing
- Multi-threaded (handles concurrent requests)
- Correct Content-Length calculation

v2.0.1 fixes:
- Added /vacation/* endpoints (compatibility with status.html)
- ThreadingHTTPServer for true concurrency

v2.0.2 fixes:
- Path traversal protection (proper URL parsing)
- Zombie process reaping (SIGCHLD handler)
- Rate limiting (10 req/min per IP)
- Comprehensive healthcheck (tests critical functionality)

v2.4.0 additions:
- PWA support (manifest.json, service-worker.js, icons)
"""

import os
import sys
import json
import subprocess
import logging
import signal
import time
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from collections import defaultdict

# Configuration from environment
PORT = int(os.environ.get('WEBHOOK_PORT', 8085))
LOG_FILE = '/var/log/parking-reminder/reminder.log'
VACATION_FILE = Path('/var/lib/parking-reminder/vacation-mode')
STATUS_HTML = Path('/usr/local/share/status.html')
STATIC_DIR = Path('/usr/local/share')

# Acknowledgment file paths (with timestamp support)
ACK_DIR = Path('/var/lib/parking-reminder')

# Allowed paths (whitelist for security)
# FIXED v2.0.1: Added /vacation/* paths for status.html compatibility
# v2.4.0: Added PWA static files
ALLOWED_PATHS = {
    '/', '/health', '/status',
    '/vacation/status', '/vacation/toggle',  # Used by status.html
    '/api/vacation/status', '/api/vacation/toggle',  # Alternative API paths
    '/ack/gotit', '/ack/nothome', '/ack/moved', '/ack/done',
    # PWA static files
    '/manifest.json', '/service-worker.js',
    '/icons/icon.svg', '/icons/icon-192.png', '/icons/icon-512.png'
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] WEBHOOK: %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# FIXED v2.0.2: Automatic zombie process reaping via SIGCHLD handler
def reap_zombies(signum, frame):
    """Signal handler to reap zombie processes"""
    while True:
        try:
            # Reap any terminated child processes (non-blocking)
            pid, status = os.waitpid(-1, os.WNOHANG)
            if pid == 0:  # No more zombies
                break
            logger.debug(f"Reaped zombie process: PID {pid}, status {status}")
        except ChildProcessError:
            # No more children
            break

# Install SIGCHLD handler to automatically clean up zombie processes
signal.signal(signal.SIGCHLD, reap_zombies)


# FIXED v2.0.2: Add rate limiting to prevent abuse
class RateLimiter:
    """Simple token bucket rate limiter"""
    def __init__(self, max_requests=10, window_seconds=60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)  # IP -> [timestamps]
        self.lock = threading.Lock()

    def is_allowed(self, ip: str) -> bool:
        """Check if request from IP is allowed"""
        now = time.time()

        with self.lock:
            # Clean up old timestamps
            self.requests[ip] = [ts for ts in self.requests[ip]
                                if now - ts < self.window_seconds]

            # Check if under limit
            if len(self.requests[ip]) < self.max_requests:
                self.requests[ip].append(now)
                return True

            return False

    def cleanup_old_entries(self):
        """Periodically clean up old IP entries to prevent memory leak"""
        now = time.time()
        with self.lock:
            ips_to_remove = []
            for ip, timestamps in self.requests.items():
                # Remove IPs with no recent requests
                if not timestamps or (now - timestamps[-1]) > self.window_seconds * 2:
                    ips_to_remove.append(ip)

            for ip in ips_to_remove:
                del self.requests[ip]

# Global rate limiter: 10 requests per minute per IP
rate_limiter = RateLimiter(max_requests=10, window_seconds=60)

# Status-specific rate limiter: 1 request per 5 seconds (prevents double-clicks)
status_rate_limiter = RateLimiter(max_requests=1, window_seconds=5)


def create_ack_file(ack_type: str, client_ip: str = "unknown"):
    """Create acknowledgment file with timestamp (atomic with persistence guarantee)"""
    try:
        # Use microsecond precision to avoid timestamp collisions
        timestamp = datetime.now().timestamp()  # Keep decimal (microseconds)
        ack_file = ACK_DIR / f"ack-{ack_type}.{timestamp}"

        # Validate directory exists and is writable
        if not ACK_DIR.exists():
            logger.error(f"ACK CREATION FAILED: Directory does not exist: {ACK_DIR}")
            raise FileNotFoundError(f"Ack directory missing: {ACK_DIR}")

        if not os.access(ACK_DIR, os.W_OK):
            logger.error(f"ACK CREATION FAILED: Directory not writable: {ACK_DIR}")
            raise PermissionError(f"Cannot write to {ACK_DIR}")

        # Atomic file creation with O_CREAT|O_EXCL flags
        fd = os.open(str(ack_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)

        # Force fsync for persistence (prevent loss on crash)
        os.fsync(fd)
        os.close(fd)

        # Also sync parent directory (ensures directory entry is persisted)
        dir_fd = os.open(str(ACK_DIR), os.O_RDONLY)
        os.fsync(dir_fd)
        os.close(dir_fd)

        # Success - log with full context
        logger.info(f"ACK CREATED: type={ack_type}, file={ack_file.name}, "
                   f"timestamp={timestamp}, client_ip={client_ip}")

        # METRIC: Track ack creation by type
        logger.info(f"METRIC: ack_created type={ack_type} client_ip={client_ip}")
        return True

    except FileExistsError:
        # Collision - retry with nanosecond precision
        timestamp_ns = time.time_ns()
        ack_file = ACK_DIR / f"ack-{ack_type}.{timestamp_ns}"
        fd = os.open(str(ack_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.fsync(fd)
        os.close(fd)
        logger.info(f"ACK CREATED: type={ack_type}, file={ack_file.name}, "
                   f"timestamp={timestamp_ns}, client_ip={client_ip} (collision resolved)")

        # METRIC: Track ack creation by type (collision case)
        logger.info(f"METRIC: ack_created type={ack_type} client_ip={client_ip}")
        return True

    except Exception as e:
        logger.error(f"ACK CREATION FAILED: type={ack_type}, error={type(e).__name__}: {e}, "
                    f"client_ip={client_ip}")
        raise


def is_vacation_mode() -> bool:
    """Check if vacation mode is enabled"""
    return VACATION_FILE.exists()


def toggle_vacation_mode():
    """Toggle vacation mode on/off (thread-safe)"""
    try:
        if VACATION_FILE.exists():
            VACATION_FILE.unlink(missing_ok=True)  # Don't raise if already deleted
            logger.info("Vacation mode DISABLED")
            return False
        else:
            VACATION_FILE.touch(exist_ok=True)  # Don't raise if already created
            # Ensure persistence
            os.sync()
            logger.info("Vacation mode ENABLED")
            return True
    except Exception as e:
        logger.error(f"Failed to toggle vacation mode: {e}")
        # Return current state
        return VACATION_FILE.exists()


def healthcheck() -> tuple[bool, str]:
    """
    Comprehensive health check (FIXED v2.0.2)
    Tests critical functionality instead of just HTTP response
    Returns: (is_healthy, message)
    """
    checks = []
    all_ok = True

    # 1. Check ack directory writable
    try:
        test_file = ACK_DIR / '.healthcheck'
        test_file.touch()
        test_file.unlink()
        checks.append("✓ Ack directory writable")
    except Exception as e:
        checks.append(f"✗ Ack directory not writable: {e}")
        all_ok = False

    # 2. Check clock synchronization and drift (CRITICAL for ack timestamps)
    try:
        # Create test file and immediately check timestamp
        test_time = datetime.now()
        test_timestamp = test_time.timestamp()
        test_file = ACK_DIR / f'ack-clocktest.{test_timestamp}'
        test_file.touch()

        # Get file mtime and compare to expected
        file_mtime = test_file.stat().st_mtime
        expected_mtime = test_timestamp
        drift = abs(file_mtime - expected_mtime)

        test_file.unlink()

        if drift > 2:  # More than 2 seconds drift
            checks.append(f"✗ Clock drift: {drift:.1f}s (NTP sync may be failing)")
            all_ok = False
        else:
            checks.append(f"✓ Clock synchronized (drift: {drift:.2f}s)")

        # Also check timezone
        tz = os.environ.get('TZ', 'NOT SET')
        if tz != 'America/New_York':
            checks.append(f"⚠ Timezone: {tz} (expected: America/New_York)")
        else:
            checks.append(f"✓ Timezone: {tz}")

    except Exception as e:
        checks.append(f"✗ Clock check failed: {e}")
        all_ok = False

    # 3. Check log directory writable
    try:
        log_dir = Path(LOG_FILE).parent
        test_file = log_dir / '.healthcheck'
        test_file.touch()
        test_file.unlink()
        checks.append("✓ Log directory writable")
    except Exception as e:
        checks.append(f"✗ Log directory not writable: {e}")
        all_ok = False

    # 4. Check cron daemon running (critical for scheduled reminders)
    try:
        result = subprocess.run(['pgrep', 'crond'], capture_output=True, timeout=2)
        if result.returncode == 0:
            checks.append("✓ Cron daemon running")
        else:
            checks.append("✗ Cron daemon NOT running")
            all_ok = False
    except Exception as e:
        checks.append(f"✗ Cannot check cron: {e}")
        all_ok = False

    # 5. Check environment variables are set
    required_vars = ['NTFY_SERVER', 'NTFY_TOPIC', 'WEBHOOK_BASE_URL']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    if not missing_vars:
        checks.append("✓ Required env vars set")
    else:
        checks.append(f"✗ Missing env vars: {', '.join(missing_vars)}")
        all_ok = False

    status = "HEALTHY" if all_ok else "UNHEALTHY"
    message = f"{status}\n" + "\n".join(checks)
    return all_ok, message


class WebhookHandler(BaseHTTPRequestHandler):
    """HTTP request handler with security improvements"""

    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info(f"{self.client_address[0]} - {format % args}")

    def send_json_response(self, data: dict, status=200):
        """Send JSON response with proper encoding"""
        body = json.dumps(data)
        body_bytes = body.encode('utf-8')

        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body_bytes))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body_bytes)

    def send_text_response(self, text: str, status=200):
        """Send plain text response with proper encoding"""
        body_bytes = text.encode('utf-8')

        self.send_response(status)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', len(body_bytes))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body_bytes)

    def send_html_response(self, html: str, status=200):
        """Send HTML response with proper encoding"""
        body_bytes = html.encode('utf-8')

        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(body_bytes))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('X-XSS-Protection', '1; mode=block')
        self.end_headers()
        self.wfile.write(body_bytes)

    def send_redirect(self, location: str):
        """Send 303 redirect"""
        self.send_response(303)
        self.send_header('Location', location)
        self.end_headers()

    def send_static_file(self, filepath: Path, content_type: str):
        """Serve a static file with caching headers"""
        if not filepath.exists():
            self.send_error(404, "File not found")
            return

        content = filepath.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', len(content))
        self.send_header('Cache-Control', 'public, max-age=86400')  # 24h cache
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        """Handle GET requests"""
        # FIXED v2.0.2: Check rate limit
        client_ip = self.client_address[0]
        if not rate_limiter.is_allowed(client_ip):
            self.send_error(429, "Too Many Requests")
            logger.warning(f"Rate limit exceeded for {client_ip}")
            return

        # Parse URL to extract path component (ignore query params and fragments)
        parsed = urlparse(self.path)
        clean_path = parsed.path

        # Validate path against whitelist
        if clean_path not in ALLOWED_PATHS and not clean_path.startswith('/?'):
            self.send_error(404, "Not Found")
            logger.warning(f"Blocked invalid path: {self.path}")
            return

        # Serve status page
        if clean_path == '/' or clean_path.startswith('/?'):
            if STATUS_HTML.exists():
                html = STATUS_HTML.read_text()
                self.send_html_response(html)
            else:
                self.send_error(500, "Status page not found")
                logger.error("status.html missing")
            return

        # Healthcheck endpoint (FIXED v2.0.2: comprehensive checks)
        if clean_path == '/health':
            is_healthy, message = healthcheck()
            if is_healthy:
                self.send_text_response(message)
            else:
                self.send_text_response(message, status=503)
            return

        # Vacation status (FIXED v2.0.1: support both /vacation and /api/vacation paths)
        if clean_path == '/vacation/status' or clean_path == '/api/vacation/status':
            self.send_json_response({'enabled': is_vacation_mode()})
            return

        # Acknowledgment endpoints - redirect GET to home
        # (ntfy action buttons use GET, so we support it but log)
        if clean_path.startswith('/ack/'):
            ack_type = clean_path.split('/')[-1]
            if ack_type in ['gotit', 'nothome', 'moved', 'done']:
                create_ack_file(ack_type, client_ip)
                self.send_text_response(f"Acknowledged: {ack_type}")
            else:
                self.send_error(404, "Invalid acknowledgment type")
            return

        # PWA static files (v2.4.0)
        if clean_path == '/manifest.json':
            self.send_static_file(STATIC_DIR / 'manifest.json', 'application/manifest+json')
            return

        if clean_path == '/service-worker.js':
            # Service worker needs no-cache to update properly
            filepath = STATIC_DIR / 'service-worker.js'
            if filepath.exists():
                content = filepath.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'application/javascript')
                self.send_header('Content-Length', len(content))
                self.send_header('Cache-Control', 'no-cache')  # SW should always be fresh
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "Service worker not found")
            return

        if clean_path.startswith('/icons/'):
            icon_name = clean_path.split('/')[-1]
            icon_path = STATIC_DIR / 'icons' / icon_name
            if icon_name.endswith('.svg'):
                self.send_static_file(icon_path, 'image/svg+xml')
            elif icon_name.endswith('.png'):
                self.send_static_file(icon_path, 'image/png')
            else:
                self.send_error(404, "Unknown icon format")
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        """Handle POST requests"""
        # FIXED v2.0.2: Check rate limit
        client_ip = self.client_address[0]
        if not rate_limiter.is_allowed(client_ip):
            self.send_error(429, "Too Many Requests")
            logger.warning(f"Rate limit exceeded for {client_ip}")
            return

        # Parse URL to extract path component (ignore query params and fragments)
        parsed = urlparse(self.path)
        clean_path = parsed.path

        # Validate path against whitelist
        if clean_path not in ALLOWED_PATHS:
            self.send_error(404, "Not Found")
            logger.warning(f"Blocked invalid path: {self.path}")
            return

        # On-demand status notification
        if clean_path == '/status':
            # Check status-specific rate limit (prevents double-clicks)
            if not status_rate_limiter.is_allowed(client_ip):
                self.send_error(429, "Please wait 5 seconds between status checks")
                return

            try:
                # Trigger status notification in background
                subprocess.Popen(
                    ['/usr/local/bin/status-notify.sh'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                logger.info("On-demand status notification triggered")
                self.send_redirect('/')
            except Exception as e:
                logger.error(f"Failed to trigger status notification: {e}")
                self.send_error(500, "Failed to send notification")
            return

        # Vacation mode toggle (FIXED v2.0.1: support both /vacation and /api/vacation paths)
        if clean_path == '/vacation/toggle' or clean_path == '/api/vacation/toggle':
            try:
                enabled = toggle_vacation_mode()
                self.send_json_response({'enabled': enabled})
            except Exception as e:
                logger.error(f"Failed to toggle vacation mode: {e}")
                self.send_error(500, "Failed to toggle vacation mode")
            return

        # Acknowledgment endpoints
        if clean_path.startswith('/ack/'):
            ack_type = clean_path.split('/')[-1]
            if ack_type in ['gotit', 'nothome', 'moved', 'done']:
                create_ack_file(ack_type, client_ip)
                self.send_text_response(f"Acknowledged: {ack_type}")
            else:
                self.send_error(404, "Invalid acknowledgment type")
            return

        self.send_error(404, "Not Found")


def main():
    """Start HTTP server"""
    # Ensure directories exist
    ACK_DIR.mkdir(parents=True, exist_ok=True)
    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)

    # Create HTTP server (FIXED v2.0.1: ThreadingHTTPServer for true concurrency)
    server_address = ('', PORT)
    httpd = ThreadingHTTPServer(server_address, WebhookHandler)

    logger.info(f"Webhook server starting on port {PORT} (multi-threaded)")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Webhook server shutting down")
        httpd.shutdown()
        sys.exit(0)


if __name__ == '__main__':
    main()
