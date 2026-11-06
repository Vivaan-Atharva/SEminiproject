"""In-app notifications (CMS-14).

Two kinds of functions live here:

* Event hooks - ``submitted``, ``assigned``, ``status_changed`` and
  ``comment_added``. They only ADD rows to the session and never commit, so
  the notification is saved in the same commit as the change that caused it.
  If that change fails and is rolled back, no notification is left behind.
* Read helpers for the pages - ``unread_count``, ``for_user``, ``open`` and
  ``mark_all_read``.

Nobody is ever notified about their own action.

For CMS-10 (comments): after adding the Comment to the session, call
``notification_service.comment_added(cr, author)`` and then commit once.
"""

from flask import abort

from cms.constants import Role, Status
from cms.extensions import db
from cms.models import Notification, User


# --- event hooks (add to the session, do not commit) -------------------------


def _notify(people, cr, kind, message, actor) -> list[Notification]:
    """Add one notification per distinct person, skipping the actor and missing people."""
    created, seen = [], set()
    for person in people:
        if person is None or person.id is None or person.id in seen:
            continue
        seen.add(person.id)
        if actor is not None and person.id == actor.id:
            continue
        note = Notification(user=person, change_request=cr, kind=kind, message=message[:300])
        db.session.add(note)
        created.append(note)
    return created


def _label(cr) -> str:
    return f"{cr.cr_number} “{cr.title}”"


def submitted(cr, actor) -> list[Notification]:
    """A new change request is waiting for review: tell every active reviewer."""
    with db.session.no_autoflush:  # the new request is saved by the caller's commit
        reviewers = User.query.filter(User.role == Role.REVIEWER, User.active.is_(True)).all()
    return _notify(reviewers, cr, Notification.NEW, f"{_label(cr)} was submitted and is waiting for review.", actor)


def assigned(cr, engineer, actor, previous=None) -> list[Notification]:
    """Tell the new engineer, the previous engineer (on reassignment) and the requester."""
    notes = _notify([engineer], cr, Notification.ASSIGNED, f"{_label(cr)} was assigned to you by {actor.name}.", actor)
    if previous is not None and previous.id != engineer.id:
        notes += _notify(
            [previous], cr, Notification.ASSIGNED, f"{_label(cr)} was reassigned to {engineer.name}.", actor
        )
    notes += _notify(
        [cr.requester], cr, Notification.ASSIGNED, f"{_label(cr)} was assigned to {engineer.name}.", actor
    )
    return notes


def status_changed(cr, from_status, to_status, actor, reason=None) -> list[Notification]:
    """Tell the requester and the assignee that the status changed.

    Moves to Assigned are announced by ``assigned`` instead, which knows who
    the new engineer is.
    """
    if to_status == Status.ASSIGNED:
        return []
    message = f"{_label(cr)} moved from {from_status} to {to_status} ({actor.name})."
    if reason:
        message = f"{message[:-1]}: {reason}"
    return _notify([cr.requester, cr.assignee], cr, Notification.STATUS, message, actor)


def comment_added(cr, author) -> list[Notification]:
    """Tell the requester and the assignee that someone commented (used by CMS-10)."""
    return _notify(
        [cr.requester, cr.assignee], cr, Notification.COMMENT, f"{author.name} commented on {_label(cr)}.", author
    )


# --- read helpers for the pages ---------------------------------------------


def unread_count(user) -> int:
    if user is None or not getattr(user, "is_authenticated", False):
        return 0
    return Notification.query.filter_by(user_id=user.id, read=False).count()


def for_user(user, limit=50) -> list[Notification]:
    """The user's notifications, unread first, then newest first."""
    return (
        Notification.query.filter_by(user_id=user.id)
        .order_by(Notification.read, Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .all()
    )


def open(notification_id, user) -> Notification:
    """Mark one of the user's notifications as read. Someone else's gives 404."""
    note = db.session.get(Notification, notification_id)
    if note is None or note.user_id != user.id:
        abort(404)
    if not note.read:
        note.read = True
        db.session.commit()
    return note


def mark_all_read(user) -> int:
    count = Notification.query.filter_by(user_id=user.id, read=False).update({"read": True})
    db.session.commit()
    return count
