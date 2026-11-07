"""Notification pages (CMS-14): the list, opening one, and marking all as read."""

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from cms.services import notification_service

bp = Blueprint("notifications", __name__, url_prefix="/notifications")


@bp.app_context_processor
def _unread_count():
    """Unread count for the bell in the navigation bar on every page."""
    return {"unread_notifications": lambda: notification_service.unread_count(current_user)}


@bp.route("")
@bp.route("/")
@login_required
def index():
    return render_template(
        "notifications/list.html", notifications=notification_service.for_user(current_user)
    )


@bp.route("/<int:notification_id>/open", methods=["POST"])
@login_required
def open(notification_id):
    note = notification_service.open(notification_id, current_user)
    return redirect(url_for("change_requests.detail", cr_id=note.change_request_id))


@bp.route("/read-all", methods=["POST"])
@login_required
def read_all():
    count = notification_service.mark_all_read(current_user)
    flash(f"Marked {count} notification{'s' if count != 1 else ''} as read.", "success")
    return redirect(url_for("notifications.index"))
