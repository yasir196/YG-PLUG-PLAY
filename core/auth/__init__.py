"""Single-admin local authentication and HTTP security."""

from .app import create_app
from .service import AuthService

__all__ = ["AuthService", "create_app"]
