"""Create change request pages (CMS-3)."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.routing import BuildError

from cms.constants import COMPONENTS, CRType, Priority
from cms.services.change_request_service import ValidationError, create

bp = Blueprint("change_requests", __name__, url_prefix="/change-requests")


def _new_form(**context):
    return render_template(
        "change_requests/new.html",
        cr_types=CRType.ALL,
        priorities=Priority.ALL,
        components=COMPONENTS,
        data=context.pop("data", {}),
        errors=context.pop("errors", {}),
        **context,
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "GET":
        return _new_form()

    data = request.form.to_dict()
    try:
        change_request = create(data, current_user)
    except ValidationError as error:
        return _new_form(data=data, errors=error.errors), 400

    flash(f"{change_request.cr_number} was created and submitted for review.", "success")
    try:
        return redirect(url_for("change_requests.detail", cr_id=change_request.id))
    except BuildError:
        # CMS-4 owns the detail and list endpoints. Until it merges, the
        # dashboard is the available signed-in destination.
        return redirect(url_for("main.index"))
