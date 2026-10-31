from datetime import datetime, timezone

from cms.extensions import db


def _now():
    return datetime.now(timezone.utc)


class StatusHistory(db.Model):
    """One row for every status a change request has entered (CMS-5).

    The first row of a request has no ``from_status`` (None -> Submitted).
    Rows are only written by ``cms.services.workflow_service``, so the history
    always matches what the status engine actually did.
    """

    __tablename__ = "status_history"

    id = db.Column(db.Integer, primary_key=True)
    change_request_id = db.Column(
        db.Integer, db.ForeignKey("change_requests.id"), nullable=False, index=True
    )
    from_status = db.Column(db.String(20), nullable=True)
    to_status = db.Column(db.String(20), nullable=False)
    reason = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)

    # cr.status_history is a list, oldest entry first.
    change_request = db.relationship(
        "ChangeRequest",
        backref=db.backref(
            "status_history",
            order_by=lambda: [StatusHistory.created_at, StatusHistory.id],
        ),
    )
    user = db.relationship("User")

    def __repr__(self) -> str:
        return f"<StatusHistory cr={self.change_request_id} {self.from_status} -> {self.to_status}>"
