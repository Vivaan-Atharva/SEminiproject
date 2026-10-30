"""Data for the home dashboard (CMS-12).

What each role sees:

- Requester: counts and lists for their own change requests only
- Engineer: everything, plus the requests assigned to them
- Reviewer / Admin: everything, plus requests waiting for review or assignment

Overdue = has a due date before today and is not Resolved, Closed or Rejected.
Due dates are set by CMS-13; requests without a due date are never overdue.
"""

from datetime import date

from cms.constants import Priority, Role, Status
from cms.models import ChangeRequest

LIST_LIMIT = 10


def visible_change_requests(user):
    """Base query of the change requests this user may see on the dashboard."""
    query = ChangeRequest.query
    if user.role == Role.REQUESTER:
        query = query.filter(ChangeRequest.requester_id == user.id)
    return query


def status_counts(user) -> dict:
    query = visible_change_requests(user)
    return {status: query.filter(ChangeRequest.status == status).count() for status in Status.ALL}


def open_priority_counts(user) -> dict:
    """Counts by priority for requests that are not Rejected or Closed."""
    query = visible_change_requests(user).filter(ChangeRequest.status.not_in(Status.TERMINAL))
    return {priority: query.filter(ChangeRequest.priority == priority).count() for priority in Priority.ALL}


def overdue(user, today: date | None = None):
    today = today or date.today()
    return (
        visible_change_requests(user)
        .filter(
            ChangeRequest.due_date.is_not(None),
            ChangeRequest.due_date < today,
            ChangeRequest.status.not_in(Status.NOT_DUE),
        )
        .order_by(ChangeRequest.due_date, ChangeRequest.id)
        .all()
    )


def assigned_to(user):
    return (
        ChangeRequest.query.filter(
            ChangeRequest.assignee_id == user.id,
            ChangeRequest.status.in_(Status.ENGINEER_WORK),
        )
        .order_by(ChangeRequest.updated_at.desc(), ChangeRequest.id.desc())
        .limit(LIST_LIMIT)
        .all()
    )


def requested_by(user):
    return (
        ChangeRequest.query.filter(
            ChangeRequest.requester_id == user.id,
            ChangeRequest.status.not_in(Status.TERMINAL),
        )
        .order_by(ChangeRequest.updated_at.desc(), ChangeRequest.id.desc())
        .limit(LIST_LIMIT)
        .all()
    )


def awaiting_review():
    return (
        ChangeRequest.query.filter(ChangeRequest.status.in_(Status.AWAITING_REVIEW))
        .order_by(ChangeRequest.created_at, ChangeRequest.id)
        .limit(LIST_LIMIT)
        .all()
    )


def awaiting_assignment():
    return (
        ChangeRequest.query.filter(
            ChangeRequest.status == Status.APPROVED,
            ChangeRequest.assignee_id.is_(None),
        )
        .order_by(ChangeRequest.created_at, ChangeRequest.id)
        .limit(LIST_LIMIT)
        .all()
    )


def build_dashboard(user, today: date | None = None) -> dict:
    """Everything the dashboard template needs, chosen by the user's role."""
    counts = status_counts(user)
    data = {
        "total": sum(counts.values()),
        "open_total": sum(n for s, n in counts.items() if s not in Status.TERMINAL),
        "status_counts": counts,
        "priority_counts": open_priority_counts(user),
        "overdue": overdue(user, today),
        "sections": [],
    }

    if user.role == Role.REQUESTER:
        data["sections"].append(("My open requests", requested_by(user), "my-requests"))
    if user.role == Role.ENGINEER:
        data["sections"].append(("Assigned to me", assigned_to(user), "assigned-to-me"))
    if user.role in (Role.REVIEWER, Role.ADMIN):
        data["sections"].append(("Waiting for review", awaiting_review(), "awaiting-review"))
        data["sections"].append(("Approved, waiting for an engineer", awaiting_assignment(), "awaiting-assignment"))

    return data
