#!/usr/bin/env python3
"""
Parking Reminder v2.0.1 - Secure Webhook Server
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
"""

import os
import sys
import json
import subprocess
import logging
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime

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
        # Validate path against whitelist
        if self.path not in ALLOWED_PATHS and not self.path.startswith('/?'):
            self.send_error(404, "Not Found")
            logger.warning(f"Blocked invalid path: {self.path}")
            return

        # Serve status page
        if self.path == '/' or self.path.startswith('/?'):
            if STATUS_HTML.exists():
                html = STATUS_HTML.read_text()
                self.send_html_response(html)
            else:
                self.send_error(500, "Status page not found")
                logger.error("status.html missing")
            return

        # Healthcheck endpoint
        if self.path == '/health':
            self.send_text_response('OK')
            return

        # Vacation status (FIXED v2.0.1: support both /vacation and /api/vacation paths)
        if self.path == '/vacation/status' or self.path == '/api/vacation/status':
            self.send_json_response({'enabled': is_vacation_mode()})
            return

        # Acknowledgment endpoints - redirect GET to home
        # (ntfy action buttons use GET, so we support it but log)
        if self.path.startswith('/ack/'):
            ack_type = self.path.split('/')[-1]
            if ack_type in ['gotit', 'nothome', 'moved', 'done']:
                create_ack_file(ack_type)
                self.send_text_response(f"Acknowledged: {ack_type}")
            else:
                self.send_error(404, "Invalid acknowledgment type")
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        """Handle POST requests"""
        # Validate path against whitelist
        if self.path not in ALLOWED_PATHS:
            self.send_error(404, "Not Found")
            logger.warning(f"Blocked invalid path: {self.path}")
            return

        # On-demand status notification
        if self.path == '/status':
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
        if self.path == '/vacation/toggle' or self.path == '/api/vacation/toggle':
            try:
                enabled = toggle_vacation_mode()
                self.send_json_response({'enabled': enabled})
            except Exception as e:
                logger.error(f"Failed to toggle vacation mode: {e}")
                self.send_error(500, "Failed to toggle vacation mode")
            return

        # Acknowledgment endpoints
        if self.path.startswith('/ack/'):
            ack_type = self.path.split('/')[-1]
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
