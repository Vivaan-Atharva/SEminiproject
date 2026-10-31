"""Assign and reassign change requests (CMS-7).

All the rules live here so they can be unit-tested. The status change itself
(Approved -> Assigned, In Progress -> Assigned) is done by the status engine,
``workflow_service.transition``; this module never sets ``cr.status``.

Typical use::

    try:
        assignment_service.assign(cr, engineer, current_user)
    except assignment_service.AssignmentError as error:
        flash(str(error), "danger")     # every error message is meant for users
"""

from cms.constants import Role, Status
from cms.extensions import db
from cms.models import AssignmentHistory, User
from cms.services import workflow_service

# Statuses in which a change request can be assigned or reassigned.
ASSIGNABLE_STATUSES = [Status.APPROVED, Status.ASSIGNED, Status.IN_PROGRESS]


class AssignmentError(Exception):
    """Base class. ``str(error)`` is a friendly message that can be flashed."""


class AssignmentPermissionDenied(AssignmentError):
    """Only a Reviewer or an Admin may assign."""


def assignable_engineers() -> list[User]:
    """Active users with the Engineer role, sorted by name (for the dropdown)."""
    return (
        User.query.filter(User.role == Role.ENGINEER, User.active.is_(True))
        .order_by(User.name, User.id)
        .all()
    )


def can_assign(user) -> bool:
    return bool(
        user is not None
        and getattr(user, "is_authenticated", False)
        and (user.is_admin or user.has_role(Role.REVIEWER))
    )


def assign(cr, engineer, by_user) -> AssignmentHistory:
    """Assign ``cr`` to ``engineer`` (or reassign it) and record it in the history.

    Raises ``AssignmentPermissionDenied`` or ``AssignmentError`` and changes
    nothing if a check fails.

    - Approved -> Assigned and In Progress -> Assigned go through the status
      engine, which commits the new assignee, the assignment row and the
      status history together in one transaction.
    - Reassigning while already Assigned only changes the assignee.
    """
    if not can_assign(by_user):
        raise AssignmentPermissionDenied("Only a reviewer or an admin can assign a change request.")

    if engineer is None or engineer.role != Role.ENGINEER:
        raise AssignmentError("A change request can only be assigned to an engineer.")
    if not engineer.active:
        raise AssignmentError(f"{engineer.name} is inactive and cannot be assigned work.")

    if cr.status not in ASSIGNABLE_STATUSES:
        raise AssignmentError(
            f"A change request that is {cr.status} cannot be assigned. "
            "Only Approved, Assigned or In Progress requests can be assigned."
        )
    if cr.assignee_id == engineer.id:
        raise AssignmentError(f"This change request is already assigned to {engineer.name}.")

    entry = AssignmentHistory(
        change_request=cr,
        from_user_id=cr.assignee_id,
        to_user_id=engineer.id,
        assigned_by_id=by_user.id,
    )
    previous_status = cr.status
    try:
        cr.assignee = engineer
        db.session.add(entry)
        if previous_status == Status.ASSIGNED:
            # Same status, new person: not a status transition, so commit here.
            db.session.commit()
        else:
            # Commits everything above together with the new status.
            workflow_service.transition(cr, Status.ASSIGNED, by_user)
    except Exception:
        db.session.rollback()
        raise
    return entry