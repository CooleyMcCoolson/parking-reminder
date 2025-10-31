"""
Parking Reminder v2.0 - Configuration
Loads and validates environment variables
"""
import os
from typing import Optional


class Config:
    """Application configuration from environment variables"""

    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(24).hex())
    FLASK_ENV = os.environ.get('FLASK_ENV', 'production')

    # Server
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('WEBHOOK_PORT', 8085))

    # Database
    DATABASE_PATH = os.environ.get('DATABASE_PATH', '/var/lib/parking-reminder/parking.db')

    # Timezone
    TIMEZONE = os.environ.get('TZ', 'America/New_York')

    # ntfy Configuration
    NTFY_SERVER = os.environ.get('NTFY_SERVER', 'https://ntfy.sh')
    NTFY_TOPIC = os.environ.get('NTFY_TOPIC')
    NTFY_AUTH_USER = os.environ.get('NTFY_AUTH_USER')
    NTFY_AUTH_PASS = os.environ.get('NTFY_AUTH_PASS')
    NTFY_FAILSAFE_TOPIC = os.environ.get('NTFY_FAILSAFE_TOPIC')

    # Webhook Base URL (for action buttons)
    # Uses environment variable or falls back to constructed URL
    WEBHOOK_BASE_URL = os.environ.get('WEBHOOK_BASE_URL', f'http://YOUR_SERVER_IP:{PORT}')

    # Twilio Configuration (optional)
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_FROM_PHONE = os.environ.get('TWILIO_FROM_PHONE')
    TWILIO_TO_PHONE = os.environ.get('TWILIO_TO_PHONE')

    # Uptime Kuma (optional)
    UPTIME_KUMA_PUSH_URL = os.environ.get('UPTIME_KUMA_PUSH_URL')

    @classmethod
    def validate(cls) -> list[str]:
        """Validate required configuration and return list of errors"""
        errors = []

        if not cls.NTFY_TOPIC:
            errors.append("NTFY_TOPIC environment variable is required")

        # Validate Twilio config if any Twilio var is set
        twilio_vars = [cls.TWILIO_ACCOUNT_SID, cls.TWILIO_AUTH_TOKEN,
                       cls.TWILIO_FROM_PHONE, cls.TWILIO_TO_PHONE]
        twilio_set = [v for v in twilio_vars if v]

        if twilio_set and len(twilio_set) != 4:
            errors.append("If using Twilio, all four variables must be set: "
                         "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
                         "TWILIO_FROM_PHONE, TWILIO_TO_PHONE")

        return errors

    @classmethod
    def has_twilio(cls) -> bool:
        """Check if Twilio is configured"""
        return all([cls.TWILIO_ACCOUNT_SID, cls.TWILIO_AUTH_TOKEN,
                    cls.TWILIO_FROM_PHONE, cls.TWILIO_TO_PHONE])

    @classmethod
    def has_ntfy_auth(cls) -> bool:
        """Check if ntfy authentication is configured"""
        return bool(cls.NTFY_AUTH_USER and cls.NTFY_AUTH_PASS)
