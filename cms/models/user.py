from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from cms.constants import Role
from cms.extensions import db


def _now():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    """A person who uses the system. UserMixin adds what Flask-Login needs."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=Role.REQUESTER)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)

    __table_args__ = (
        db.CheckConstraint(
            "role IN ('Requester', 'Reviewer', 'Engineer', 'Admin')",
            name="ck_user_role_valid",
        ),
    )

    def set_password(self, password: str) -> None:
        """Store a salted hash, never the plain password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self) -> bool:
        """Flask-Login refuses to sign in users for whom this is False."""
        return bool(self.active)

    def has_role(self, *roles: str) -> bool:
        return self.role in roles

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"
