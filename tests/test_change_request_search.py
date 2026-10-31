"""CMS-4: List, search, filter and view change requests."""

import pytest
from werkzeug.exceptions import Forbidden, NotFound

from cms.constants import COMPONENTS, Priority, Role, Status
from cms.models import ChangeRequest, User
from cms.services.change_request_service import get_by_id_or_404, search


def user(email):
    return User.query.filter_by(email=email).one()


# ---------- Service tests: search & filters ----------

def test_search_all_for_staff(seeded):
    items = search(user("reviewer@cms.local"))
    assert len(items) == 10


def test_search_requester_sees_only_own(seeded):
    requester2 = user("requester2@cms.local")
    items = search(requester2)
    assert len(items) == 4
    for cr in items:
        assert cr.requester_id == requester2.id


def test_search_by_query_text(seeded):
    reviewer = user("reviewer@cms.local")
    # match title
    results = search(reviewer, q="dark mode")
    assert len(results) == 1
    assert results[0].cr_number == "CR-0002"

    # match CR number case-insensitively
    results_cr = search(reviewer, q="cr-0006")
    assert len(results_cr) == 1
    assert results_cr[0].cr_number == "CR-0006"


def test_filter_by_status(seeded):
    reviewer = user("reviewer@cms.local")
    approved = search(reviewer, status=Status.APPROVED)
    assert len(approved) == 3
    for cr in approved:
        assert cr.status == Status.APPROVED


def test_filter_by_priority(seeded):
    reviewer = user("reviewer@cms.local")
    critical = search(reviewer, priority=Priority.CRITICAL)
    assert len(critical) == 2
    assert {cr.cr_number for cr in critical} == {"CR-0005", "CR-0006"}


def test_filter_by_component(seeded):
    reviewer = user("reviewer@cms.local")
    backend = search(reviewer, component="Backend API")
    assert len(backend) == 3
    assert {cr.cr_number for cr in backend} == {"CR-0004", "CR-0007", "CR-0009"}


def test_filter_by_assignee_and_requester(seeded):
    reviewer = user("reviewer@cms.local")
    engineer1 = user("engineer1@cms.local")
    assigned = search(reviewer, assignee_id=engineer1.id)
    assert {cr.cr_number for cr in assigned} == {"CR-0006", "CR-0008"}

    requester2 = user("requester2@cms.local")
    requested = search(reviewer, requester_id=requester2.id)
    assert len(requested) == 4


def test_filter_combined(seeded):
    reviewer = user("reviewer@cms.local")
    results = search(
        reviewer,
        status=Status.APPROVED,
        priority=Priority.CRITICAL,
    )
    assert len(results) == 1
    assert results[0].cr_number == "CR-0005"


def test_search_sort_orders(seeded):
    reviewer = user("reviewer@cms.local")
    newest = search(reviewer, sort="newest")
    assert newest[0].id > newest[-1].id

    oldest = search(reviewer, sort="oldest")
    assert oldest[0].id < oldest[-1].id

    by_priority = search(reviewer, sort="priority")
    priorities = [cr.priority for cr in by_priority]
    # Critical should precede Low
    assert priorities.index(Priority.CRITICAL) < priorities.index(Priority.LOW)


# ---------- Service tests: get_by_id_or_404 ----------

def test_get_by_id_or_404_success(seeded):
    cr = get_by_id_or_404(1)
    assert cr.cr_number == "CR-0001"


def test_get_by_id_or_404_not_found(seeded):
    with pytest.raises(NotFound):
        get_by_id_or_404(9999)


def test_get_by_id_or_404_requester_isolation(seeded):
    requester2 = user("requester2@cms.local")
    # CR-0001 belongs to requester@cms.local
    with pytest.raises(Forbidden):
        get_by_id_or_404(1, requester2)

    # CR-0002 belongs to requester2
    cr = get_by_id_or_404(2, requester2)
    assert cr.cr_number == "CR-0002"


# ---------- Route tests: list and detail ----------

def test_list_requires_login(client):
    response = client.get("/change-requests")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_list_renders_for_reviewer(seeded, client, login):
    login("reviewer@cms.local")
    response = client.get("/change-requests")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "CR-0001" in page
    assert "CR-0010" in page
    assert "Apply filters" in page


def test_list_empty_state(seeded, client, login):
    login("reviewer@cms.local")
    response = client.get("/change-requests?q=NonexistentQueryString12345")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "No change requests found" in page


def test_list_filters_in_route(seeded, client, login):
    login("reviewer@cms.local")
    response = client.get("/change-requests?priority=Critical")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "CR-0005" in page
    assert "CR-0006" in page
    assert "CR-0001" not in page


def test_detail_requires_login(client):
    response = client.get("/change-requests/1")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_detail_renders_all_fields(seeded, client, login):
    login("reviewer@cms.local")
    response = client.get("/change-requests/6")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "CR-0006" in page
    assert "Rotate expired TLS certificate" in page
    assert "Infrastructure" in page
    assert "Critical" in page
    assert "Assigned" in page
    assert "Eshan Engineer" in page
    assert "Rahul Requester" in page
    assert "Back to list" in page


def test_detail_unknown_id_returns_404(seeded, client, login):
    login("reviewer@cms.local")
    response = client.get("/change-requests/9999")
    assert response.status_code == 404


def test_detail_requester_role_isolation(seeded, client, login):
    login("requester2@cms.local")
    # CR 1 belongs to requester1 -> 403
    forbidden_resp = client.get("/change-requests/1")
    assert forbidden_resp.status_code == 403

    # CR 2 belongs to requester2 -> 200
    allowed_resp = client.get("/change-requests/2")
    assert allowed_resp.status_code == 200
    assert "CR-0002" in allowed_resp.get_data(as_text=True)


def test_dashboard_cr_numbers_link_to_detail(seeded, client, login):
    login("admin@cms.local")
    page = client.get("/").get_data(as_text=True)
    cr = ChangeRequest.query.filter_by(cr_number="CR-0006").one()
    assert f'href="/change-requests/{cr.id}">CR-0006</a>' in page
