#!/usr/bin/env python3
"""
Parking Reminder v2.0.2 - Secure Webhook Server
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

# Acknowledgment file paths (with timestamp support)
ACK_DIR = Path('/var/lib/parking-reminder')

# Allowed paths (whitelist for security)
# FIXED v2.0.1: Added /vacation/* paths for status.html compatibility
ALLOWED_PATHS = {
    '/', '/health', '/status',
    '/vacation/status', '/vacation/toggle',  # Used by status.html
    '/api/vacation/status', '/api/vacation/toggle',  # Alternative API paths
    '/ack/gotit', '/ack/nothome', '/ack/moved', '/ack/done'
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


def create_ack_file(ack_type: str):
    """Create acknowledgment file with timestamp"""
    timestamp = int(datetime.now().timestamp())
    ack_file = ACK_DIR / f"ack-{ack_type}.{timestamp}"
    ack_file.touch()
    logger.info(f"Acknowledgment created: {ack_type}")


def is_vacation_mode() -> bool:
    """Check if vacation mode is enabled"""
    return VACATION_FILE.exists()


def toggle_vacation_mode():
    """Toggle vacation mode on/off"""
    if VACATION_FILE.exists():
        VACATION_FILE.unlink()
        logger.info("Vacation mode DISABLED")
        return False
    else:
        VACATION_FILE.touch()
        logger.info("Vacation mode ENABLED")
        return True


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

    # 2. Check log directory writable
    try:
        log_dir = Path(LOG_FILE).parent
        test_file = log_dir / '.healthcheck'
        test_file.touch()
        test_file.unlink()
        checks.append("✓ Log directory writable")
    except Exception as e:
        checks.append(f"✗ Log directory not writable: {e}")
        all_ok = False

    # 3. Check cron daemon running (critical for scheduled reminders)
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

    # 4. Check environment variables are set
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
                create_ack_file(ack_type)
                self.send_text_response(f"Acknowledged: {ack_type}")
            else:
                self.send_error(404, "Invalid acknowledgment type")
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
                create_ack_file(ack_type)
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
