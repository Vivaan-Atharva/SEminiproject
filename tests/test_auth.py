"""CMS-2: sign in, sign out and role-based access."""

import re

import pytest
from flask_login import login_required

from cms.constants import Role
from cms.decorators import roles_required
from cms.models import User
from cms.services.auth_service import authenticate, is_safe_redirect


# ---------- sign in ----------

def test_login_page_loads(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"Sign in" in response.data


def test_valid_login_redirects_home_and_shows_user(seeded, client, login):
    response = login("reviewer@cms.local")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")

    home = client.get("/")
    assert home.status_code == 200
    assert b"Riya Reviewer" in home.data
    assert b"Reviewer" in home.data


def test_email_is_case_insensitive(seeded, login):
    assert login("  Reviewer@CMS.local ").status_code == 302


@pytest.mark.parametrize(
    "email, password",
    [
        ("reviewer@cms.local", "wrong-password"),
        ("nobody@cms.local", "demo1234"),
        ("", "demo1234"),
        ("reviewer@cms.local", ""),
    ],
)
def test_invalid_login_is_rejected_with_same_message(seeded, client, login, email, password):
    response = login(email, password)
    assert response.status_code == 401
    assert b"Invalid email or password." in response.data
    # Still not signed in.
    assert client.get("/").status_code == 302


def test_inactive_user_cannot_sign_in(seeded, client, login):
    response = login("engineer3@cms.local")
    assert response.status_code == 401
    assert client.get("/").status_code == 302


def test_signed_in_user_visiting_login_goes_home(seeded, client, login):
    login("requester@cms.local")
    response = client.get("/login")
    assert response.status_code == 302


# ---------- sign out ----------

def test_logout_signs_the_user_out(seeded, client, login, logout):
    login("requester@cms.local")
    assert client.get("/").status_code == 200

    response = logout()
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert client.get("/").status_code == 302


def test_logout_requires_post(seeded, client, login):
    login("requester@cms.local")
    assert client.get("/logout").status_code == 405


def test_user_deactivated_while_signed_in_is_signed_out(seeded, client, login):
    login("engineer1@cms.local")
    assert client.get("/").status_code == 200

    user = User.query.filter_by(email="engineer1@cms.local").one()
    user.active = False
    from cms.extensions import db

    db.session.commit()
    assert client.get("/").status_code == 302


# ---------- protected pages and redirects ----------

def test_anonymous_user_is_sent_to_login_with_next(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert "next=" in response.headers["Location"]


def test_login_returns_to_next_page(seeded, client):
    response = client.post(
        "/login?next=/health",
        data={"email": "requester@cms.local", "password": "demo1234"},
    )
    assert response.headers["Location"].endswith("/health")


def test_login_ignores_next_pointing_to_another_site(seeded, client):
    response = client.post(
        "/login?next=https://evil.example.com/",
        data={"email": "requester@cms.local", "password": "demo1234"},
    )
    assert "evil.example.com" not in response.headers["Location"]


@pytest.mark.parametrize(
    "target, safe",
    [
        ("/change-requests/3", True),
        ("/", True),
        ("https://evil.example.com", False),
        ("//evil.example.com", False),
        ("/\\evil.example.com", False),
        ("javascript:alert(1)", False),
        ("", False),
        (None, False),
    ],
)
def test_is_safe_redirect(target, safe):
    assert is_safe_redirect(target) is safe


def test_authenticate_service(seeded):
    assert authenticate("admin@cms.local", "demo1234").role == Role.ADMIN
    assert authenticate("admin@cms.local", "nope") is None
    assert authenticate("engineer3@cms.local", "demo1234") is None


# ---------- role checks ----------

@pytest.fixture
def role_pages(app):
    """Test-only pages protected by the decorators, as other stories will use them."""

    @roles_required(Role.REVIEWER)
    def reviewer_only():
        return "reviewer page"

    @roles_required(Role.ENGINEER, Role.REVIEWER)
    def engineer_or_reviewer():
        return "engineer or reviewer page"

    @login_required
    def any_signed_in_user():
        return "any user page"

    app.add_url_rule("/_test/reviewer-only", view_func=reviewer_only)
    app.add_url_rule("/_test/engineer-or-reviewer", view_func=engineer_or_reviewer)
    app.add_url_rule("/_test/any-user", view_func=any_signed_in_user)
    return app


def test_correct_role_can_open_page(role_pages, seeded, client, login):
    login("reviewer@cms.local")
    assert client.get("/_test/reviewer-only").status_code == 200
    assert client.get("/_test/engineer-or-reviewer").status_code == 200


def test_wrong_role_gets_403(role_pages, seeded, client, login):
    login("requester@cms.local")
    response = client.get("/_test/reviewer-only")
    assert response.status_code == 403
    assert b"403" in response.data
    assert client.get("/_test/engineer-or-reviewer").status_code == 403
    assert client.get("/_test/any-user").status_code == 200


def test_engineer_allowed_only_where_listed(role_pages, seeded, client, login):
    login("engineer1@cms.local")
    assert client.get("/_test/engineer-or-reviewer").status_code == 200
    assert client.get("/_test/reviewer-only").status_code == 403


def test_admin_passes_every_role_check(role_pages, seeded, client, login):
    login("admin@cms.local")
    assert client.get("/_test/reviewer-only").status_code == 200


def test_anonymous_user_is_redirected_not_403(role_pages, client):
    response = client.get("/_test/reviewer-only")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_roles_required_needs_a_role():
    with pytest.raises(ValueError):
        roles_required()


# ---------- security ----------

def test_password_is_not_stored_or_put_in_session(seeded, client, login):
    login("admin@cms.local")
    user = User.query.filter_by(email="admin@cms.local").one()
    assert "demo1234" not in user.password_hash
    with client.session_transaction() as session:
        assert "demo1234" not in str(dict(session))


def test_post_without_csrf_token_is_rejected(seeded, app, client):
    app.config["CSRF_ENABLED"] = True
    response = client.post("/login", data={"email": "admin@cms.local", "password": "demo1234"})
    assert response.status_code == 400


def test_post_with_csrf_token_is_accepted(seeded, app, client):
    app.config["CSRF_ENABLED"] = True
    page = client.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    response = client.post(
        "/login",
        data={"email": "admin@cms.local", "password": "demo1234", "csrf_token": token},
    )
    assert response.status_code == 302
