"""Add a comment or work note to a change request (CMS-10)."""

from flask import Blueprint, abort, flash, redirect, request, url_for
from flask_login import current_user, login_required

from cms.services import comment_service
from cms.services.change_request_service import get_by_id_or_404

bp = Blueprint("comments", __name__, url_prefix="/change-requests")


@bp.app_context_processor
def _template_helpers():
    """Lets the history and comment partials build the timeline and the form."""
    return {
        "timeline": comment_service.timeline,
        "can_write_work_note": comment_service.can_write_work_note,
        "COMMENT_MAX_LENGTH": comment_service.MAX_LENGTH,
    }


@bp.route("/<int:cr_id>/comments", methods=["POST"])
@login_required
def add(cr_id):
    cr = get_by_id_or_404(cr_id, current_user)  # a requester can only reach their own CRs
    try:
        comment = comment_service.add_comment(
            cr,
            current_user,
            request.form.get("body"),
            is_work_note=request.form.get("is_work_note") == "on",
        )
    except comment_service.CommentPermissionDenied:
        abort(403)
    except comment_service.CommentError as error:
        flash(str(error), "danger")
    else:
        flash("Work note added." if comment.is_work_note else "Comment added.", "success")
    return redirect(url_for("change_requests.detail", cr_id=cr.id))