"""Workflow action routes: the buttons on a change request's detail page.

CMS-6: a reviewer starts a review, approves or rejects a change request.
CMS-8: an engineer starts work on a change request and resolves it.
CMS-9: the requester (or a reviewer) closes a resolved change request, or reopens it.

Every route only asks the status engine to make the move; all the rules
(who may do it, which input is needed) live in ``workflow_service``.
"""

from flask import Blueprint, abort, flash, redirect, request, url_for
from flask_login import current_user, login_required

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


# --- reviewer actions (CMS-6) -----------------------------------------------


@bp.route("/<int:cr_id>/start-review", methods=["POST"])
@roles_required(Role.REVIEWER)
def start_review(cr_id):
    """Submitted -> Under Review."""
    return _perform(cr_id, Status.UNDER_REVIEW, "{cr} is now under review.")


@bp.route("/<int:cr_id>/approve", methods=["POST"])
@roles_required(Role.REVIEWER)
def approve(cr_id):
    """Under Review -> Approved."""
    return _perform(cr_id, Status.APPROVED, "{cr} was approved.")


@bp.route("/<int:cr_id>/reject", methods=["POST"])
@roles_required(Role.REVIEWER)
def reject(cr_id):
    """Under Review -> Rejected. A reason is required and is kept in the history."""
    return _perform(
        cr_id,
        Status.REJECTED,
        "{cr} was rejected.",
        reason=request.form.get("reason"),
    )


# --- engineer actions (CMS-8) -----------------------------------------------


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


# --- requester actions (CMS-9) ----------------------------------------------


@bp.route("/<int:cr_id>/close", methods=["POST"])
@login_required
def close(cr_id):
    """Resolved -> Closed (the requester or a reviewer; the engine checks who)."""
    return _perform(cr_id, Status.CLOSED, "{cr} is now closed.")


@bp.route("/<int:cr_id>/reopen", methods=["POST"])
@login_required
def reopen(cr_id):
    """Resolved -> Reopened. A reason is required and is kept in the history."""
    return _perform(
        cr_id,
        Status.REOPENED,
        "{cr} was reopened. The assigned engineer can resume work.",
        reason=request.form.get("reason"),
    )