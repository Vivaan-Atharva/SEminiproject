from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from cms.constants import Role
from cms.extensions import db


def _now():
    return datetime.now(timezone.utc)


class User(db.Model):
    """A person who uses the system. Login itself is added in CMS-2."""

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

    def has_role(self, *roles: str) -> bool:
        return self.role in roles

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"
