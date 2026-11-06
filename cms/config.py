"""Application settings.

Values can be overridden with environment variables so that secrets are never
committed to the repository.
"""

import os

from cms.constants import Priority


def _sla_days_from_env() -> dict:
    """Read SLA days from CMS_SLA_DAYS, e.g. "Critical=1,High=3,Medium=5,Low=10"."""
    days = dict(Priority.DEFAULT_SLA_DAYS)
    for item in os.environ.get("CMS_SLA_DAYS", "").split(","):
        name, _, value = item.partition("=")
        if name.strip() in days and value.strip().isdigit():
            days[name.strip()] = int(value)
    return days


class Config:
    SECRET_KEY = os.environ.get("CMS_SECRET_KEY", "dev-only-change-me")
    # When this is None, create_app() stores the SQLite file in the instance/ folder.
    SQLALCHEMY_DATABASE_URI = os.environ.get("CMS_DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Security (CMS-2)
    CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    # Show the demo account hint on the login page (turn off outside development).
    SHOW_DEMO_LOGINS = os.environ.get("CMS_SHOW_DEMO_LOGINS", "1") == "1"

    # SLA days per priority used to set due dates (CMS-13).
    SLA_DAYS = _sla_days_from_env()


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # Tests post forms directly; one test switches this back on to check CSRF.
    CSRF_ENABLED = False
