"""Comments, work notes and the activity timeline (CMS-10).

Typical use::

    try:
        comment_service.add_comment(cr, current_user, request.form.get("body"))
    except comment_service.CommentPermissionDenied:
        abort(403)
    except comment_service.CommentError as error:
        flash(str(error), "danger")      # every error message is meant for users

``add_comment`` saves the comment and the notifications it causes in one commit.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from cms.constants import Role
from cms.extensions import db
from cms.models import Comment
from cms.services import notification_service

MAX_LENGTH = 2000


class CommentError(Exception):
    """Base class. ``str(error)`` is a friendly message that can be flashed."""


class CommentPermissionDenied(CommentError):
    """The user may not comment here, or may not write a work note."""


def can_view(cr, user) -> bool:
    """A requester only sees their own change requests; everyone else sees all."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.role == Role.REQUESTER:
        return cr.requester_id == user.id
    return True


def can_write_work_note(user) -> bool:
    return bool(
        user is not None
        and getattr(user, "is_authenticated", False)
        and (user.is_admin or user.has_role(Role.ENGINEER, Role.REVIEWER))
    )


def add_comment(cr, user, body, is_work_note=False) -> Comment:
    """Add a comment (or a work note) to ``cr`` and notify the people involved."""
    if not can_view(cr, user):
        raise CommentPermissionDenied("You cannot comment on this change request.")
    if is_work_note and not can_write_work_note(user):
        raise CommentPermissionDenied("Only engineers, reviewers and admins can add work notes.")

    text = (body or "").strip()
    if not text:
        raise CommentError("A comment cannot be empty.")
    if len(text) > MAX_LENGTH:
        raise CommentError(f"A comment can be at most {MAX_LENGTH} characters (this one has {len(text)}).")

    comment = Comment(change_request=cr, author=user, body=text, is_work_note=bool(is_work_note))
    try:
        db.session.add(comment)
        notification_service.comment_added(cr, user)  # adds rows only; saved by the commit below
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return comment


# --- the activity timeline ---------------------------------------------------


@dataclass
class TimelineItem:
    when: datetime
    who: str
    kind: str  # "status", "assignment", "comment" or "work note"
    text: str
    # Only for kind == "status", so the page can show "From → To" and the reason.
    from_status: str | None = None
    to_status: str | None = None
    reason: str | None = None


def _naive_utc(moment: datetime) -> datetime:
    """SQLite gives naive times and new rows give aware ones; compare them on one scale."""
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


def timeline(cr) -> list[TimelineItem]:
    """Status changes, assignments and comments of ``cr`` in one list, oldest first."""
    items: list[TimelineItem] = []

    for entry in cr.status_history:
        if entry.from_status:
            text = f"{entry.from_status} → {entry.to_status}"
        else:
            text = f"Created as {entry.to_status}"
        items.append(
            TimelineItem(
                entry.created_at, entry.user.name, "status", text,
                from_status=entry.from_status, to_status=entry.to_status, reason=entry.reason,
            )
        )

    for entry in cr.assignment_history:
        if entry.from_user is None:
            text = f"Assigned to {entry.to_user.name}"
        else:
            text = f"Reassigned from {entry.from_user.name} to {entry.to_user.name}"
        items.append(TimelineItem(entry.created_at, entry.assigned_by.name, "assignment", text))

    for comment in cr.comments:
        kind = "work note" if comment.is_work_note else "comment"
        items.append(TimelineItem(comment.created_at, comment.author.name, kind, comment.body))

    items.sort(key=lambda item: _naive_utc(item.when))  # stable: equal times keep the order above
    return items