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


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
