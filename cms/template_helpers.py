"""Small helpers available in every template."""

from flask import url_for
from werkzeug.routing import BuildError

# CMS-4 should register the change request detail page as:
#   Blueprint name "change_requests", view "detail", URL parameter cr_id
#   e.g. @bp.route("/change-requests/<int:cr_id>") def detail(cr_id): ...
CR_DETAIL_ENDPOINT = "change_requests.detail"


def cr_url(change_request):
    """Link to a change request's detail page, or None until that page exists."""
    try:
        return url_for(CR_DETAIL_ENDPOINT, cr_id=change_request.id)
    except BuildError:
        return None


def init_template_helpers(app) -> None:
    app.jinja_env.globals["cr_url"] = cr_url
