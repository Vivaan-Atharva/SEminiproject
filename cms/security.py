"""Protection against cross-site request forgery (CSRF).

Every form that uses method="post" must include this hidden field:

    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

Requests that change data without the right token are rejected with 400.
Tests turn the check off through TestConfig.CSRF_ENABLED = False.
"""

import hmac
import secrets

from flask import abort, request, session

_SESSION_KEY = "_csrf_token"
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def generate_csrf_token() -> str:
    if _SESSION_KEY not in session:
        session[_SESSION_KEY] = secrets.token_hex(32)
    return session[_SESSION_KEY]


def init_csrf(app) -> None:
    app.jinja_env.globals["csrf_token"] = generate_csrf_token

    @app.before_request
    def check_csrf_token():
        if not app.config.get("CSRF_ENABLED", True):
            return None
        if request.method not in _UNSAFE_METHODS:
            return None
        expected = session.get(_SESSION_KEY)
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not expected or not sent or not hmac.compare_digest(expected, sent):
            abort(400)
        return None
