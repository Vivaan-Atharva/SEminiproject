"""Assign / reassign a change request (CMS-7)."""

from flask import Blueprint, flash, redirect, request, url_for
from flask_login import current_user

from cms.constants import Role
from cms.decorators import roles_required
from cms.extensions import db
from cms.models import User
from cms.services import assignment_service
from cms.services.change_request_service import get_by_id_or_404
from cms.services.workflow_service import WorkflowError

bp = Blueprint("assignment", __name__, url_prefix="/change-requests")


@bp.app_context_processor
def _template_helpers():
    """Lets _actions.html fill the Assign dropdown without touching other routes."""
    return {
        "assignable_engineers": assignment_service.assignable_engineers,
        "can_assign": assignment_service.can_assign,
        "ASSIGNABLE_STATUSES": assignment_service.ASSIGNABLE_STATUSES,
    }


@bp.route("/<int:cr_id>/assign", methods=["POST"])
@roles_required(Role.REVIEWER)
def assign(cr_id):
    cr = get_by_id_or_404(cr_id, current_user)
    raw_id = request.form.get("assignee_id", "")
    engineer = _user_from_form(raw_id)

    try:
        if engineer is None:
            raise assignment_service.AssignmentError("Choose an engineer to assign this change request to.")
        assignment_service.assign(cr, engineer, current_user)
    except (assignment_service.AssignmentError, WorkflowError) as error:
        flash(str(error), "danger")
    else:
        flash(f"{cr.cr_number} is now assigned to {engineer.name}.", "success")
    return redirect(url_for("change_requests.detail", cr_id=cr.id))


def _user_from_form(raw_id):
    """The user with this id from the form, or None if it is missing or not a number."""
    raw_id = (raw_id or "").strip()
    return db.session.get(User, int(raw_id)) if raw_id.isdigit() else None