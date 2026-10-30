"""Application settings.

Values can be overridden with environment variables so that secrets are never
committed to the repository.
"""

import os


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


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # Tests post forms directly; one test switches this back on to check CSRF.
    CSRF_ENABLED = False
