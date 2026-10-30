"""Shared Flask extension objects, created once and initialised in create_app()."""

from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please sign in to continue."
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id: str):
    from cms.models import User

    user = db.session.get(User, int(user_id))
    # A deactivated user is signed out on their next request.
    return user if user is not None and user.active else None
