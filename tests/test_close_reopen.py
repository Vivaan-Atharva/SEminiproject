"""Tests for closing and reopening change requests (CMS-9)."""

import pytest

from cms.constants import Status
from cms.models import ChangeRequest, StatusHistory, User


def _cr(number):
    return ChangeRequest.query.filter_by(cr_number=number).one()


def _history(cr):
    return StatusHistory.query.filter_by(change_request_id=cr.id).all()


# --- close -----------------------------------------------------------------


def test_requester_closes_a_resolved_cr(seeded, client, login):
    login("requester@cms.local")
    cr = _cr("CR-0008")

    response = client.post(f"/change-requests/{cr.id}/close")

    assert response.status_code == 302
    cr = _cr("CR-0008")
    assert cr.status == Status.CLOSED
    assert cr.closed_at is not None
    rows = _history(cr)
    assert [(r.from_status, r.to_status) for r in rows] == [(Status.RESOLVED, Status.CLOSED)]


def test_reviewer_may_close_too(seeded, client, login):
    login("reviewer@cms.local")
    client.post(f"/change-requests/{_cr('CR-0008').id}/close")
    assert _cr("CR-0008").status == Status.CLOSED


def test_close_shows_a_success_message(seeded, client, login):
    login("requester@cms.local")
    response = client.post(f"/change-requests/{_cr('CR-0008').id}/close", follow_redirects=True)
    assert b"alert-success" in response.data


# --- reopen ----------------------------------------------------------------


def test_reopen_with_a_reason(seeded, client, login):
    login("requester@cms.local")
    cr = _cr("CR-0008")
    assignee_id = cr.assignee_id

    client.post(f"/change-requests/{cr.id}/reopen", data={"reason": "Typo is still there on page 3"})

    cr = _cr("CR-0008")
    assert cr.status == Status.REOPENED
    assert cr.assignee_id == assignee_id  # same engineer resumes work
    assert cr.closed_at is None
    row = _history(cr)[-1]
    assert (row.from_status, row.to_status) == (Status.RESOLVED, Status.REOPENED)
    assert row.reason == "Typo is still there on page 3"


@pytest.mark.parametrize("data", [{}, {"reason": ""}, {"reason": "   "}])
def test_reopen_without_a_reason_is_refused(seeded, client, login, data):
    login("requester@cms.local")
    cr = _cr("CR-0008")

    response = client.post(f"/change-requests/{cr.id}/reopen", data=data, follow_redirects=True)

    assert b"alert-danger" in response.data
    assert _cr("CR-0008").status == Status.RESOLVED
    assert _history(cr) == []


def test_reopened_cr_can_be_resumed_by_the_assignee(seeded, client, login, logout):
    login("requester@cms.local")
    cr = _cr("CR-0008")
    client.post(f"/change-requests/{cr.id}/reopen", data={"reason": "Not fixed"})
    logout()

    from cms.services import workflow_service

    engineer = User.query.filter_by(email="engineer1@cms.local").one()
    assert Status.IN_PROGRESS in workflow_service.allowed_next(_cr("CR-0008"), engineer)


# --- who may do it ---------------------------------------------------------


@pytest.mark.parametrize("action", ["close", "reopen"])
def test_other_requester_gets_403(seeded, client, login, action):
    login("requester2@cms.local")
    cr = _cr("CR-0008")  # belongs to requester@cms.local

    response = client.post(f"/change-requests/{cr.id}/{action}", data={"reason": "x"})

    assert response.status_code == 403
    assert _cr("CR-0008").status == Status.RESOLVED


@pytest.mark.parametrize("action", ["close", "reopen"])
def test_engineer_gets_403(seeded, client, login, action):
    login("engineer1@cms.local")  # the assignee, but not requester or reviewer
    cr = _cr("CR-0008")

    response = client.post(f"/change-requests/{cr.id}/{action}", data={"reason": "x"})

    assert response.status_code == 403
    assert _cr("CR-0008").status == Status.RESOLVED


@pytest.mark.parametrize("action", ["close", "reopen"])
def test_anonymous_user_is_sent_to_login(seeded, client, action):
    response = client.post(f"/change-requests/{_cr('CR-0008').id}/{action}", data={"reason": "x"})
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_unknown_cr_returns_404(seeded, client, login):
    login("requester@cms.local")
    assert client.post("/change-requests/9999/close").status_code == 404


# --- other statuses ----------------------------------------------------------


def test_closing_an_in_progress_cr_is_refused(seeded, client, login):
    login("requester2@cms.local")  # CR-0007 is theirs, In Progress
    cr = _cr("CR-0007")

    response = client.post(f"/change-requests/{cr.id}/close", follow_redirects=True)

    assert b"alert-danger" in response.data
    assert _cr("CR-0007").status == Status.IN_PROGRESS
    assert _cr("CR-0007").closed_at is None


@pytest.mark.parametrize(
    "number, owner",
    [
        ("CR-0001", "requester@cms.local"),   # Submitted
        ("CR-0006", "requester@cms.local"),   # Assigned
        ("CR-0009", "requester2@cms.local"),  # already Closed
        ("CR-0010", "requester@cms.local"),   # Rejected
    ],
)
def test_close_and_reopen_refused_in_other_statuses(seeded, client, login, number, owner):
    login(owner)
    cr = _cr(number)
    before = cr.status

    client.post(f"/change-requests/{cr.id}/close")
    client.post(f"/change-requests/{cr.id}/reopen", data={"reason": "please"})

    assert _cr(number).status == before


def test_csrf_token_is_required_when_csrf_is_on(seeded, app, client, login):
    login("requester@cms.local")
    app.config["CSRF_ENABLED"] = True
    response = client.post(f"/change-requests/{_cr('CR-0008').id}/close")
    assert response.status_code == 400
    assert _cr("CR-0008").status == Status.RESOLVED


# --- buttons on the page -------------------------------------------------------


def test_requester_sees_close_and_reopen_on_a_resolved_cr(seeded, client, login):
    login("requester@cms.local")
    page = client.get(f"/change-requests/{_cr('CR-0008').id}")
    assert b"/close" in page.data and b"/reopen" in page.data
    assert b'name="reason"' in page.data


def test_reviewer_sees_the_buttons_on_a_resolved_cr(seeded, client, login):
    login("reviewer@cms.local")
    page = client.get(f"/change-requests/{_cr('CR-0008').id}")
    assert b"/close" in page.data and b"/reopen" in page.data


@pytest.mark.parametrize("email", ["engineer1@cms.local", "engineer2@cms.local"])
def test_engineers_do_not_see_the_buttons(seeded, client, login, email):
    login(email)
    page = client.get(f"/change-requests/{_cr('CR-0008').id}")
    assert b"/close" not in page.data and b"/reopen" not in page.data


@pytest.mark.parametrize(
    "number, owner",
    [
        ("CR-0001", "requester@cms.local"),
        ("CR-0006", "requester@cms.local"),
        ("CR-0007", "requester2@cms.local"),
        ("CR-0009", "requester2@cms.local"),
        ("CR-0010", "requester@cms.local"),
    ],
)
def test_buttons_hidden_in_other_statuses(seeded, client, login, number, owner):
    login(owner)
    page = client.get(f"/change-requests/{_cr(number).id}")
    assert page.status_code == 200
    assert b"/close" not in page.data and b"/reopen" not in page.data