"""Business rules for creating change requests (CMS-3)."""

from flask import abort
from sqlalchemy import case, func, or_

from cms.constants import COMPONENTS, CRType, Priority, Role, Status
from cms.extensions import db
from cms.models import ChangeRequest, format_cr_number
from cms.services import workflow_service
from cms.services.dashboard_service import visible_change_requests


class ValidationError(Exception):
    """Input errors keyed by the form field that needs attention."""

    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("Invalid change request data.")


def _value(data: dict, field: str) -> str:
    return str(data.get(field, "")).strip()


def validate(data: dict) -> dict[str, str]:
    """Return cleaned values or raise with all validation errors."""
    cleaned = {
        "title": _value(data, "title"),
        "description": _value(data, "description"),
        "cr_type": _value(data, "cr_type"),
        "priority": _value(data, "priority"),
        "component": _value(data, "component"),
    }
    errors = {}

    if not cleaned["title"]:
        errors["title"] = "Title is required."
    elif len(cleaned["title"]) > 200:
        errors["title"] = "Title must be 200 characters or fewer."
    if not cleaned["description"]:
        errors["description"] = "Description is required."
    if cleaned["cr_type"] not in CRType.ALL:
        errors["cr_type"] = "Choose a valid change request type."
    if cleaned["priority"] not in Priority.ALL:
        errors["priority"] = "Choose a valid priority."
    if cleaned["component"] not in COMPONENTS:
        errors["component"] = "Choose a valid component."

    if errors:
        raise ValidationError(errors)
    return cleaned


def create(data: dict, user) -> ChangeRequest:
    """Validate, persist and return a newly submitted change request."""
    values = validate(data)
    highest_id = db.session.query(func.max(ChangeRequest.id)).scalar() or 0
    change_request = ChangeRequest(
        cr_number=format_cr_number(highest_id + 1),
        status=Status.SUBMITTED,
        requester=user,
        **values,
    )
    db.session.add(change_request)
    workflow_service.record_initial_status(change_request, user)
    db.session.commit()
    return change_request


def search(
    user,
    *,
    q=None,
    status=None,
    priority=None,
    assignee_id=None,
    requester_id=None,
    component=None,
    sort="newest",
):
    """Return change requests visible to *user*, with optional filters."""
    query = visible_change_requests(user)
    if q and str(q).strip():
        term = f"%{str(q).strip()}%"
        query = query.filter(or_(ChangeRequest.title.ilike(term), ChangeRequest.cr_number.ilike(term)))
    if status in Status.ALL:
        query = query.filter(ChangeRequest.status == status)
    if priority in Priority.ALL:
        query = query.filter(ChangeRequest.priority == priority)
    if component in COMPONENTS:
        query = query.filter(ChangeRequest.component == component)
    if assignee_id is not None:
        query = query.filter(ChangeRequest.assignee_id == assignee_id)
    if requester_id is not None:
        query = query.filter(ChangeRequest.requester_id == requester_id)

    if sort == "oldest":
        return query.order_by(ChangeRequest.created_at, ChangeRequest.id).all()
    if sort == "priority":
        priority_order = case(
            {Priority.CRITICAL: 0, Priority.HIGH: 1, Priority.MEDIUM: 2, Priority.LOW: 3},
            value=ChangeRequest.priority,
            else_=4,
        )
        return query.order_by(priority_order, ChangeRequest.created_at.desc(), ChangeRequest.id.desc()).all()
    return query.order_by(ChangeRequest.created_at.desc(), ChangeRequest.id.desc()).all()


def get_by_id_or_404(cr_id: int, user=None) -> ChangeRequest:
    """Return change request with *cr_id* or 404; abort 403 if user is a requester and not owner."""
    change_request = ChangeRequest.query.get_or_404(cr_id)
    if user is not None and user.role == Role.REQUESTER and change_request.requester_id != user.id:
        abort(403)
    return change_request
