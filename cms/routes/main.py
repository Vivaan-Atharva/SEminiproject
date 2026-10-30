from flask import Blueprint, jsonify, render_template
from flask_login import current_user, login_required

from cms.services.dashboard_service import build_dashboard

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def index():
    """Home dashboard (CMS-12)."""
    return render_template("dashboard.html", dash=build_dashboard(current_user))


@bp.route("/health")
def health():
    """Simple check used by tests and CI to confirm the app starts."""
    return jsonify(status="ok")
