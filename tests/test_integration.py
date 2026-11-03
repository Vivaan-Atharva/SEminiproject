"""CMS-15: end-to-end tests across roles and modules.

Each test drives a change request through the real web pages, signing in as
the person who would do each step (requester, reviewer, engineer).

The review / start / resolve / close / reopen pages are being built in
Sprint 2. Until a page exists, that step calls the status engine directly as
the same user. Once the route is merged, the step uses the real route
automatically, so these tests become full UI tests without changes.
"""

import pytest

from cms.constants import CRType, Priority, Status
from cms.extensions import db
from cms.models import AssignmentHistory, ChangeRequest, StatusHistory, User
from cms.seed import DEMO_PASSWORD
from cms.services import dashboard_service, workflow_service
from cms.services.workflow_service import WorkflowError

REQUESTER = "requester@cms.local"
OTHER_REQUESTER = "requester2@cms.local"
REVIEWER = "reviewer@cms.local"
ENGINEER = "engineer1@cms.local"
OTHER_ENGINEER = "engineer2@cms.local"
ADMIN = "admin@cms.local"

# URL action (from the team's endpoint contract) -> status it moves to.
ACTIONS = {
    "start-review": Status.UNDER_REVIEW,
    "approve": Status.APPROVED,
    "reject": Status.REJECTED,
    "start-work": Status.IN_PROGRESS,
    "resolve": Status.RESOLVED,
    "close": Status.CLOSED,
    "reopen": Status.REOPENED,
}

NEW_CR = {
    "title": "Add audit log export",
    "description": "Admins need to download the audit log as CSV for compliance.",
    "cr_type": CRType.ENHANCEMENT,
    "priority": Priority.HIGH,
    "component": "Backend API",
}


def user(email):
    return User.query.filter_by(email=email).one()


def fresh(cr_id):
    """Reload the change request so we see what the request actually saved."""
    db.session.expire_all()
    return db.session.get(ChangeRequest, cr_id)


def history(cr_id):
    rows = (
        StatusHistory.query.filter_by(change_request_id=cr_id)
        .order_by(StatusHistory.created_at, StatusHistory.id)
        .all()
    )
    return [(row.from_status, row.to_status) for row in rows]


class Flow:
    """Signs in as different people and performs each step of the lifecycle."""

    def __init__(self, app, client):
        self.app = app
        self.client = client
        self.current = None

    def sign_in(self, email):
        if self.current == email:
            return
        self.sign_out()
        response = self.client.post("/login", data={"email": email, "password": DEMO_PASSWORD})
        assert response.status_code == 302, f"could not sign in as {email}"
        self.current = email

    def sign_out(self):
        if self.current is not None:
            self.client.post("/logout")
            self.current = None

    def get(self, email, path):
        self.sign_in(email)
        return self.client.get(path)

    def create(self, email=REQUESTER, **overrides):
        self.sign_in(email)
        data = {**NEW_CR, **overrides}
        response = self.client.post("/change-requests/new", data=data)
        assert response.status_code == 302, response.get_data(as_text=True)
        cr = ChangeRequest.query.filter_by(title=data["title"]).one()
        assert response.headers["Location"].endswith(f"/change-requests/{cr.id}")
        return cr.id

    def assign(self, email, cr_id, engineer_email):
        self.sign_in(email)
        return self.client.post(
            f"/change-requests/{cr_id}/assign",
            data={"assignee_id": str(user(engineer_email).id)},
        )

    def has_route(self, action):
        rule = f"/change-requests/<int:cr_id>/{action}"
        return any(r.rule == rule and "POST" in r.methods for r in self.app.url_map.iter_rules())

    def do(self, email, cr_id, action, **form):
        """Perform a workflow action as ``email`` and return the resulting status.

        A refused action (wrong person, missing reason...) leaves the status
        unchanged, whichever way it was performed.
        """
        self.sign_in(email)
        if self.has_route(action):
            self.client.post(f"/change-requests/{cr_id}/{action}", data=form)
        else:
            try:
                workflow_service.transition(
                    fresh(cr_id),
                    ACTIONS[action],
                    user(email),
                    reason=form.get("reason"),
                    resolution_summary=form.get("resolution_summary"),
                )
            except WorkflowError:
                pass
        return fresh(cr_id).status

    def to_resolved(self, **overrides):
        """Create a request and take it all the way to Resolved."""
        cr_id = self.create(**overrides)
        assert self.do(REVIEWER, cr_id, "start-review") == Status.UNDER_REVIEW
        assert self.do(REVIEWER, cr_id, "approve") == Status.APPROVED
        assert self.assign(REVIEWER, cr_id, ENGINEER).status_code == 302
        assert self.do(ENGINEER, cr_id, "start-work") == Status.IN_PROGRESS
        assert self.do(ENGINEER, cr_id, "resolve", resolution_summary="Export added.") == Status.RESOLVED
        return cr_id


@pytest.fixture
def flow(seeded, client):
    return Flow(seeded, client)


# ---------- the main path ----------

def test_full_lifecycle_from_submission_to_closure(flow):
    # Requester submits through the form.
    cr_id = flow.create(REQUESTER)
    cr = fresh(cr_id)
    assert cr.cr_number == "CR-0011"  # continues after the 10 demo requests
    assert cr.status == Status.SUBMITTED
    assert cr.requester.email == REQUESTER

    # It shows up in the reviewer's queue.
    page = flow.get(REVIEWER, "/").get_data(as_text=True)
    assert "Waiting for review" in page
    assert NEW_CR["title"] in page

    # Reviewer reviews, approves and assigns it.
    assert flow.do(REVIEWER, cr_id, "start-review") == Status.UNDER_REVIEW
    assert flow.do(REVIEWER, cr_id, "approve") == Status.APPROVED
    response = flow.assign(REVIEWER, cr_id, ENGINEER)
    assert response.status_code == 302
    cr = fresh(cr_id)
    assert cr.status == Status.ASSIGNED
    assert cr.assignee.email == ENGINEER

    # The engineer sees it, starts and resolves it.
    page = flow.get(ENGINEER, "/").get_data(as_text=True)
    assert "Assigned to me" in page
    assert NEW_CR["title"] in page
    assert flow.do(ENGINEER, cr_id, "start-work") == Status.IN_PROGRESS
    summary = "Added /admin/audit-log.csv and a download button."
    assert flow.do(ENGINEER, cr_id, "resolve", resolution_summary=summary) == Status.RESOLVED
    assert fresh(cr_id).resolution_summary == summary

    # The requester confirms and closes it.
    assert flow.do(REQUESTER, cr_id, "close") == Status.CLOSED
    cr = fresh(cr_id)
    assert cr.closed_at is not None
    assert cr.is_open is False

    # Every step is in the history, made by the right person.
    assert history(cr_id) == [
        (None, Status.SUBMITTED),
        (Status.SUBMITTED, Status.UNDER_REVIEW),
        (Status.UNDER_REVIEW, Status.APPROVED),
        (Status.APPROVED, Status.ASSIGNED),
        (Status.ASSIGNED, Status.IN_PROGRESS),
        (Status.IN_PROGRESS, Status.RESOLVED),
        (Status.RESOLVED, Status.CLOSED),
    ]
    actors = [
        row.user_id
        for row in StatusHistory.query.filter_by(change_request_id=cr_id).order_by(StatusHistory.id)
    ]
    req, rev, eng = user(REQUESTER).id, user(REVIEWER).id, user(ENGINEER).id
    assert actors == [req, rev, rev, rev, eng, eng, req]
    assert AssignmentHistory.query.filter_by(change_request_id=cr_id).count() == 1

    # Closed work leaves the engineer's list, and the requester can still read it.
    assert cr_id not in [c.id for c in dashboard_service.assigned_to(user(ENGINEER))]
    detail = flow.get(REQUESTER, f"/change-requests/{cr_id}")
    assert detail.status_code == 200
    page = detail.get_data(as_text=True)
    assert "CR-0011" in page
    assert Status.CLOSED in page


def test_reopen_then_resolve_and_close_again(flow):
    cr_id = flow.to_resolved()

    # A reason is required to reopen.
    assert flow.do(REQUESTER, cr_id, "reopen") == Status.RESOLVED
    assert flow.do(REQUESTER, cr_id, "reopen", reason="Export is empty for last month.") == Status.REOPENED
    reopen_row = StatusHistory.query.filter_by(change_request_id=cr_id, to_status=Status.REOPENED).one()
    assert reopen_row.reason == "Export is empty for last month."

    # It is back on the engineer's list.
    assert cr_id in [c.id for c in dashboard_service.assigned_to(user(ENGINEER))]

    assert flow.do(ENGINEER, cr_id, "start-work") == Status.IN_PROGRESS
    assert flow.do(ENGINEER, cr_id, "resolve", resolution_summary="Fixed the date filter.") == Status.RESOLVED
    assert flow.do(REQUESTER, cr_id, "close") == Status.CLOSED
    assert [to for _from, to in history(cr_id)].count(Status.RESOLVED) == 2


def test_reviewer_can_also_close_a_resolved_request(flow):
    cr_id = flow.to_resolved()
    assert flow.do(REVIEWER, cr_id, "close") == Status.CLOSED


def test_rejected_request_stops_and_cannot_be_assigned(flow):
    cr_id = flow.create()
    assert flow.do(REVIEWER, cr_id, "start-review") == Status.UNDER_REVIEW

    # A reason is required to reject.
    assert flow.do(REVIEWER, cr_id, "reject") == Status.UNDER_REVIEW
    assert flow.do(REVIEWER, cr_id, "reject", reason="Duplicate of CR-0004.") == Status.REJECTED
    assert fresh(cr_id).is_open is False

    flow.assign(REVIEWER, cr_id, ENGINEER)
    cr = fresh(cr_id)
    assert cr.status == Status.REJECTED
    assert cr.assignee is None
    assert AssignmentHistory.query.filter_by(change_request_id=cr_id).count() == 0

    # Not in the requester's open list, not overdue.
    requester = user(REQUESTER)
    assert cr_id not in [c.id for c in dashboard_service.requested_by(requester)]
    assert cr_id not in [c.id for c in dashboard_service.overdue(requester)]


def test_reassign_moves_work_to_the_new_engineer(flow):
    cr_id = flow.create()
    flow.do(REVIEWER, cr_id, "start-review")
    flow.do(REVIEWER, cr_id, "approve")
    flow.assign(REVIEWER, cr_id, ENGINEER)
    assert flow.do(ENGINEER, cr_id, "start-work") == Status.IN_PROGRESS

    flow.assign(REVIEWER, cr_id, OTHER_ENGINEER)
    cr = fresh(cr_id)
    assert cr.assignee.email == OTHER_ENGINEER
    assert cr.status == Status.ASSIGNED  # In Progress -> Assigned for the new engineer

    # Only the new engineer can pick it up now.
    assert flow.do(ENGINEER, cr_id, "start-work") == Status.ASSIGNED
    assert flow.do(OTHER_ENGINEER, cr_id, "start-work") == Status.IN_PROGRESS
    assert AssignmentHistory.query.filter_by(change_request_id=cr_id).count() == 2


# ---------- the wrong person / missing input ----------

def test_only_the_right_people_can_move_a_request(flow):
    cr_id = flow.create()

    # Requesters and engineers cannot review or approve.
    assert flow.do(REQUESTER, cr_id, "start-review") == Status.SUBMITTED
    assert flow.do(ENGINEER, cr_id, "start-review") == Status.SUBMITTED
    flow.do(REVIEWER, cr_id, "start-review")
    assert flow.do(REQUESTER, cr_id, "approve") == Status.UNDER_REVIEW
    flow.do(REVIEWER, cr_id, "approve")
    flow.assign(REVIEWER, cr_id, ENGINEER)

    # Only the assigned engineer can start.
    assert flow.do(OTHER_ENGINEER, cr_id, "start-work") == Status.ASSIGNED
    assert flow.do(REQUESTER, cr_id, "start-work") == Status.ASSIGNED
    assert flow.do(ENGINEER, cr_id, "start-work") == Status.IN_PROGRESS

    # Resolving needs the assignee and a summary.
    assert flow.do(ENGINEER, cr_id, "resolve") == Status.IN_PROGRESS
    assert flow.do(REVIEWER, cr_id, "resolve", resolution_summary="Done.") == Status.IN_PROGRESS
    assert flow.do(ENGINEER, cr_id, "resolve", resolution_summary="Done.") == Status.RESOLVED

    # Engineers and other requesters cannot close.
    assert flow.do(ENGINEER, cr_id, "close") == Status.RESOLVED
    assert flow.do(OTHER_REQUESTER, cr_id, "close") == Status.RESOLVED


def test_steps_cannot_be_skipped(flow):
    cr_id = flow.create()
    assert flow.do(REVIEWER, cr_id, "approve") == Status.SUBMITTED  # must start review first
    assert flow.do(ADMIN, cr_id, "close") == Status.SUBMITTED  # even Admin follows the flow
    flow.assign(REVIEWER, cr_id, ENGINEER)  # not approved yet
    assert fresh(cr_id).assignee is None
    assert history(cr_id) == [(None, Status.SUBMITTED)]


def test_admin_can_run_the_whole_lifecycle(flow):
    cr_id = flow.create(ADMIN)
    for action in ["start-review", "approve"]:
        flow.do(ADMIN, cr_id, action)
    flow.assign(ADMIN, cr_id, ENGINEER)
    flow.do(ADMIN, cr_id, "start-work")
    flow.do(ADMIN, cr_id, "resolve", resolution_summary="Done by admin.")
    assert flow.do(ADMIN, cr_id, "close") == Status.CLOSED


# ---------- access control over HTTP ----------

def test_pages_require_sign_in(flow):
    cr_id = flow.create()
    flow.sign_out()
    for path in ["/", "/change-requests", "/change-requests/new", f"/change-requests/{cr_id}"]:
        response = flow.client.get(path)
        assert response.status_code == 302, path
        assert "/login" in response.headers["Location"]


def test_requesters_only_see_their_own_requests(flow):
    cr_id = flow.create(REQUESTER)
    assert flow.get(OTHER_REQUESTER, f"/change-requests/{cr_id}").status_code == 403
    listing = flow.get(OTHER_REQUESTER, "/change-requests").get_data(as_text=True)
    assert NEW_CR["title"] not in listing
    assert flow.get(REVIEWER, f"/change-requests/{cr_id}").status_code == 200
    assert flow.get(ENGINEER, f"/change-requests/{cr_id}").status_code == 200


@pytest.mark.parametrize("email", [REQUESTER, ENGINEER])
def test_non_reviewers_get_403_when_assigning(flow, email):
    cr_id = flow.create()
    flow.do(REVIEWER, cr_id, "start-review")
    flow.do(REVIEWER, cr_id, "approve")
    assert flow.assign(email, cr_id, ENGINEER).status_code == 403
    cr = fresh(cr_id)
    assert cr.status == Status.APPROVED
    assert cr.assignee is None


def test_invalid_form_creates_nothing(flow):
    flow.sign_in(REQUESTER)
    response = flow.client.post("/change-requests/new", data={**NEW_CR, "title": "", "priority": "Urgent"})
    assert response.status_code == 400
    assert ChangeRequest.query.count() == 10
    assert StatusHistory.query.filter(StatusHistory.from_status.is_(None)).count() == 0


# ---------- dashboard stays in step with the lifecycle ----------

def test_dashboard_numbers_follow_the_lifecycle(flow):
    admin = user(ADMIN)
    before = dashboard_service.build_dashboard(admin)
    assert (before["total"], before["open_total"]) == (10, 8)

    cr_id = flow.to_resolved()
    during = dashboard_service.build_dashboard(admin)
    assert (during["total"], during["open_total"]) == (11, 9)

    flow.do(REQUESTER, cr_id, "close")
    after = dashboard_service.build_dashboard(admin)
    assert (after["total"], after["open_total"]) == (11, 8)
    assert dashboard_service.status_counts(admin)[Status.CLOSED] == 2


# ---------- Test Plan system cases ----------

def test_script_text_is_shown_as_plain_text(flow):
    """TC-VAL-02 / CMS-SR-004."""
    payload = "<script>alert('x')</script>"
    cr_id = flow.create(description=f"Steps: {payload}")
    assert payload in fresh(cr_id).description  # stored as typed
    page = flow.get(REVIEWER, f"/change-requests/{cr_id}").get_data(as_text=True)
    assert payload not in page  # never sent back as live HTML
    assert "&lt;script&gt;" in page


def test_full_lifecycle_with_reassignment_has_complete_history(flow):
    """TC-HIST-01 / CMS-F-013: every status and assignment change, in order, with the actor."""
    cr_id = flow.create()
    flow.do(REVIEWER, cr_id, "start-review")
    flow.do(REVIEWER, cr_id, "approve")
    flow.assign(REVIEWER, cr_id, ENGINEER)
    flow.assign(REVIEWER, cr_id, OTHER_ENGINEER)
    flow.do(OTHER_ENGINEER, cr_id, "start-work")
    flow.do(OTHER_ENGINEER, cr_id, "resolve", resolution_summary="Done.")
    flow.do(REQUESTER, cr_id, "close")

    assert [to for _from, to in history(cr_id)] == [
        Status.SUBMITTED, Status.UNDER_REVIEW, Status.APPROVED, Status.ASSIGNED,
        Status.IN_PROGRESS, Status.RESOLVED, Status.CLOSED,
    ]
    moves = (
        AssignmentHistory.query.filter_by(change_request_id=cr_id)
        .order_by(AssignmentHistory.id)
        .all()
    )
    eng, other, rev = user(ENGINEER).id, user(OTHER_ENGINEER).id, user(REVIEWER).id
    assert [(m.from_user_id, m.to_user_id, m.assigned_by_id) for m in moves] == [
        (None, eng, rev),
        (eng, other, rev),
    ]
    rows = StatusHistory.query.filter_by(change_request_id=cr_id).all() + moves
    assert all(row.created_at is not None for row in rows)


def test_data_survives_an_application_restart(tmp_path):
    """TC-RESTART-01 / CMS-NF-002: committed requests and history are still there."""
    from cms import create_app
    from cms.config import TestConfig
    from cms.seed import seed_demo_data
    from cms.services import change_request_service

    class FileConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'cms.db').as_posix()}"

    first = create_app(FileConfig)
    with first.app_context():
        seed_demo_data()
        cr = change_request_service.create(dict(NEW_CR), user(REQUESTER))
        workflow_service.transition(cr, Status.UNDER_REVIEW, user(REVIEWER))
        cr_id = cr.id
        db.session.remove()
        db.engine.dispose()

    second = create_app(FileConfig)
    with second.app_context():
        cr = db.session.get(ChangeRequest, cr_id)
        assert cr.title == NEW_CR["title"]
        assert cr.status == Status.UNDER_REVIEW
        assert history(cr_id) == [(None, Status.SUBMITTED), (Status.SUBMITTED, Status.UNDER_REVIEW)]
        assert ChangeRequest.query.count() == 11
        db.session.remove()
        db.engine.dispose()
