"""Access-control decorators for routes (CMS-2).

Usage:

    from cms.constants import Role
    from cms.decorators import roles_required

    @bp.route("/change-requests/<int:cr_id>/approve", methods=["POST"])
    @roles_required(Role.REVIEWER)
    def approve(cr_id):
        ...

- Not signed in      -> redirected to the login page
- Signed in, no role -> 403 page
- Admin              -> always allowed

For pages any signed-in user may open, use flask_login.login_required instead.
Record-level checks (for example "only the assignee may resolve") belong in
the services, because the decorator only knows the user's role.
"""

from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def roles_required(*roles: str):
    if not roles:
        raise ValueError("roles_required() needs at least one role")

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not (current_user.is_admin or current_user.has_role(*roles)):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
