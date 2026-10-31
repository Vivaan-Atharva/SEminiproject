"""CMS-12: home dashboard with counts, work lists and overdue items."""

from datetime import date, timedelta

import pytest

from cms.constants import CRType, Priority, Role, Status
from cms.extensions import db
from cms.models import ChangeRequest, User, format_cr_number
from cms.services import dashboard_service as ds


def user(email):
    return User.query.filter_by(email=email).one()


# ---------- service: counts ----------

def test_status_counts_match_database_for_staff(seeded):
    counts = ds.status_counts(user("reviewer@cms.local"))
    assert sum(counts.values()) == ChangeRequest.query.count() == 10
    for status, count in counts.items():
        assert count == ChangeRequest.query.filter_by(status=status).count()


def test_requester_counts_only_include_own_requests(seeded):
    requester = user("requester@cms.local")
    counts = ds.status_counts(requester)
    own = ChangeRequest.query.filter_by(requester_id=requester.id).count()
    assert sum(counts.values()) == own == 6


def test_priority_counts_exclude_closed_and_rejected(seeded):
    counts = ds.open_priority_counts(user("admin@cms.local"))
    assert counts == {
        Priority.CRITICAL: 2,
        Priority.HIGH: 2,
        Priority.MEDIUM: 2,
        Priority.LOW: 2,
    }


def test_build_dashboard_totals(seeded):
    dash = ds.build_dashboard(user("admin@cms.local"))
    assert dash["total"] == 10
    assert dash["open_total"] == 8  # everything except Closed and Rejected


# ---------- service: work lists per role ----------

def section_titles(dash):
    return [title for title, _items, _test_id in dash["sections"]]


def test_engineer_sees_only_their_active_work(seeded):
    engineer = user("engineer1@cms.local")
    items = ds.assigned_to(engineer)
    assert [cr.cr_number for cr in items] == ["CR-0006"]  # CR-0008 is Resolved, so not listed
    assert section_titles(ds.build_dashboard(engineer)) == ["Assigned to me"]


def test_requester_sees_own_open_requests(seeded):
    requester = user("requester@cms.local")
    numbers = {cr.cr_number for cr in ds.requested_by(requester)}
    assert numbers == {"CR-0001", "CR-0003", "CR-0005", "CR-0006", "CR-0008"}
    assert section_titles(ds.build_dashboard(requester)) == ["My open requests"]


def test_reviewer_sees_review_and_assignment_queues(seeded):
    reviewer = user("reviewer@cms.local")
    assert [cr.cr_number for cr in ds.awaiting_review()] == ["CR-0001", "CR-0002"]
    assert [cr.cr_number for cr in ds.awaiting_assignment()] == ["CR-0003", "CR-0004", "CR-0005"]
    assert section_titles(ds.build_dashboard(reviewer)) == [
        "Waiting for review",
        "Approved, waiting for an engineer",
    ]


def test_admin_gets_reviewer_sections(seeded):
    assert len(ds.build_dashboard(user("admin@cms.local"))["sections"]) == 2


# ---------- service: overdue ----------

@pytest.fixture
def overdue_cases(app):
    """One CR for each due-date boundary, all owned by one requester."""
    requester = User(name="Req", email="req@cms.local", role=Role.REQUESTER)
    requester.set_password("x")
    db.session.add(requester)
    today = date(2026, 11, 4)
    cases = [
        ("yesterday", today - timedelta(days=1), Status.IN_PROGRESS),
        ("today", today, Status.IN_PROGRESS),
        ("tomorrow", today + timedelta(days=1), Status.IN_PROGRESS),
        ("no-due-date", None, Status.SUBMITTED),
        ("resolved-late", today - timedelta(days=5), Status.RESOLVED),
        ("closed-late", today - timedelta(days=5), Status.CLOSED),
        ("rejected-late", today - timedelta(days=5), Status.REJECTED),
        ("reopened-late", today - timedelta(days=2), Status.REOPENED),
    ]
    for i, (title, due, status) in enumerate(cases, start=1):
        db.session.add(
            ChangeRequest(
                cr_number=format_cr_number(i),
                title=title,
                description="boundary case",
                cr_type=CRType.BUG_FIX,
                priority=Priority.HIGH,
                component="Backend API",
                status=status,
                requester=requester,
                due_date=due,
            )
        )
    db.session.commit()
    return requester, today


def test_overdue_boundaries(overdue_cases):
    requester, today = overdue_cases
    titles = [cr.title for cr in ds.overdue(requester, today=today)]
    # Oldest due date first; due today is not yet overdue; finished requests never are.
    assert titles == ["reopened-late", "yesterday"]


def test_seeded_overdue_items(seeded):
    numbers = [cr.cr_number for cr in ds.overdue(user("admin@cms.local"))]
    assert numbers == ["CR-0006", "CR-0005"]  # CR-0008 is past due but Resolved


def test_requester_only_sees_own_overdue(seeded):
    assert len(ds.overdue(user("requester@cms.local"))) == 2
    assert ds.overdue(user("requester2@cms.local")) == []


# ---------- page ----------

def test_dashboard_requires_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_dashboard_page_for_reviewer(seeded, client, login):
    login("reviewer@cms.local")
    page = client.get("/").get_data(as_text=True)
    assert 'data-test="cr-count">10<' in page
    assert 'data-test="overdue-count">2<' in page
    assert 'data-test="review-count">' in page
    assert "Waiting for review" in page
    assert "Approved, waiting for an engineer" in page
    assert 'data-test="status-approved">3<' in page


def test_dashboard_page_for_requester_shows_own_numbers(seeded, client, login):
    login("requester2@cms.local")
    page = client.get("/").get_data(as_text=True)
    assert 'data-test="cr-count">4<' in page
    assert "My open requests" in page
    assert "Showing your change requests" in page
    assert 'data-test="overdue-empty"' in page


def test_dashboard_page_for_engineer(seeded, client, login):
    login("engineer1@cms.local")
    page = client.get("/").get_data(as_text=True)
    assert "Assigned to me" in page
    assert "Rotate expired TLS certificate" in page


def test_statuses_and_priorities_have_text_labels(seeded, client, login):
    login("admin@cms.local")
    page = client.get("/").get_data(as_text=True)
    for label in Status.ALL + Priority.ALL:
        assert f">{label}</span>" in page


def test_cr_numbers_are_plain_text_until_detail_page_exists(seeded, client, login):
    login("admin@cms.local")
    page = client.get("/").get_data(as_text=True)
    assert "CR-0006" in page
    assert 'href="/change-requests/6"' not in page


def test_cr_numbers_link_to_detail_page_once_it_exists(app, seeded, client, login):
    def detail(cr_id):
        return f"detail {cr_id}"

    app.add_url_rule(
        "/change-requests/<int:cr_id>",
        endpoint="change_requests.detail",
        view_func=detail,
    )
    login("admin@cms.local")
    page = client.get("/").get_data(as_text=True)
    cr = ChangeRequest.query.filter_by(cr_number="CR-0006").one()
    assert f'href="/change-requests/{cr.id}">CR-0006</a>' in page
