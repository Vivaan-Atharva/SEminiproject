from flask import Blueprint, jsonify, render_template
from flask_login import login_required

from cms.constants import Status
from cms.models import ChangeRequest, User

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def index():
    counts = {status: ChangeRequest.query.filter_by(status=status).count() for status in Status.ALL}
    return render_template(
        "index.html",
        user_count=User.query.count(),
        cr_count=ChangeRequest.query.count(),
        counts=counts,
    )


@bp.route("/health")
def health():
    """Simple check used by tests and CI to confirm the app starts."""
    return jsonify(status="ok")
