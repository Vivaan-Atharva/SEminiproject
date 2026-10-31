"""CMS-5: the status-flow engine and the status history."""

import pytest

from cms.constants import COMPONENTS, CRType, Priority, Status
from cms.extensions import db
from cms.models import ChangeRequest, StatusHistory, User
from cms.services import workflow_service
from cms.services.change_request_service import create
from cms.services.workflow_service import (
    TRANSITIONS,
    MissingInput,
    PermissionDenied,
    TransitionNotAllowed,
    WorkflowError,
    allowed_next,
    record_initial_status,
    transition,
)

ADMIN_EMAIL = "admin@cms.local"
REVIEWER_EMAIL = "reviewer@cms.local"
ENGINEER1_EMAIL = "engineer1@cms.local"
ENGINEER2_EMAIL = "engineer2@cms.local"
REQUESTER_EMAIL = "requester@cms.local"
REQUESTER2_EMAIL = "requester2@cms.local"

# Seeded change requests used below (see cms/seed.py):
#   CR-0001 Submitted, requester          CR-0002 Under Review, requester2
#   CR-0003 Approved, no assignee         CR-0006 Assigned to engineer1, requester
#   CR-0007 In Progress, engineer2        CR-0008 Resolved, engineer1, requester
#   CR-0009 Closed                        CR-0010 Rejected


def get_cr(number):
    return ChangeRequest.query.filter_by(cr_number=number).one()


def get_user(email):
    return User.query.filter_by(email=email).one()


def prepare(cr, changes):
    """Put a seeded change request into the state a test needs.

    ``changes`` may hold "status" and/or "assignee" (an email, or None for nobody).
    """
    if "status" in changes:
        cr.status = changes["status"]
    if "assignee" in changes:
        email = changes["assignee"]
        cr.assignee = get_user(email) if email else None
    db.session.commit()


def snapshot(cr):
    return (cr.status, cr.resolution_summary, cr.closed_at, cr.assignee_id)


def move_id(from_status, to_status):
    return f"{from_status} -> {to_status}"


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


# --- every allowed transition ---------------------------------------------

# (cr number, from, to, who, changes to prepare, inputs for transition())
ALLOWED = [
    ("CR-0001", Status.SUBMITTED, Status.UNDER_REVIEW, REVIEWER_EMAIL, {}, {}),
    ("CR-0002", Status.UNDER_REVIEW, Status.APPROVED, REVIEWER_EMAIL, {}, {}),
    ("CR-0002", Status.UNDER_REVIEW, Status.REJECTED, REVIEWER_EMAIL, {},
     {"reason": "Out of scope for this release."}),
    # The assign service sets the assignee first, then asks for the move.
    ("CR-0003", Status.APPROVED, Status.ASSIGNED, REVIEWER_EMAIL,
     {"assignee": ENGINEER1_EMAIL}, {}),
    ("CR-0007", Status.IN_PROGRESS, Status.ASSIGNED, REVIEWER_EMAIL,
     {"assignee": ENGINEER1_EMAIL}, {}),
    ("CR-0006", Status.ASSIGNED, Status.IN_PROGRESS, ENGINEER1_EMAIL, {}, {}),
    ("CR-0007", Status.IN_PROGRESS, Status.RESOLVED, ENGINEER2_EMAIL, {},
     {"resolution_summary": "Raised the limits and verified."}),
    ("CR-0008", Status.RESOLVED, Status.CLOSED, REQUESTER_EMAIL, {}, {}),
    ("CR-0008", Status.RESOLVED, Status.CLOSED, REVIEWER_EMAIL, {}, {}),
    ("CR-0008", Status.RESOLVED, Status.REOPENED, REQUESTER_EMAIL, {},
     {"reason": "The typo is still there."}),
    ("CR-0008", Status.RESOLVED, Status.REOPENED, REVIEWER_EMAIL, {},
     {"reason": "Needs another look."}),
    ("CR-0008", Status.REOPENED, Status.IN_PROGRESS, ENGINEER1_EMAIL,
     {"status": Status.REOPENED}, {}),
]


def test_allowed_scenarios_cover_every_row_of_the_transition_table():
    assert {(row[1], row[2]) for row in ALLOWED} == set(TRANSITIONS)


@pytest.mark.parametrize(
    ("number", "from_status", "to_status", "actor", "changes", "inputs"),
    ALLOWED,
    ids=[f"{move_id(row[1], row[2])} by {row[3].split('@')[0]}" for row in ALLOWED],
)
def test_allowed_transition_succeeds_and_writes_one_history_row(
    seeded, number, from_status, to_status, actor, changes, inputs
):
    cr = get_cr(number)
    prepare(cr, changes)
    assert cr.status == from_status
    user = get_user(actor)

    entry = transition(cr, to_status, user, **inputs)

    assert cr.status == to_status
    assert StatusHistory.query.count() == 1
    assert len(cr.status_history) == 1
    assert entry.id == cr.status_history[0].id
    assert (entry.from_status, entry.to_status) == (from_status, to_status)
    assert entry.user.email == actor


def test_rejecting_stores_the_trimmed_reason_in_the_history(seeded):
    cr = get_cr("CR-0002")

    entry = transition(cr, Status.REJECTED, get_user(REVIEWER_EMAIL), reason="  Duplicate of CR-0001.  ")

    assert entry.reason == "Duplicate of CR-0001."
    assert cr.status_history[0].reason == "Duplicate of CR-0001."


def test_move_without_a_reason_stores_none(seeded):
    cr = get_cr("CR-0001")

    entry = transition(cr, Status.UNDER_REVIEW, get_user(REVIEWER_EMAIL))

    assert entry.reason is None


def test_resolving_saves_the_trimmed_summary_on_the_change_request(seeded):
    cr = get_cr("CR-0007")
    assert cr.resolution_summary is None

    transition(
        cr, Status.RESOLVED, get_user(ENGINEER2_EMAIL), resolution_summary="  Raised the pool size.  "
    )

    assert cr.resolution_summary == "Raised the pool size."


def test_closing_sets_closed_at_and_other_moves_do_not(seeded):
    cr = get_cr("CR-0008")
    assert cr.closed_at is None

    transition(cr, Status.REOPENED, get_user(REVIEWER_EMAIL), reason="Needs another look.")
    assert cr.closed_at is None

    prepare(cr, {"status": Status.RESOLVED})
    transition(cr, Status.CLOSED, get_user(REQUESTER_EMAIL))
    assert cr.closed_at is not None


def test_admin_may_make_every_allowed_move(seeded):
    cr = get_cr("CR-0006")  # has an assignee, so the "assignee set" rule is met
    admin = get_user(ADMIN_EMAIL)

    for count, (from_status, to_status) in enumerate(TRANSITIONS, start=1):
        prepare(cr, {"status": from_status})

        transition(cr, to_status, admin, reason="Admin override.", resolution_summary="Done by admin.")

        assert cr.status == to_status, move_id(from_status, to_status)
        assert StatusHistory.query.count() == count, move_id(from_status, to_status)


# --- disallowed transitions -----------------------------------------------

DISALLOWED = [
    ("CR-0001", Status.CLOSED),       # Submitted -> Closed
    ("CR-0001", Status.APPROVED),     # skips the review
    ("CR-0003", Status.IN_PROGRESS),  # Approved -> In Progress skips the assignment
    ("CR-0010", Status.APPROVED),     # Rejected is final
    ("CR-0009", Status.REOPENED),     # Closed is final
    ("CR-0008", Status.IN_PROGRESS),  # Resolved must be reopened first
    ("CR-0006", Status.RESOLVED),     # Assigned -> Resolved skips "start work"
    ("CR-0002", Status.UNDER_REVIEW), # to the same status
    ("CR-0001", "Archived"),          # not a status at all
]


@pytest.mark.parametrize(("number", "to_status"), DISALLOWED)
def test_disallowed_move_is_rejected_even_for_admin_and_changes_nothing(seeded, number, to_status):
    cr = get_cr(number)
    before = snapshot(cr)
    from_status = cr.status

    with pytest.raises(TransitionNotAllowed) as raised:
        transition(
            cr, to_status, get_user(ADMIN_EMAIL), reason="Because.", resolution_summary="Because."
        )

    assert from_status in str(raised.value)
    assert to_status in str(raised.value)
    assert snapshot(cr) == before
    assert StatusHistory.query.count() == 0


def test_every_pair_of_statuses_outside_the_table_is_rejected(seeded):
    cr = get_cr("CR-0006")
    admin = get_user(ADMIN_EMAIL)

    for from_status in Status.ALL:
        for to_status in Status.ALL:
            if (from_status, to_status) in TRANSITIONS:
                continue
            prepare(cr, {"status": from_status})

            with pytest.raises(TransitionNotAllowed):
                transition(cr, to_status, admin, reason="x", resolution_summary="x")

            assert cr.status == from_status, move_id(from_status, to_status)

    assert StatusHistory.query.count() == 0


# --- wrong role / wrong person --------------------------------------------


def moves_without(actor):
    """The moves in the table that the given kind of person may NOT make."""
    return [move for move, rule in TRANSITIONS.items() if actor not in rule.who]


# On CR-0006 the assignee is engineer1 and the requester is requester@cms.local.
WRONG_PERSON = (
    # Not the assignee, not the requester, not a reviewer: may make no move at all.
    [(REQUESTER2_EMAIL, move) for move in TRANSITIONS]
    + [(ENGINEER2_EMAIL, move) for move in TRANSITIONS]
    # The right person for some moves must still be refused for the others.
    + [(REVIEWER_EMAIL, move) for move in moves_without(workflow_service.REVIEWER)]
    + [(ENGINEER1_EMAIL, move) for move in moves_without(workflow_service.ASSIGNEE)]
    + [(REQUESTER_EMAIL, move) for move in moves_without(workflow_service.REQUESTER)]
)


def test_wrong_role_or_wrong_person_cannot_make_a_move_and_nothing_changes(seeded):
    cr = get_cr("CR-0006")

    for email, (from_status, to_status) in WRONG_PERSON:
        prepare(cr, {"status": from_status})
        before = snapshot(cr)
        label = f"{email.split('@')[0]}: {move_id(from_status, to_status)}"

        with pytest.raises(PermissionDenied):
            transition(cr, to_status, get_user(email), reason="x", resolution_summary="x")

        assert snapshot(cr) == before, label
        assert StatusHistory.query.count() == 0, label


def test_only_the_assigned_engineer_may_start_or_resolve(seeded):
    started = get_cr("CR-0006")   # Assigned to engineer1
    resolving = get_cr("CR-0007")  # In Progress with engineer2

    with pytest.raises(PermissionDenied):
        transition(started, Status.IN_PROGRESS, get_user(ENGINEER2_EMAIL))
    with pytest.raises(PermissionDenied):
        transition(
            resolving, Status.RESOLVED, get_user(ENGINEER1_EMAIL), resolution_summary="Done."
        )

    assert started.status == Status.ASSIGNED
    assert resolving.status == Status.IN_PROGRESS


def test_permission_is_checked_before_missing_input(seeded):
    cr = get_cr("CR-0007")  # engineer2's change request

    with pytest.raises(PermissionDenied):
        transition(cr, Status.RESOLVED, get_user(ENGINEER1_EMAIL))  # no summary either


def test_a_move_outside_the_table_is_reported_before_permission(seeded):
    cr = get_cr("CR-0001")

    with pytest.raises(TransitionNotAllowed):
        transition(cr, Status.CLOSED, get_user(REQUESTER2_EMAIL))


# --- missing input --------------------------------------------------------

# (cr number, to, who, changes to prepare, inputs, a word the message must contain)
MISSING = [
    ("CR-0002", Status.REJECTED, REVIEWER_EMAIL, {}, {}, "reason"),
    ("CR-0002", Status.REJECTED, REVIEWER_EMAIL, {}, {"reason": "   "}, "reason"),
    ("CR-0008", Status.REOPENED, REQUESTER_EMAIL, {}, {}, "reason"),
    ("CR-0008", Status.REOPENED, REVIEWER_EMAIL, {}, {"reason": ""}, "reason"),
    ("CR-0007", Status.RESOLVED, ENGINEER2_EMAIL, {}, {}, "summary"),
    ("CR-0007", Status.RESOLVED, ENGINEER2_EMAIL, {}, {"resolution_summary": "  "}, "summary"),
    ("CR-0003", Status.ASSIGNED, REVIEWER_EMAIL, {}, {}, "assigned"),  # Approved, nobody assigned
    ("CR-0007", Status.ASSIGNED, REVIEWER_EMAIL, {"assignee": None}, {}, "assigned"),  # reassign
]


@pytest.mark.parametrize(
    ("number", "to_status", "actor", "changes", "inputs", "word"),
    MISSING,
    ids=[f"{row[0]} to {row[1]} by {row[2].split('@')[0]} #{index}" for index, row in enumerate(MISSING)],
)
def test_missing_input_is_refused_and_nothing_changes(
    seeded, number, to_status, actor, changes, inputs, word
):
    cr = get_cr(number)
    prepare(cr, changes)
    before = snapshot(cr)

    with pytest.raises(MissingInput) as raised:
        transition(cr, to_status, get_user(actor), **inputs)

    assert word in str(raised.value)
    assert snapshot(cr) == before
    assert StatusHistory.query.count() == 0


def test_all_errors_are_workflow_errors_with_a_message(seeded):
    for error in (TransitionNotAllowed, PermissionDenied, MissingInput):
        assert issubclass(error, WorkflowError)

    with pytest.raises(WorkflowError) as raised:
        transition(get_cr("CR-0001"), Status.CLOSED, get_user(REVIEWER_EMAIL))
    assert str(raised.value)


# --- allowed_next ---------------------------------------------------------

# (cr number, who, the statuses allowed_next must return, in table order)
ALLOWED_NEXT = [
    ("CR-0001", REVIEWER_EMAIL, [Status.UNDER_REVIEW]),
    ("CR-0001", REQUESTER_EMAIL, []),
    ("CR-0001", ENGINEER1_EMAIL, []),
    ("CR-0002", REVIEWER_EMAIL, [Status.APPROVED, Status.REJECTED]),
    ("CR-0003", REVIEWER_EMAIL, [Status.ASSIGNED]),
    ("CR-0006", ENGINEER1_EMAIL, [Status.IN_PROGRESS]),
    ("CR-0006", ENGINEER2_EMAIL, []),
    ("CR-0006", REVIEWER_EMAIL, []),
    ("CR-0007", ENGINEER2_EMAIL, [Status.RESOLVED]),
    ("CR-0007", REVIEWER_EMAIL, [Status.ASSIGNED]),
    ("CR-0008", REQUESTER_EMAIL, [Status.CLOSED, Status.REOPENED]),
    ("CR-0008", REVIEWER_EMAIL, [Status.CLOSED, Status.REOPENED]),
    ("CR-0008", REQUESTER2_EMAIL, []),  # CR-0008 belongs to requester@, not requester2@
    ("CR-0008", ENGINEER1_EMAIL, []),   # the assignee cannot close their own work
    ("CR-0002", ADMIN_EMAIL, [Status.APPROVED, Status.REJECTED]),
    ("CR-0007", ADMIN_EMAIL, [Status.ASSIGNED, Status.RESOLVED]),
    ("CR-0009", ADMIN_EMAIL, []),  # Closed is final
    ("CR-0010", ADMIN_EMAIL, []),  # Rejected is final
]


def test_allowed_next_for_different_users(seeded):
    for number, email, expected in ALLOWED_NEXT:
        assert allowed_next(get_cr(number), get_user(email)) == expected, f"{number} {email}"


def test_allowed_next_ignores_missing_input_so_buttons_can_be_shown(seeded):
    # CR-0003 has nobody assigned yet; the reviewer still gets the Assign step.
    assert get_cr("CR-0003").assignee is None
    assert allowed_next(get_cr("CR-0003"), get_user(REVIEWER_EMAIL)) == [Status.ASSIGNED]


def test_allowed_next_is_empty_for_a_user_who_is_not_signed_in(seeded):
    from flask_login import AnonymousUserMixin

    assert allowed_next(get_cr("CR-0001"), AnonymousUserMixin()) == []
    assert allowed_next(get_cr("CR-0001"), None) == []


# --- a whole life ---------------------------------------------------------


def test_a_change_request_can_go_from_submitted_to_closed_with_a_full_history(seeded):
    cr = get_cr("CR-0001")  # Submitted, requested by requester@
    reviewer = get_user(REVIEWER_EMAIL)
    engineer = get_user(ENGINEER1_EMAIL)
    requester = get_user(REQUESTER_EMAIL)

    transition(cr, Status.UNDER_REVIEW, reviewer)
    transition(cr, Status.APPROVED, reviewer)
    cr.assignee = engineer  # what the assign service does before asking for the move
    transition(cr, Status.ASSIGNED, reviewer)
    transition(cr, Status.IN_PROGRESS, engineer)
    transition(cr, Status.RESOLVED, engineer, resolution_summary="First fix.")
    transition(cr, Status.REOPENED, requester, reason="Still broken on mobile.")
    transition(cr, Status.IN_PROGRESS, engineer)
    transition(cr, Status.RESOLVED, engineer, resolution_summary="Second fix.")
    transition(cr, Status.CLOSED, requester)

    assert [row.to_status for row in cr.status_history] == [
        Status.UNDER_REVIEW,
        Status.APPROVED,
        Status.ASSIGNED,
        Status.IN_PROGRESS,
        Status.RESOLVED,
        Status.REOPENED,
        Status.IN_PROGRESS,
        Status.RESOLVED,
        Status.CLOSED,
    ]
    assert cr.status_history[5].reason == "Still broken on mobile."
    assert cr.resolution_summary == "Second fix."
    assert cr.closed_at is not None
    assert allowed_next(cr, get_user(ADMIN_EMAIL)) == []


# --- the first history row (connects CMS-3 and CMS-5) ---------------------


def test_new_change_request_has_one_initial_history_row(seeded):
    requester = get_user(REQUESTER_EMAIL)

    cr = create(valid_data(), requester)

    assert len(cr.status_history) == 1
    first = cr.status_history[0]
    assert (first.from_status, first.to_status) == (None, Status.SUBMITTED)
    assert first.user_id == requester.id


def test_creating_through_the_form_writes_the_initial_history_row(seeded, client, login):
    login(REQUESTER_EMAIL)

    client.post("/change-requests/new", data=valid_data())

    cr = get_cr("CR-0011")
    assert [(row.from_status, row.to_status) for row in cr.status_history] == [
        (None, Status.SUBMITTED)
    ]


def test_record_initial_status_does_not_commit(seeded):
    cr = get_cr("CR-0001")

    record_initial_status(cr, get_user(REQUESTER_EMAIL))
    db.session.rollback()

    assert StatusHistory.query.count() == 0
