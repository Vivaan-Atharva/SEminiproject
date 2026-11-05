"""CMS-8: an engineer starts work on a change request and resolves it."""

import pytest

from cms.constants import Status
from cms.extensions import db
from cms.models import ChangeRequest, StatusHistory

ENGINEER1 = "engineer1@cms.local"  # assignee of CR-0006 (Assigned) and CR-0008 (Resolved)
ENGINEER2 = "engineer2@cms.local"  # assignee of CR-0007 (In Progress)
REVIEWER = "reviewer@cms.local"
REQUESTER = "requester@cms.local"
ADMIN = "admin@cms.local"

START = "/change-requests/{}/start-work"
RESOLVE = "/change-requests/{}/resolve"
DETAIL = "/change-requests/{}"


def get_cr(number):
    db.session.expire_all()  # the request may have changed it behind this session's back
    return ChangeRequest.query.filter_by(cr_number=number).one()


def history_rows(cr):
    return [(row.from_status, row.to_status) for row in cr.status_history]


def set_status(number, status):
    cr = get_cr(number)
    cr.status = status
    db.session.commit()


# --- start work -------------------------------------------------------------


def test_assignee_starts_work_and_it_is_recorded_in_the_history(seeded, client, login):
    login(ENGINEER1)
    cr = get_cr("CR-0006")

    response = client.post(START.format(cr.id))

    assert response.status_code == 302
    assert response.headers["Location"].endswith(DETAIL.format(cr.id))
    cr = get_cr("CR-0006")
    assert cr.status == Status.IN_PROGRESS
    assert history_rows(cr) == [(Status.ASSIGNED, Status.IN_PROGRESS)]
    assert cr.status_history[0].user.email == ENGINEER1


def test_start_work_shows_a_success_message(seeded, client, login):
    login(ENGINEER1)

    response = client.post(START.format(get_cr("CR-0006").id), follow_redirects=True)

    assert response.status_code == 200
    assert b"You started work on CR-0006." in response.data


def test_assignee_resumes_work_on_a_reopened_request(seeded, client, login):
    set_status("CR-0008", Status.REOPENED)  # Resolved -> Reopened, engineer1 is the assignee
    login(ENGINEER1)

    client.post(START.format(get_cr("CR-0008").id))

    assert get_cr("CR-0008").status == Status.IN_PROGRESS


def test_only_the_assignee_may_start_work(seeded, client, login):
    login(ENGINEER2)  # CR-0006 is assigned to engineer1
    cr = get_cr("CR-0006")

    response = client.post(START.format(cr.id))

    assert response.status_code == 403
    cr = get_cr("CR-0006")
    assert cr.status == Status.ASSIGNED
    assert cr.status_history == []


@pytest.mark.parametrize("email", [REVIEWER, REQUESTER])
def test_reviewers_and_requesters_cannot_start_work(seeded, client, login, email):
    login(email)
    cr = get_cr("CR-0006")

    assert client.post(START.format(cr.id)).status_code == 403

    assert get_cr("CR-0006").status == Status.ASSIGNED
    assert StatusHistory.query.count() == 0


def test_admin_may_start_work(seeded, client, login):
    login(ADMIN)

    client.post(START.format(get_cr("CR-0006").id))

    assert get_cr("CR-0006").status == Status.IN_PROGRESS


def test_start_work_needs_an_assigned_request(seeded, client, login):
    login(ENGINEER1)
    cr = get_cr("CR-0003")  # Approved, nobody assigned yet

    response = client.post(START.format(cr.id), follow_redirects=True)

    assert response.status_code == 200
    assert b"cannot move from Approved to In Progress" in response.data
    assert get_cr("CR-0003").status == Status.APPROVED
    assert StatusHistory.query.count() == 0


# --- resolve ----------------------------------------------------------------


def test_assignee_resolves_with_a_summary_and_both_steps_show_in_the_history(seeded, client, login):
    login(ENGINEER1)
    cr = get_cr("CR-0006")
    client.post(START.format(cr.id))

    response = client.post(
        RESOLVE.format(cr.id),
        data={"resolution_summary": "  Installed the new certificate and restarted nginx.  "},
    )

    assert response.status_code == 302
    cr = get_cr("CR-0006")
    assert cr.status == Status.RESOLVED
    assert cr.resolution_summary == "Installed the new certificate and restarted nginx."
    assert history_rows(cr) == [
        (Status.ASSIGNED, Status.IN_PROGRESS),
        (Status.IN_PROGRESS, Status.RESOLVED),
    ]

    page = client.get(DETAIL.format(cr.id)).data
    assert b"Installed the new certificate and restarted nginx." in page  # the summary is shown
    assert page.count(b'class="list-group-item px-0 history-entry"') == 2
    assert b"Assigned &rarr; <strong>In Progress</strong>" in page
    assert b"In Progress &rarr; <strong>Resolved</strong>" in page


def test_resolve_shows_a_success_message(seeded, client, login):
    login(ENGINEER2)

    response = client.post(
        RESOLVE.format(get_cr("CR-0007").id),
        data={"resolution_summary": "Raised the limits."},
        follow_redirects=True,
    )

    assert b"CR-0007 was resolved." in response.data


@pytest.mark.parametrize("data", [{}, {"resolution_summary": ""}, {"resolution_summary": "   \n "}])
def test_resolving_without_a_summary_is_refused(seeded, client, login, data):
    login(ENGINEER2)
    cr = get_cr("CR-0007")

    response = client.post(RESOLVE.format(cr.id), data=data, follow_redirects=True)

    assert response.status_code == 200
    assert b"A resolution summary is required" in response.data
    cr = get_cr("CR-0007")
    assert cr.status == Status.IN_PROGRESS
    assert cr.resolution_summary is None
    assert cr.status_history == []


def test_only_the_assignee_may_resolve(seeded, client, login):
    login(ENGINEER1)  # CR-0007 is assigned to engineer2
    cr = get_cr("CR-0007")

    response = client.post(RESOLVE.format(cr.id), data={"resolution_summary": "Done."})

    assert response.status_code == 403
    cr = get_cr("CR-0007")
    assert cr.status == Status.IN_PROGRESS
    assert cr.resolution_summary is None
    assert cr.status_history == []


@pytest.mark.parametrize("email", [REVIEWER, REQUESTER])
def test_reviewers_and_requesters_cannot_resolve(seeded, client, login, email):
    login(email)
    cr = get_cr("CR-0007")

    response = client.post(RESOLVE.format(cr.id), data={"resolution_summary": "Done."})

    assert response.status_code == 403
    assert get_cr("CR-0007").status == Status.IN_PROGRESS
    assert StatusHistory.query.count() == 0


def test_admin_may_resolve(seeded, client, login):
    login(ADMIN)

    client.post(RESOLVE.format(get_cr("CR-0007").id), data={"resolution_summary": "Done by admin."})

    assert get_cr("CR-0007").status == Status.RESOLVED


def test_resolve_needs_work_to_have_started(seeded, client, login):
    login(ENGINEER1)
    cr = get_cr("CR-0006")  # Assigned, work not started

    response = client.post(
        RESOLVE.format(cr.id), data={"resolution_summary": "Done."}, follow_redirects=True
    )

    assert b"cannot move from Assigned to Resolved" in response.data
    cr = get_cr("CR-0006")
    assert cr.status == Status.ASSIGNED
    assert cr.resolution_summary is None


@pytest.mark.parametrize("url", [START, RESOLVE])
def test_actions_require_login(seeded, client, url):
    response = client.post(url.format(get_cr("CR-0006").id), data={"resolution_summary": "Done."})

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert get_cr("CR-0006").status == Status.ASSIGNED


@pytest.mark.parametrize("url", [START, RESOLVE])
def test_actions_on_a_missing_change_request_are_404(seeded, client, login, url):
    login(ENGINEER1)

    assert client.post(url.format(9999), data={"resolution_summary": "Done."}).status_code == 404


@pytest.mark.parametrize("url", [START, RESOLVE])
def test_actions_only_accept_post(seeded, client, login, url):
    login(ENGINEER1)

    assert client.get(url.format(get_cr("CR-0006").id)).status_code == 405


# --- what the detail page shows ----------------------------------------------


def test_assignee_sees_start_work_but_not_resolve(seeded, client, login):
    login(ENGINEER1)
    cr = get_cr("CR-0006")  # Assigned

    page = client.get(DETAIL.format(cr.id)).data

    assert f'action="{START.format(cr.id)}"'.encode() in page
    assert b'name="csrf_token"' in page
    assert RESOLVE.format(cr.id).encode() not in page


def test_assignee_sees_resolve_form_with_a_summary_box_but_not_start_work(seeded, client, login):
    login(ENGINEER2)
    cr = get_cr("CR-0007")  # In Progress

    page = client.get(DETAIL.format(cr.id)).data

    assert f'action="{RESOLVE.format(cr.id)}"'.encode() in page
    assert b'name="resolution_summary"' in page
    assert b'name="csrf_token"' in page
    assert START.format(cr.id).encode() not in page


def test_reopened_request_offers_resume_work(seeded, client, login):
    set_status("CR-0008", Status.REOPENED)
    login(ENGINEER1)

    page = client.get(DETAIL.format(get_cr("CR-0008").id)).data

    assert b"Resume work" in page


@pytest.mark.parametrize(
    ("email", "number"),
    [
        (ENGINEER2, "CR-0006"),  # an engineer who is not the assignee
        (ENGINEER1, "CR-0007"),
        (REVIEWER, "CR-0006"),
        (REVIEWER, "CR-0007"),
        (REQUESTER, "CR-0006"),
        (ENGINEER1, "CR-0009"),  # Closed
        (ENGINEER1, "CR-0001"),  # Submitted
    ],
)
def test_nobody_else_sees_the_engineer_buttons(seeded, client, login, email, number):
    login(email)
    cr = get_cr(number)

    page = client.get(DETAIL.format(cr.id)).data

    assert START.format(cr.id).encode() not in page
    assert RESOLVE.format(cr.id).encode() not in page


def test_history_list_is_shown_for_a_change_request_without_changes(seeded, client, login):
    login(REVIEWER)

    page = client.get(DETAIL.format(get_cr("CR-0001").id)).data

    assert b"Status history" in page
    assert b"No status changes recorded yet." in page
