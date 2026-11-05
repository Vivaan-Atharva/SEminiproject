"""CMS-6: a reviewer starts a review, approves or rejects a change request."""

import pytest

from cms.constants import Status
from cms.extensions import db
from cms.models import ChangeRequest, StatusHistory

REVIEWER = "reviewer@cms.local"
ENGINEER1 = "engineer1@cms.local"
REQUESTER = "requester@cms.local"  # requested CR-0001
REQUESTER2 = "requester2@cms.local"
ADMIN = "admin@cms.local"

START_REVIEW = "/change-requests/{}/start-review"
APPROVE = "/change-requests/{}/approve"
REJECT = "/change-requests/{}/reject"
DETAIL = "/change-requests/{}"

# Seeded: CR-0001 Submitted, CR-0002 Under Review, CR-0003 Approved, CR-0010 Rejected.


def get_cr(number):
    db.session.expire_all()  # the request may have changed it behind this session's back
    return ChangeRequest.query.filter_by(cr_number=number).one()


def history_rows(cr):
    return [(row.from_status, row.to_status) for row in cr.status_history]


# --- the reviewer's path ----------------------------------------------------


def test_reviewer_moves_submitted_to_under_review_to_approved(seeded, client, login):
    login(REVIEWER)
    cr = get_cr("CR-0001")

    first = client.post(START_REVIEW.format(cr.id))
    assert first.status_code == 302
    assert first.headers["Location"].endswith(DETAIL.format(cr.id))
    assert get_cr("CR-0001").status == Status.UNDER_REVIEW

    second = client.post(APPROVE.format(cr.id))
    assert second.status_code == 302
    cr = get_cr("CR-0001")
    assert cr.status == Status.APPROVED
    assert history_rows(cr) == [
        (Status.SUBMITTED, Status.UNDER_REVIEW),
        (Status.UNDER_REVIEW, Status.APPROVED),
    ]
    assert {row.user.email for row in cr.status_history} == {REVIEWER}


def test_review_actions_show_success_messages(seeded, client, login):
    login(REVIEWER)
    cr = get_cr("CR-0001")

    started = client.post(START_REVIEW.format(cr.id), follow_redirects=True)
    approved = client.post(APPROVE.format(cr.id), follow_redirects=True)

    assert b"CR-0001 is now under review." in started.data
    assert b"CR-0001 was approved." in approved.data


def test_admin_may_review(seeded, client, login):
    login(ADMIN)

    client.post(APPROVE.format(get_cr("CR-0002").id))

    assert get_cr("CR-0002").status == Status.APPROVED


# --- rejecting --------------------------------------------------------------


def test_rejecting_with_a_reason_sets_rejected_and_shows_the_reason_in_the_history(seeded, client, login):
    login(REVIEWER)
    cr = get_cr("CR-0002")

    response = client.post(REJECT.format(cr.id), data={"reason": "  Duplicate of CR-0001.  "})

    assert response.status_code == 302
    cr = get_cr("CR-0002")
    assert cr.status == Status.REJECTED
    assert history_rows(cr) == [(Status.UNDER_REVIEW, Status.REJECTED)]
    assert cr.status_history[0].reason == "Duplicate of CR-0001."
    page = client.get(DETAIL.format(cr.id)).data
    assert b"Reason: Duplicate of CR-0001." in page
    assert b"Under Review &rarr; <strong>Rejected</strong>" in page


def test_reject_shows_a_success_message(seeded, client, login):
    login(REVIEWER)

    response = client.post(
        REJECT.format(get_cr("CR-0002").id), data={"reason": "Out of scope."}, follow_redirects=True
    )

    assert b"CR-0002 was rejected." in response.data


@pytest.mark.parametrize("data", [{}, {"reason": ""}, {"reason": "  \n "}])
def test_rejecting_without_a_reason_is_refused(seeded, client, login, data):
    login(REVIEWER)
    cr = get_cr("CR-0002")

    response = client.post(REJECT.format(cr.id), data=data, follow_redirects=True)

    assert response.status_code == 200
    assert b"A reason is required to move a change request to Rejected." in response.data
    cr = get_cr("CR-0002")
    assert cr.status == Status.UNDER_REVIEW
    assert cr.status_history == []


def test_a_reason_is_shown_escaped_in_the_history(seeded, client, login):
    login(REVIEWER)
    cr = get_cr("CR-0002")

    client.post(REJECT.format(cr.id), data={"reason": "<script>alert(1)</script>"})

    page = client.get(DETAIL.format(cr.id)).data
    assert b"<script>alert(1)</script>" not in page
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in page


# --- who may not -------------------------------------------------------------


@pytest.mark.parametrize("email", [REQUESTER, REQUESTER2, ENGINEER1])
@pytest.mark.parametrize(
    ("url", "number", "data", "status"),
    [
        (START_REVIEW, "CR-0001", {}, Status.SUBMITTED),
        (APPROVE, "CR-0002", {}, Status.UNDER_REVIEW),
        (REJECT, "CR-0002", {"reason": "Not needed."}, Status.UNDER_REVIEW),
    ],
    ids=["start-review", "approve", "reject"],
)
def test_requesters_and_engineers_get_403_even_when_calling_the_url_directly(
    seeded, client, login, email, url, number, data, status
):
    login(email)
    cr = get_cr(number)

    response = client.post(url.format(cr.id), data=data)

    assert response.status_code == 403
    assert get_cr(number).status == status
    assert StatusHistory.query.count() == 0


@pytest.mark.parametrize("url", [START_REVIEW, APPROVE, REJECT])
def test_actions_require_login(seeded, client, url):
    response = client.post(url.format(get_cr("CR-0002").id), data={"reason": "No."})

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert get_cr("CR-0002").status == Status.UNDER_REVIEW


# --- moves that are not allowed ---------------------------------------------


@pytest.mark.parametrize(
    ("url", "number", "data", "message", "status"),
    [
        (APPROVE, "CR-0001", {}, b"cannot move from Submitted to Approved", Status.SUBMITTED),
        (REJECT, "CR-0001", {"reason": "No."}, b"cannot move from Submitted to Rejected", Status.SUBMITTED),
        (START_REVIEW, "CR-0002", {}, b"cannot move from Under Review to Under Review", Status.UNDER_REVIEW),
        (APPROVE, "CR-0010", {}, b"cannot move from Rejected to Approved", Status.REJECTED),
        (START_REVIEW, "CR-0003", {}, b"cannot move from Approved to Under Review", Status.APPROVED),
    ],
)
def test_a_move_the_workflow_does_not_allow_is_refused_with_a_message(
    seeded, client, login, url, number, data, message, status
):
    login(REVIEWER)
    cr = get_cr(number)

    response = client.post(url.format(cr.id), data=data, follow_redirects=True)

    assert response.status_code == 200
    assert message in response.data
    assert get_cr(number).status == status
    assert StatusHistory.query.count() == 0


@pytest.mark.parametrize("url", [START_REVIEW, APPROVE, REJECT])
def test_actions_on_a_missing_change_request_are_404(seeded, client, login, url):
    login(REVIEWER)

    assert client.post(url.format(9999), data={"reason": "No."}).status_code == 404


@pytest.mark.parametrize("url", [START_REVIEW, APPROVE, REJECT])
def test_actions_only_accept_post(seeded, client, login, url):
    login(REVIEWER)

    assert client.get(url.format(get_cr("CR-0001").id)).status_code == 405


# --- what the detail page shows ----------------------------------------------


def test_reviewer_sees_only_start_review_on_a_submitted_request(seeded, client, login):
    login(REVIEWER)
    cr = get_cr("CR-0001")

    page = client.get(DETAIL.format(cr.id)).data

    assert f'action="{START_REVIEW.format(cr.id)}"'.encode() in page
    assert b'name="csrf_token"' in page
    assert APPROVE.format(cr.id).encode() not in page
    assert REJECT.format(cr.id).encode() not in page


def test_reviewer_sees_approve_and_reject_with_a_reason_box_when_under_review(seeded, client, login):
    login(REVIEWER)
    cr = get_cr("CR-0002")

    page = client.get(DETAIL.format(cr.id)).data

    assert f'action="{APPROVE.format(cr.id)}"'.encode() in page
    assert f'action="{REJECT.format(cr.id)}"'.encode() in page
    assert b'name="reason"' in page
    assert page.count(b'name="csrf_token"') >= 2
    assert START_REVIEW.format(cr.id).encode() not in page


@pytest.mark.parametrize(
    ("email", "number"),
    [
        (REQUESTER, "CR-0001"),
        (REQUESTER2, "CR-0002"),
        (ENGINEER1, "CR-0001"),
        (ENGINEER1, "CR-0002"),
        (REVIEWER, "CR-0003"),  # Approved: nothing left for a reviewer to decide
        (REVIEWER, "CR-0010"),  # Rejected is final
    ],
)
def test_nobody_else_sees_the_review_buttons(seeded, client, login, email, number):
    login(email)
    cr = get_cr(number)

    page = client.get(DETAIL.format(cr.id)).data

    assert START_REVIEW.format(cr.id).encode() not in page
    assert APPROVE.format(cr.id).encode() not in page
    assert REJECT.format(cr.id).encode() not in page
