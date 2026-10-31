"""Tests for assigning and reassigning change requests (CMS-7)."""

import pytest

from cms.constants import Role, Status
from cms.extensions import db
from cms.models import AssignmentHistory, ChangeRequest, StatusHistory, User
from cms.services import assignment_service
from cms.services.assignment_service import AssignmentError, AssignmentPermissionDenied


def _cr(number):
    return ChangeRequest.query.filter_by(cr_number=number).one()


def _user(email):
    return User.query.filter_by(email=email).one()


# --- service ---------------------------------------------------------------


def test_assignable_engineers_are_active_engineers_sorted_by_name(seeded):
    names = [u.name for u in assignment_service.assignable_engineers()]
    assert names == ["Eshan Engineer", "Meera Engineer"]  # no inactive, no reviewer/requester


def test_assign_approved_cr_sets_assignee_status_and_history(seeded):
    cr, engineer, reviewer = _cr("CR-0003"), _user("engineer1@cms.local"), _user("reviewer@cms.local")

    assignment_service.assign(cr, engineer, reviewer)

    cr = _cr("CR-0003")
    assert cr.assignee_id == engineer.id
    assert cr.status == Status.ASSIGNED
    rows = AssignmentHistory.query.filter_by(change_request_id=cr.id).all()
    assert len(rows) == 1
    assert rows[0].from_user_id is None
    assert rows[0].to_user_id == engineer.id
    assert rows[0].assigned_by_id == reviewer.id
    # the status engine wrote the status history row for Approved -> Assigned
    status_rows = StatusHistory.query.filter_by(change_request_id=cr.id).all()
    assert [(r.from_status, r.to_status) for r in status_rows] == [(Status.APPROVED, Status.ASSIGNED)]


def test_admin_may_assign(seeded):
    assignment_service.assign(_cr("CR-0004"), _user("engineer2@cms.local"), _user("admin@cms.local"))
    assert _cr("CR-0004").status == Status.ASSIGNED


@pytest.mark.parametrize("email", ["engineer3@cms.local", "requester@cms.local", "reviewer@cms.local"])
def test_inactive_or_non_engineer_is_rejected(seeded, email):
    cr = _cr("CR-0003")
    with pytest.raises(AssignmentError):
        assignment_service.assign(cr, _user(email), _user("reviewer@cms.local"))
    cr = _cr("CR-0003")
    assert cr.assignee_id is None
    assert cr.status == Status.APPROVED
    assert AssignmentHistory.query.count() == 0


def test_none_engineer_is_rejected(seeded):
    with pytest.raises(AssignmentError):
        assignment_service.assign(_cr("CR-0003"), None, _user("reviewer@cms.local"))


@pytest.mark.parametrize("email", ["requester@cms.local", "engineer1@cms.local"])
def test_service_refuses_non_reviewers(seeded, email):
    with pytest.raises(AssignmentPermissionDenied):
        assignment_service.assign(_cr("CR-0003"), _user("engineer1@cms.local"), _user(email))
    assert _cr("CR-0003").status == Status.APPROVED


def test_reassign_while_assigned_changes_only_the_assignee(seeded):
    cr = _cr("CR-0006")  # Assigned to engineer1
    old, new = _user("engineer1@cms.local"), _user("engineer2@cms.local")
    status_rows_before = StatusHistory.query.filter_by(change_request_id=cr.id).count()

    assignment_service.assign(cr, new, _user("reviewer@cms.local"))

    cr = _cr("CR-0006")
    assert cr.assignee_id == new.id
    assert cr.status == Status.ASSIGNED
    assert StatusHistory.query.filter_by(change_request_id=cr.id).count() == status_rows_before
    row = AssignmentHistory.query.filter_by(change_request_id=cr.id).one()
    assert (row.from_user_id, row.to_user_id) == (old.id, new.id)


def test_reassign_in_progress_moves_it_back_to_assigned(seeded):
    cr = _cr("CR-0007")  # In Progress with engineer2
    assignment_service.assign(cr, _user("engineer1@cms.local"), _user("reviewer@cms.local"))

    cr = _cr("CR-0007")
    assert cr.status == Status.ASSIGNED
    assert cr.assignee.email == "engineer1@cms.local"
    row = AssignmentHistory.query.filter_by(change_request_id=cr.id).one()
    assert row.from_user.email == "engineer2@cms.local"
    last = StatusHistory.query.filter_by(change_request_id=cr.id).one()
    assert (last.from_status, last.to_status) == (Status.IN_PROGRESS, Status.ASSIGNED)


def test_assigning_to_the_current_assignee_is_rejected(seeded):
    with pytest.raises(AssignmentError):
        assignment_service.assign(_cr("CR-0006"), _user("engineer1@cms.local"), _user("reviewer@cms.local"))
    assert AssignmentHistory.query.count() == 0


@pytest.mark.parametrize("number", ["CR-0001", "CR-0002", "CR-0008", "CR-0009", "CR-0010"])
def test_cr_in_other_statuses_cannot_be_assigned(seeded, number):
    before = _cr(number).status
    with pytest.raises(AssignmentError):
        assignment_service.assign(_cr(number), _user("engineer1@cms.local"), _user("reviewer@cms.local"))
    assert _cr(number).status == before
    assert AssignmentHistory.query.count() == 0


# --- routes ----------------------------------------------------------------


def test_reviewer_assigns_through_the_route(seeded, client, login):
    login("reviewer@cms.local")
    cr = _cr("CR-0003")
    engineer = _user("engineer1@cms.local")

    response = client.post(f"/change-requests/{cr.id}/assign", data={"assignee_id": engineer.id})

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/change-requests/{cr.id}")
    cr = _cr("CR-0003")
    assert cr.assignee_id == engineer.id and cr.status == Status.ASSIGNED


def test_assigned_cr_shows_in_assigned_to_me_for_the_engineer(seeded, client, login, logout):
    login("reviewer@cms.local")
    cr = _cr("CR-0003")
    client.post(f"/change-requests/{cr.id}/assign", data={"assignee_id": _user("engineer1@cms.local").id})
    logout()

    login("engineer1@cms.local")
    page = client.get("/")
    assert b"CR-0003" in page.data


@pytest.mark.parametrize("email", ["requester@cms.local", "engineer1@cms.local"])
def test_other_roles_get_403_on_assign(seeded, client, login, email):
    login(email)
    cr = _cr("CR-0003")
    response = client.post(
        f"/change-requests/{cr.id}/assign", data={"assignee_id": _user("engineer2@cms.local").id}
    )
    assert response.status_code == 403
    assert _cr("CR-0003").assignee_id is None


def test_anonymous_user_is_sent_to_login(seeded, client):
    cr = _cr("CR-0003")
    response = client.post(f"/change-requests/{cr.id}/assign", data={"assignee_id": "1"})
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_invalid_assignees_flash_an_error_and_change_nothing(seeded, client, login):
    login("reviewer@cms.local")
    cr = _cr("CR-0003")
    for value in [_user("engineer3@cms.local").id, _user("requester@cms.local").id, "", "abc", 99999]:
        response = client.post(f"/change-requests/{cr.id}/assign", data={"assignee_id": value}, follow_redirects=True)
        assert response.status_code == 200
        assert b"alert-danger" in response.data
    assert _cr("CR-0003").status == Status.APPROVED
    assert AssignmentHistory.query.count() == 0


def test_unknown_cr_returns_404(seeded, client, login):
    login("reviewer@cms.local")
    response = client.post("/change-requests/9999/assign", data={"assignee_id": "1"})
    assert response.status_code == 404


def test_csrf_token_is_required_when_csrf_is_on(seeded, app, client, login):
    login("reviewer@cms.local")
    app.config["CSRF_ENABLED"] = True
    cr = _cr("CR-0003")
    response = client.post(f"/change-requests/{cr.id}/assign", data={"assignee_id": _user("engineer1@cms.local").id})
    assert response.status_code == 400
    assert _cr("CR-0003").assignee_id is None


# --- UI ----------------------------------------------------------------------


def test_assign_form_shows_for_reviewer_on_approved_cr(seeded, client, login):
    login("reviewer@cms.local")
    page = client.get(f"/change-requests/{_cr('CR-0003').id}")
    assert b'action="/change-requests/%d/assign"' % _cr("CR-0003").id in page.data
    assert b"Eshan Engineer" in page.data and b"Meera Engineer" in page.data
    assert b"Old Engineer" not in page.data  # inactive engineers are not offered


def test_reassign_label_when_already_assigned(seeded, client, login):
    login("reviewer@cms.local")
    page = client.get(f"/change-requests/{_cr('CR-0006').id}")
    assert b">Reassign<" in page.data or b"Reassign</button>" in page.data


@pytest.mark.parametrize("email", ["requester@cms.local", "engineer1@cms.local"])
def test_assign_form_hidden_from_requesters_and_engineers(seeded, client, login, email):
    login(email)
    page = client.get(f"/change-requests/{_cr('CR-0003').id}")
    assert page.status_code == 200
    assert b"/assign" not in page.data


@pytest.mark.parametrize("number", ["CR-0001", "CR-0008", "CR-0009"])
def test_assign_form_hidden_in_other_statuses(seeded, client, login, number):
    login("reviewer@cms.local")
    page = client.get(f"/change-requests/{_cr(number).id}")
    assert b"/assign" not in page.data