"""CMS-3: create a change request with validation."""

import pytest

from cms.constants import COMPONENTS, CRType, Priority, Status
from cms.models import ChangeRequest, User
from cms.services.change_request_service import ValidationError, create


def valid_data(**overrides):
    data = {
        "title": "Improve audit logging",
        "description": "Keep detailed audit information for change requests.",
        "cr_type": CRType.ENHANCEMENT,
        "priority": Priority.HIGH,
        "component": COMPONENTS[0],
    }
    data.update(overrides)
    return data


def requester():
    return User.query.filter_by(email="requester@cms.local").one()


def test_create_sets_number_status_requester_and_trimmed_values(seeded):
    cr = create(valid_data(title="  Improve audit logging  "), requester())

    assert cr.cr_number == "CR-0011"
    assert cr.status == Status.SUBMITTED
    assert cr.requester == requester()
    assert cr.title == "Improve audit logging"
    assert ChangeRequest.query.count() == 11


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", " "),
        ("title", "x" * 201),
        ("description", " "),
        ("cr_type", "Invalid type"),
        ("priority", "Urgent"),
        ("component", "Unknown system"),
    ],
)
def test_create_rejects_invalid_fields_without_saving(seeded, field, value):
    before = ChangeRequest.query.count()

    with pytest.raises(ValidationError) as raised:
        create(valid_data(**{field: value}), requester())

    assert field in raised.value.errors
    assert ChangeRequest.query.count() == before


def test_new_form_requires_login(client):
    response = client.get("/change-requests/new")

    assert response.status_code == 302
    assert "/login?next=" in response.headers["Location"]


def test_new_form_loads_for_signed_in_user(seeded, client, login):
    login("requester@cms.local")

    response = client.get("/change-requests/new")

    assert response.status_code == 200
    assert b"New change request" in response.data
    assert b'name="csrf_token"' in response.data


def test_new_form_valid_post_creates_request_and_redirects(seeded, client, login):
    login("requester@cms.local")

    response = client.post("/change-requests/new", data=valid_data())

    assert response.status_code == 302
    created = ChangeRequest.query.filter_by(cr_number="CR-0011").one()
    assert created.requester.email == "requester@cms.local"
    assert response.headers["Location"].endswith("/")


def test_new_form_invalid_post_keeps_values_and_creates_nothing(seeded, client, login):
    login("requester@cms.local")
    data = valid_data(title="", priority="Urgent")

    response = client.post("/change-requests/new", data=data)

    assert response.status_code == 400
    assert b"Title is required." in response.data
    assert b"Choose a valid priority." in response.data
    assert b"Keep detailed audit information" in response.data
    assert ChangeRequest.query.count() == 10
