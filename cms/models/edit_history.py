from datetime import datetime, timezone

from cms.extensions import db


def _now():
    return datetime.now(timezone.utc)


class EditHistory(db.Model):
    """One row for every field changed through the edit page (CMS-11)."""

    __tablename__ = "edit_history"

    id = db.Column(db.Integer, primary_key=True)
    change_request_id = db.Column(
        db.Integer, db.ForeignKey("change_requests.id"), nullable=False, index=True
    )
    field = db.Column(db.String(40), nullable=False)
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)

    # cr.edit_history is a list, oldest entry first.
    change_request = db.relationship(
        "ChangeRequest",
        backref=db.backref(
            "edit_history",
            order_by=lambda: [EditHistory.created_at, EditHistory.id],
        ),
    )
    user = db.relationship("User")

    def __repr__(self) -> str:
        return f"<EditHistory cr={self.change_request_id} {self.field}>"
