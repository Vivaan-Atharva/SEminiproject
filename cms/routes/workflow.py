"""Workflow action routes: the buttons on a change request's detail page.

CMS-8 (this file): an engineer starts work on a change request and resolves it.
CMS-6 adds the reviewer actions (start review, approve, reject) to this same
blueprint.

Every route only asks the status engine to make the move; all the rules
(who may do it, which input is needed) live in ``workflow_service``.
"""

from flask import Blueprint, abort, flash, redirect, request, url_for
from flask_login import current_user

from cms.constants import Role, Status
from cms.decorators import roles_required
from cms.services import workflow_service
from cms.services.change_request_service import get_by_id_or_404

bp = Blueprint("workflow", __name__, url_prefix="/change-requests")


@bp.app_context_processor
def _template_helpers():
    """Lets _actions.html show only the buttons the status engine allows."""
    return {"allowed_next": workflow_service.allowed_next, "Status": Status}


def _perform(cr_id, to_status, success_message, **inputs):
    """Ask the status engine for one move, then go back to the detail page.

    - wrong person or role (``PermissionDenied``) -> 403
    - any other ``WorkflowError`` (move not allowed, input missing) -> the
      message is flashed and nothing changes
    """
    cr = get_by_id_or_404(cr_id, current_user)
    try:
        workflow_service.transition(cr, to_status, current_user, **inputs)
    except workflow_service.PermissionDenied:
        abort(403)
    except workflow_service.WorkflowError as error:
        flash(str(error), "danger")
    else:
        flash(success_message.format(cr=cr.cr_number), "success")
    return redirect(url_for("change_requests.detail", cr_id=cr.id))


@bp.route("/<int:cr_id>/start-work", methods=["POST"])
@roles_required(Role.ENGINEER)
def start_work(cr_id):
    """Assigned -> In Progress, or Reopened -> In Progress (the assignee only)."""
    return _perform(cr_id, Status.IN_PROGRESS, "You started work on {cr}.")


@bp.route("/<int:cr_id>/resolve", methods=["POST"])
@roles_required(Role.ENGINEER)
def resolve(cr_id):
    """In Progress -> Resolved, with a summary of what was done (the assignee only)."""
    return _perform(
        cr_id,
        Status.RESOLVED,
        "{cr} was resolved.",
        resolution_summary=request.form.get("resolution_summary"),
    )
