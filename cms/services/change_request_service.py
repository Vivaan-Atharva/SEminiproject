"""Business rules for creating change requests (CMS-3)."""

from sqlalchemy import func

from cms.constants import COMPONENTS, CRType, Priority, Status
from cms.extensions import db
from cms.models import ChangeRequest, format_cr_number
from cms.services import workflow_service


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
