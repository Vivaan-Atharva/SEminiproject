from datetime import datetime, timezone

from cms.constants import Status
from cms.extensions import db


def _now():
    return datetime.now(timezone.utc)


def format_cr_number(sequence: int) -> str:
    """Turn 7 into 'CR-0007'."""
    return f"CR-{sequence:04d}"


class ChangeRequest(db.Model):
    """A request for a change, tracked from submission to closure.

    The skeleton only defines the shared table. Creating (CMS-3), listing
    (CMS-4), status changes (CMS-5) and assignment (CMS-7) are built on top
    of it in their own stories.
    """

    __tablename__ = "change_requests"

    id = db.Column(db.Integer, primary_key=True)
    cr_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    cr_type = db.Column(db.String(40), nullable=False)
    priority = db.Column(db.String(20), nullable=False)
    component = db.Column(db.String(60), nullable=False)
    status = db.Column(db.String(20), nullable=False, default=Status.SUBMITTED, index=True)

    requester_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    assignee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    due_date = db.Column(db.Date, nullable=True)  # set by CMS-13
    resolution_summary = db.Column(db.Text, nullable=True)  # set by CMS-8

    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)
    closed_at = db.Column(db.DateTime, nullable=True)

    requester = db.relationship("User", foreign_keys=[requester_id], backref="requested_changes")
    assignee = db.relationship("User", foreign_keys=[assignee_id], backref="assigned_changes")

    __table_args__ = (
        db.CheckConstraint("length(trim(title)) > 0", name="ck_cr_title_not_blank"),
        db.CheckConstraint("length(trim(description)) > 0", name="ck_cr_description_not_blank"),
    )

    @property
    def is_open(self) -> bool:
        return self.status not in Status.TERMINAL

    def __repr__(self) -> str:
        return f"<ChangeRequest {self.cr_number} {self.status}>"
