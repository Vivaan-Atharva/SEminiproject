"""Sign-in rules (CMS-2)."""

from urllib.parse import urlsplit

from cms.models import User


def authenticate(email: str, password: str):
    """Return the user if the email and password match an active account, else None.

    The caller shows the same message for every failure so that nobody can
    find out which emails have accounts.
    """
    email = (email or "").strip().lower()
    if not email or not password:
        return None

    user = User.query.filter_by(email=email).first()
    if user is None or not user.active:
        return None
    if not user.check_password(password):
        return None
    return user


def is_safe_redirect(target: str | None) -> bool:
    """Only allow redirects to pages on this site, never to another website."""
    if not target:
        return False
    parts = urlsplit(target)
    return (
        not parts.scheme
        and not parts.netloc
        and target.startswith("/")
        and not target.startswith("//")
        and "\\" not in target
    )
