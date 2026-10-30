"""CMS-1: the skeleton starts, the database works, and demo data loads."""

import pytest
from sqlalchemy.exc import IntegrityError

from cms.constants import Role, Status
from cms.extensions import db
from cms.models import ChangeRequest, User, format_cr_number
from cms.seed import DEMO_PASSWORD, DEMO_USERS, seed_demo_data


def test_app_uses_test_config(app):
    assert app.config["TESTING"] is True
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_home_page_loads_with_empty_database(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Change Management Software" in response.data
    assert b"flask --app cms seed" in response.data


def test_unknown_page_returns_404(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert b"404" in response.data


def test_password_is_hashed(app):
    user = User(name="Test", email="t@cms.local", role=Role.REQUESTER)
    user.set_password("secret123")
    db.session.add(user)
    db.session.commit()

    assert user.password_hash != "secret123"
    assert user.check_password("secret123")
    assert not user.check_password("wrong")


def test_duplicate_email_is_rejected(app):
    for _ in range(2):
        user = User(name="Dup", email="dup@cms.local", role=Role.REQUESTER)
        user.set_password("x")
        db.session.add(user)
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_cr_number_format():
    assert format_cr_number(7) == "CR-0007"
    assert format_cr_number(123) == "CR-0123"


def test_seed_creates_users_for_every_role(seeded):
    assert User.query.count() == len(DEMO_USERS)
    for role in Role.ALL:
        assert User.query.filter_by(role=role).count() >= 1
    assert User.query.filter_by(role=Role.ENGINEER, active=False).count() == 1
    assert User.query.first().check_password(DEMO_PASSWORD)


def test_seed_creates_change_requests_in_useful_statuses(seeded):
    assert ChangeRequest.query.count() == 10
    # CMS-7 needs approved requests to assign before CMS-6 exists.
    assert ChangeRequest.query.filter_by(status=Status.APPROVED).count() >= 2
    numbers = [cr.cr_number for cr in ChangeRequest.query.all()]
    assert len(numbers) == len(set(numbers))
    assigned = ChangeRequest.query.filter_by(status=Status.ASSIGNED).first()
    assert assigned.assignee is not None
    assert assigned.assignee.role == Role.ENGINEER


def test_seed_can_run_twice_without_duplicates(seeded):
    result = seed_demo_data()
    assert result == {"users_added": 0, "change_requests_added": 0}
    assert User.query.count() == len(DEMO_USERS)
    assert ChangeRequest.query.count() == 10


def test_home_page_shows_seeded_counts(seeded, client):
    response = client.get("/")
    assert b'data-test="cr-count">10<' in response.data


def test_closed_and_rejected_requests_are_not_open(seeded):
    for cr in ChangeRequest.query.all():
        assert cr.is_open == (cr.status not in (Status.CLOSED, Status.REJECTED))
