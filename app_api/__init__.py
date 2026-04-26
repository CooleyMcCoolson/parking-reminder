"""Future FastAPI app package for parking-reminder."""

from .main import create_app
from .settings import AppSettings

__all__ = ["AppSettings", "create_app"]
