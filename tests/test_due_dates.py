"""CMS-13: due dates come from priority and drive the overdue list."""

from datetime import date, datetime, timedelta, timezone

import pytest

from cms.constants import COMPONENTS, CRType, Priority, Status
from cms.extensions import db
from cms.models import User
from cms.services.change_request_service import create, due_date_for, set_priority
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
    [(Priority.CRITICAL, 1), (Priority.HIGH, 3), (Priority.MEDIUM, 7), (Priority.LOW, 14)],
)
def test_create_sets_due_date_from_priority(seeded, priority, days):
    cr = create(data(priority), requester())

    assert cr.due_date == date.today() + timedelta(days=days)


def test_due_date_for_uses_given_start_day():
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
