"""CMS-13: due dates come from priority and drive the overdue list."""

from datetime import date, datetime, timedelta, timezone

import pytest

from cms.constants import COMPONENTS, CRType, Priority, Status
from cms.extensions import db
from cms.models import User
from cms.services.change_request_service import create, due_date_for, search, set_priority
from cms.services.dashboard_service import overdue


def requester():
    return User.query.filter_by(email="requester@cms.local").one()


def data(priority):
    return {
        "title": "Patch the login page",
        "description": "Fix the wrong error message.",
        "cr_type": CRType.BUG_FIX,
        "priority": priority,
        "component": COMPONENTS[0],
    }


@pytest.mark.parametrize(
    ("priority", "days"),
    [(Priority.CRITICAL, 1), (Priority.HIGH, 3), (Priority.MEDIUM, 5), (Priority.LOW, 10)],
)
def test_create_sets_due_date_from_priority(seeded, priority, days):
    cr = create(data(priority), requester())

    assert cr.due_date == date.today() + timedelta(days=days)


def test_due_date_for_uses_given_start_day(app):
    assert due_date_for(Priority.HIGH, date(2026, 1, 1)) == date(2026, 1, 4)


def test_priority_change_recalculates_from_creation_day(seeded):
    cr = create(data(Priority.LOW), requester())
    cr.created_at = datetime(2026, 1, 10, 9, 0, tzinfo=timezone.utc)

    set_priority(cr, Priority.CRITICAL)

    assert cr.priority == Priority.CRITICAL
    assert cr.due_date == date(2026, 1, 11)


def test_same_priority_keeps_existing_due_date(seeded):
    cr = create(data(Priority.MEDIUM), requester())
    cr.due_date = date(2030, 5, 5)

    set_priority(cr, Priority.MEDIUM)

    assert cr.due_date == date(2030, 5, 5)


def test_new_request_becomes_overdue_after_its_due_date(seeded):
    cr = create(data(Priority.CRITICAL), requester())
    admin = User.query.filter_by(email="admin@cms.local").one()

    assert cr not in overdue(admin, date.today())
    assert cr in overdue(admin, date.today() + timedelta(days=2))


def test_resolved_request_is_not_overdue(seeded):
    cr = create(data(Priority.CRITICAL), requester())
    cr.status = Status.RESOLVED
    db.session.commit()
    admin = User.query.filter_by(email="admin@cms.local").one()

    assert cr not in overdue(admin, date.today() + timedelta(days=30))


def test_sla_days_come_from_settings(seeded):
    seeded.config["SLA_DAYS"] = {**seeded.config["SLA_DAYS"], Priority.LOW: 30}

    cr = create(data(Priority.LOW), requester())

    assert cr.due_date == date.today() + timedelta(days=30)


@pytest.mark.parametrize(("offset", "expected"), [(-1, True), (0, False), (1, False)])
def test_overdue_boundaries(seeded, offset, expected):
    """Due yesterday is overdue; due today or tomorrow is not."""
    cr = create(data(Priority.HIGH), requester())
    cr.due_date = date.today() + timedelta(days=offset)
    db.session.commit()

    assert cr.is_overdue is expected


@pytest.mark.parametrize("status", [Status.RESOLVED, Status.CLOSED, Status.REJECTED])
def test_finished_requests_are_never_overdue(seeded, status):
    cr = create(data(Priority.HIGH), requester())
    cr.due_date = date.today() - timedelta(days=5)
    cr.status = status

    assert not cr.is_overdue


def test_request_without_due_date_is_not_overdue(seeded):
    cr = create(data(Priority.HIGH), requester())
    cr.due_date = None

    assert not cr.is_overdue


def test_search_overdue_filter_matches_is_overdue(seeded):
    reviewer = User.query.filter_by(email="reviewer@cms.local").one()

    results = search(reviewer, overdue=True)

    assert results
    assert all(cr.is_overdue for cr in results)
    assert {cr.id for cr in results} == {cr.id for cr in overdue(reviewer)}


def test_list_page_overdue_filter(seeded, client, login):
    late = create(data(Priority.HIGH), requester())
    late.title = "Late request"
    late.due_date = date.today() - timedelta(days=1)
    on_time = create(data(Priority.HIGH), requester())
    on_time.title = "On time request"
    db.session.commit()
    login("reviewer@cms.local")

    body = client.get("/change-requests?overdue=1").data

    assert b"Late request" in body
    assert b"On time request" not in body
    assert b'name="overdue"' in body


def test_detail_shows_overdue_badge_only_when_overdue(seeded, client, login):
    cr = create(data(Priority.HIGH), requester())
    login("reviewer@cms.local")
    assert b'data-test="overdue-badge"' not in client.get(f"/change-requests/{cr.id}").data

    cr.due_date = date.today() - timedelta(days=1)
    db.session.commit()
    assert b'data-test="overdue-badge"' in client.get(f"/change-requests/{cr.id}").data
