"""Demo data so every team member can work and test without waiting for others.

Run with:  flask --app cms seed

All demo accounts use the password DEMO_PASSWORD. They are for local
development only and must never be used in a real deployment.
"""

from datetime import datetime, timezone

from cms.constants import CRType, Priority, Role, Status
from cms.extensions import db
from cms.models import ChangeRequest, User, format_cr_number

DEMO_PASSWORD = "demo1234"

DEMO_USERS = [
    # (name, email, role, active)
    ("Admin User", "admin@cms.local", Role.ADMIN, True),
    ("Riya Reviewer", "reviewer@cms.local", Role.REVIEWER, True),
    ("Eshan Engineer", "engineer1@cms.local", Role.ENGINEER, True),
    ("Meera Engineer", "engineer2@cms.local", Role.ENGINEER, True),
    ("Old Engineer", "engineer3@cms.local", Role.ENGINEER, False),  # inactive, for CMS-7 tests
    ("Rahul Requester", "requester@cms.local", Role.REQUESTER, True),
    ("Sana Requester", "requester2@cms.local", Role.REQUESTER, True),
]

# (title, type, priority, component, status, requester email, assignee email)
DEMO_CHANGE_REQUESTS = [
    ("Login page shows wrong error message", CRType.BUG_FIX, Priority.HIGH,
     "Web application", Status.SUBMITTED, "requester@cms.local", None),
    ("Add dark mode to the dashboard", CRType.ENHANCEMENT, Priority.LOW,
     "Web application", Status.UNDER_REVIEW, "requester2@cms.local", None),
    ("Increase database connection pool size", CRType.CONFIGURATION, Priority.MEDIUM,
     "Database", Status.APPROVED, "requester@cms.local", None),
    ("Export report as CSV", CRType.ENHANCEMENT, Priority.MEDIUM,
     "Backend API", Status.APPROVED, "requester2@cms.local", None),
    ("Fix crash when profile photo is missing", CRType.BUG_FIX, Priority.CRITICAL,
     "Mobile application", Status.APPROVED, "requester@cms.local", None),
    ("Rotate expired TLS certificate", CRType.CONFIGURATION, Priority.CRITICAL,
     "Infrastructure", Status.ASSIGNED, "requester@cms.local", "engineer1@cms.local"),
    ("Update API rate limits", CRType.CONFIGURATION, Priority.HIGH,
     "Backend API", Status.IN_PROGRESS, "requester2@cms.local", "engineer2@cms.local"),
    ("Correct typo in user guide", CRType.OTHER, Priority.LOW,
     "Documentation", Status.RESOLVED, "requester@cms.local", "engineer1@cms.local"),
    ("Upgrade logging library", CRType.ENHANCEMENT, Priority.MEDIUM,
     "Backend API", Status.CLOSED, "requester2@cms.local", "engineer2@cms.local"),
    ("Change company logo colour", CRType.OTHER, Priority.LOW,
     "Web application", Status.REJECTED, "requester@cms.local", None),
]


def seed_demo_data() -> dict:
    """Insert demo users and change requests. Safe to run more than once."""
    users_added = 0
    for name, email, role, active in DEMO_USERS:
        if User.query.filter_by(email=email).first() is None:
            user = User(name=name, email=email, role=role, active=active)
            user.set_password(DEMO_PASSWORD)
            db.session.add(user)
            users_added += 1
    db.session.flush()

    crs_added = 0
    if ChangeRequest.query.count() == 0:
        users = {u.email: u for u in User.query.all()}
        for index, (title, cr_type, priority, component, status, req, eng) in enumerate(
            DEMO_CHANGE_REQUESTS, start=1
        ):
            cr = ChangeRequest(
                cr_number=format_cr_number(index),
                title=title,
                description=f"Demo change request: {title.lower()}.",
                cr_type=cr_type,
                priority=priority,
                component=component,
                status=status,
                requester=users[req],
                assignee=users[eng] if eng else None,
            )
            if status == Status.RESOLVED:
                cr.resolution_summary = "Fixed and verified on the test environment."
            if status == Status.CLOSED:
                cr.resolution_summary = "Upgraded and deployed."
                cr.closed_at = datetime.now(timezone.utc)
            db.session.add(cr)
            crs_added += 1

    db.session.commit()
    return {"users_added": users_added, "change_requests_added": crs_added}
