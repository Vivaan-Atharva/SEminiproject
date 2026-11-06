"""CMS-11: edit a change request."""

from datetime import date, timedelta

import pytest

from cms.constants import COMPONENTS, CRType, Priority, Status
from cms.extensions import db
from cms.models import ChangeRequest, User
from cms.services.change_request_service import ValidationError, can_edit, create, update


def user(email):
    return User.query.filter_by(email=email).one()


def form(**overrides):
    data = {
        "title": "Updated title",
        "description": "Updated description.",
        "cr_type": CRType.ENHANCEMENT,
        "priority": Priority.MEDIUM,
        "component": COMPONENTS[1],
    }
    data.update(overrides)
    return data


@pytest.fixture
def cr(seeded):
    return create(form(title="Original", priority=Priority.LOW), user("requester@cms.local"))


def test_requester_reviewer_and_admin_can_edit(cr):
    assert can_edit(cr, user("requester@cms.local"))
    assert can_edit(cr, user("reviewer@cms.local"))
    assert can_edit(cr, user("admin@cms.local"))


def test_other_requester_and_engineer_cannot_edit(cr):
    assert not can_edit(cr, user("requester2@cms.local"))
    assert not can_edit(cr, user("engineer1@cms.local"))


def test_closed_request_cannot_be_edited(cr):
    cr.status = Status.CLOSED
    db.session.commit()

    assert not can_edit(cr, user("reviewer@cms.local"))


def test_update_saves_fields_and_recalculates_due_date(cr):
    update(cr, form(priority=Priority.CRITICAL), user("requester@cms.local"))

    assert cr.title == "Updated title"
    assert cr.component == COMPONENTS[1]
    assert cr.due_date == date.today() + timedelta(days=1)


def test_update_reuses_create_validation(cr):
    with pytest.raises(ValidationError) as raised:
        update(cr, form(title=" ", priority="Urgent"), user("requester@cms.local"))

    assert {"title", "priority"} <= raised.value.errors.keys()
    db.session.refresh(cr)
    assert cr.title == "Original"


def test_edit_page_prefills_current_values(cr, client, login):
    login("requester@cms.local")

    response = client.get(f"/change-requests/{cr.id}/edit")

    assert response.status_code == 200
    assert b"Edit CR-0011" in response.data
    assert b'value="Original"' in response.data
    assert b"Save changes" in response.data


def test_edit_post_updates_and_redirects(cr, client, login):
    login("reviewer@cms.local")

    response = client.post(f"/change-requests/{cr.id}/edit", data=form())

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/change-requests/{cr.id}")
    assert db.session.get(ChangeRequest, cr.id).title == "Updated title"


def test_edit_post_invalid_returns_400_and_keeps_input(cr, client, login):
    login("requester@cms.local")

    response = client.post(f"/change-requests/{cr.id}/edit", data=form(title=""))

    assert response.status_code == 400
    assert b"Title is required." in response.data
    assert b"Updated description." in response.data


@pytest.mark.parametrize("email", ["requester2@cms.local", "engineer1@cms.local"])
def test_edit_forbidden_for_other_users(cr, client, login, email):
    login(email)

    assert client.get(f"/change-requests/{cr.id}/edit").status_code == 403
    assert client.post(f"/change-requests/{cr.id}/edit", data=form()).status_code == 403


def test_edit_forbidden_once_closed(cr, client, login):
    cr.status = Status.CLOSED
    db.session.commit()
    login("reviewer@cms.local")

    assert client.get(f"/change-requests/{cr.id}/edit").status_code == 403


def test_edit_requires_login(cr, client):
    response = client.get(f"/change-requests/{cr.id}/edit")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_edit_missing_request_is_404(seeded, client, login):
    login("reviewer@cms.local")

    assert client.get("/change-requests/9999/edit").status_code == 404


def test_detail_shows_edit_button_only_when_allowed(cr, client, login, logout):
    login("requester@cms.local")
    assert b"/edit" in client.get(f"/change-requests/{cr.id}").data
    logout()
    login("engineer1@cms.local")
    assert b"/edit" not in client.get(f"/change-requests/{cr.id}").data
