"""Shared Flask extension objects, created once and initialised in create_app()."""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
