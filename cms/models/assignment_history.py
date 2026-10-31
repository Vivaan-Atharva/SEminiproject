from datetime import datetime, timezone

from cms.extensions import db


def _now():
    return datetime.now(timezone.utc)


class AssignmentHistory(db.Model):
    """One row for every time a change request is assigned or reassigned (CMS-7).

    ``from_user_id`` is empty for the first assignment. Rows are only written
    by ``cms.services.assignment_service``.
    """

    __tablename__ = "assignment_history"

    id = db.Column(db.Integer, primary_key=True)
    change_request_id = db.Column(
        db.Integer, db.ForeignKey("change_requests.id"), nullable=False, index=True
    )
    from_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    to_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)

    # cr.assignment_history is a list, oldest entry first.
    change_request = db.relationship(
        "ChangeRequest",
        backref=db.backref(
            "assignment_history",
            order_by=lambda: [AssignmentHistory.created_at, AssignmentHistory.id],
        ),
    )
    from_user = db.relationship("User", foreign_keys=[from_user_id])
    to_user = db.relationship("User", foreign_keys=[to_user_id])
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_id])

    def __repr__(self) -> str:
        return (
            f"<AssignmentHistory cr={self.change_request_id} "
            f"{self.from_user_id} -> {self.to_user_id}>"
        )