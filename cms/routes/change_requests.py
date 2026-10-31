"""Create change request pages (CMS-3)."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.routing import BuildError

from cms.constants import COMPONENTS, CRType, Priority, Status
from cms.models import ChangeRequest
from cms.services.change_request_service import ValidationError, create, get_by_id_or_404, search

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
    return redirect(url_for("change_requests.detail", cr_id=change_request.id))


def _optional_id(name):
    value = request.args.get(name)
    return int(value) if value and value.isdigit() else None


@bp.route("")
@bp.route("/")
@login_required
def list():
    filters = {
        "q": request.args.get("q", "").strip(),
        "status": request.args.get("status") or None,
        "priority": request.args.get("priority") or None,
        "component": request.args.get("component") or None,
        "sort": request.args.get("sort", "newest"),
    }
    items = search(
        current_user,
        **filters,
        assignee_id=_optional_id("assignee_id"),
        requester_id=_optional_id("requester_id"),
    )
    return render_template(
        "change_requests/list.html",
        items=items,
        filters=filters,
        statuses=Status.ALL,
        priorities=Priority.ALL,
        components=COMPONENTS,
    )


@bp.route("/<int:cr_id>")
@login_required
def detail(cr_id):
    change_request = get_by_id_or_404(cr_id, current_user)
    return render_template("change_requests/detail.html", cr=change_request)
