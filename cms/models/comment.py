from datetime import datetime, timezone

from cms.extensions import db


def _now():
    return datetime.now(timezone.utc)


class Comment(db.Model):
    """A comment or work note on a change request (CMS-10).

    Rows are only written by ``cms.services.comment_service``. The text is
    stored as typed and is always escaped when shown, never marked as safe.
    """

    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    change_request_id = db.Column(
        db.Integer, db.ForeignKey("change_requests.id"), nullable=False, index=True
    )
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    is_work_note = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)

    # cr.comments is a list, oldest comment first.
    change_request = db.relationship(
        "ChangeRequest",
        backref=db.backref("comments", order_by=lambda: [Comment.created_at, Comment.id]),
    )
    author = db.relationship("User")

    def __repr__(self) -> str:
        return f"<Comment cr={self.change_request_id} by={self.author_id}>"