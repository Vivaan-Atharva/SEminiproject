from datetime import datetime, timezone

from cms.extensions import db


def _now():
    return datetime.now(timezone.utc)


class Notification(db.Model):
    """An in-app message telling one user that something happened on a change request (CMS-14).

    Rows are only written by ``cms.services.notification_service``.
    """

    __tablename__ = "notifications"

    # What happened. Shown as a small label in the notification list.
    ASSIGNED = "Assigned"
    STATUS = "Status"
    COMMENT = "Comment"
    NEW = "New request"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    change_request_id = db.Column(db.Integer, db.ForeignKey("change_requests.id"), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    message = db.Column(db.String(300), nullable=False)
    read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)

    user = db.relationship("User")
    change_request = db.relationship("ChangeRequest")

    def __repr__(self) -> str:
        return f"<Notification user={self.user_id} cr={self.change_request_id} {self.kind}>"
