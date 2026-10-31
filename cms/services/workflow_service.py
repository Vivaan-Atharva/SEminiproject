"""The status-flow engine (CMS-5).

This is the only code that changes the status of a change request, so the
workflow cannot be bypassed. Routes and other services call ``transition``;
they never set ``cr.status`` themselves.

The allowed moves live in one place, the ``TRANSITIONS`` table below. It
mirrors the state machine in docs/UML.md (docs/diagrams/state.mmd).

Typical use::

    try:
        workflow_service.transition(cr, Status.REJECTED, current_user, reason=reason)
    except workflow_service.WorkflowError as error:
        flash(str(error), "danger")        # every error message is meant for users

A failed ``transition`` changes nothing: all checks run before any field is
touched, and the status, the history row and the optional fields are saved in
one commit.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from cms.constants import Role, Status
from cms.extensions import db
from cms.models import StatusHistory

# --- errors ---------------------------------------------------------------


class WorkflowError(Exception):
    """Base class. ``str(error)`` is a friendly message that can be flashed."""


class TransitionNotAllowed(WorkflowError):
    """The move is not in the table (for example Submitted -> Closed)."""


class PermissionDenied(WorkflowError):
    """Wrong role, not the assignee, or not the requester."""


class MissingInput(WorkflowError):
    """A reason, a resolution summary or an assignee is required but missing."""


# --- the transition table -------------------------------------------------

# Who may make a move.
REVIEWER = "reviewer"    # a user whose role is Reviewer
ASSIGNEE = "assignee"    # the user the change request is assigned to
REQUESTER = "requester"  # the user who submitted the change request

# What a move needs besides the right person.
NEEDS_REASON = "reason"
NEEDS_SUMMARY = "resolution_summary"
NEEDS_ASSIGNEE = "assignee_set"  # cr.assignee must already be set


@dataclass(frozen=True)
class Rule:
    """``who`` lists the people allowed to make the move; any one of them is enough.

    Admin may make every move in the table, so Admin is not listed.
    """

    who: tuple[str, ...]
    needs: tuple[str, ...] = ()


# (from_status, to_status) -> Rule. Keep this one table the single source of truth.
TRANSITIONS: dict[tuple[str, str], Rule] = {
    (Status.SUBMITTED, Status.UNDER_REVIEW): Rule((REVIEWER,)),
    (Status.UNDER_REVIEW, Status.APPROVED): Rule((REVIEWER,)),
    (Status.UNDER_REVIEW, Status.REJECTED): Rule((REVIEWER,), (NEEDS_REASON,)),
    # Hema's assign service sets cr.assignee first, then calls transition().
    (Status.APPROVED, Status.ASSIGNED): Rule((REVIEWER,), (NEEDS_ASSIGNEE,)),
    (Status.IN_PROGRESS, Status.ASSIGNED): Rule((REVIEWER,), (NEEDS_ASSIGNEE,)),
    (Status.ASSIGNED, Status.IN_PROGRESS): Rule((ASSIGNEE,)),
    (Status.IN_PROGRESS, Status.RESOLVED): Rule((ASSIGNEE,), (NEEDS_SUMMARY,)),
    (Status.RESOLVED, Status.CLOSED): Rule((REQUESTER, REVIEWER)),
    (Status.RESOLVED, Status.REOPENED): Rule((REQUESTER, REVIEWER), (NEEDS_REASON,)),
    (Status.REOPENED, Status.IN_PROGRESS): Rule((ASSIGNEE,)),
}

_WHO_TEXT = {
    REVIEWER: "a reviewer",
    ASSIGNEE: "the assigned engineer",
    REQUESTER: "the requester",
}

_MISSING_TEXT = {
    NEEDS_REASON: "A reason is required to move a change request to {to}.",
    NEEDS_SUMMARY: "A resolution summary is required to resolve a change request.",
    NEEDS_ASSIGNEE: "An engineer must be assigned before a change request can move to {to}.",
}


# --- helpers --------------------------------------------------------------


def _now():
    return datetime.now(timezone.utc)


def _clean(text) -> str:
    """Trim user input; None and whitespace-only input both become ''."""
    return "" if text is None else str(text).strip()


def _is_person(person, user) -> bool:
    return person is not None and person.id is not None and person.id == user.id


def _may_act(rule: Rule, cr, user) -> bool:
    """Is this user one of the people the rule allows? Admin always is."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.is_admin:
        return True
    for actor in rule.who:
        if actor == REVIEWER and user.has_role(Role.REVIEWER):
            return True
        if actor == ASSIGNEE and _is_person(cr.assignee, user):
            return True
        if actor == REQUESTER and _is_person(cr.requester, user):
            return True
    return False


# --- public API -----------------------------------------------------------


def allowed_next(cr, user) -> list[str]:
    """Statuses this user may move this change request to right now.

    Use it to decide which buttons to show. It checks the current status and
    who the user is, not the required input (a reason, a summary): those are
    supplied when the action is submitted, and ``transition`` checks them.
    """
    return [
        to_status
        for (from_status, to_status), rule in TRANSITIONS.items()
        if from_status == cr.status and _may_act(rule, cr, user)
    ]


def transition(cr, to_status, user, *, reason=None, resolution_summary=None) -> StatusHistory:
    """Move ``cr`` to ``to_status`` and record it in the status history.

    Checks, in this order: the move is in the table, the user may make it,
    the required input is present. Raises ``TransitionNotAllowed``,
    ``PermissionDenied`` or ``MissingInput`` and changes nothing if a check
    fails. On success the new status, the history row and any
    ``resolution_summary`` / ``closed_at`` are saved in a single commit.
    """
    from_status = cr.status

    rule = TRANSITIONS.get((from_status, to_status))
    if rule is None:
        raise TransitionNotAllowed(
            f"A change request cannot move from {from_status} to {to_status}."
        )

    if not _may_act(rule, cr, user):
        who = " or ".join(_WHO_TEXT[actor] for actor in rule.who)
        raise PermissionDenied(f"Only {who} can move this change request to {to_status}.")

    reason_text = _clean(reason)
    summary_text = _clean(resolution_summary)
    supplied = {
        NEEDS_REASON: bool(reason_text),
        NEEDS_SUMMARY: bool(summary_text),
        NEEDS_ASSIGNEE: cr.assignee is not None,
    }
    for need in rule.needs:
        if not supplied[need]:
            raise MissingInput(_MISSING_TEXT[need].format(to=to_status))

    try:
        cr.status = to_status
        if NEEDS_SUMMARY in rule.needs:
            cr.resolution_summary = summary_text
        if to_status == Status.CLOSED:
            cr.closed_at = _now()
        entry = StatusHistory(
            change_request=cr,
            from_status=from_status,
            to_status=to_status,
            reason=reason_text or None,
            user_id=user.id,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return entry


def record_initial_status(cr, user) -> StatusHistory:
    """Add the first history row (None -> Submitted) for a new change request.

    Does NOT commit: the caller (``change_request_service.create``) commits,
    so the request and its first history row are saved together.
    """
    entry = StatusHistory(
        change_request=cr,
        from_status=None,
        to_status=Status.SUBMITTED,
        user_id=user.id,
    )
    db.session.add(entry)
    return entry
