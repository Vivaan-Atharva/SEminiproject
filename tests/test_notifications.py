"""CMS-14: in-app notifications for new requests, assignments, status changes and comments."""

from cms.constants import COMPONENTS, CRType, Priority, Status
from cms.extensions import db
from cms.models import ChangeRequest, Notification, User
from cms.services import assignment_service, notification_service, workflow_service
from cms.services.change_request_service import create


def user(email):
    return User.query.filter_by(email=email).one()


def notes(email, cr=None):
    query = Notification.query.filter_by(user_id=user(email).id)
    if cr is not None:
        query = query.filter_by(change_request_id=cr.id)
    return query.order_by(Notification.id).all()


def new_cr(email="requester@cms.local"):
    return create(
        {
            "title": "Notify me",
            "description": "Something to track.",
            "cr_type": CRType.BUG_FIX,
            "priority": Priority.HIGH,
            "component": COMPONENTS[0],
        },
        user(email),
    )


def approved_cr():
    cr = new_cr()
    reviewer = user("reviewer@cms.local")
    workflow_service.transition(cr, Status.UNDER_REVIEW, reviewer)
    workflow_service.transition(cr, Status.APPROVED, reviewer)
    return cr


# ---------- who gets told what ----------

def test_new_request_notifies_active_reviewers_only(seeded):
    cr = new_cr()
    [note] = notes("reviewer@cms.local", cr)
    assert note.kind == Notification.NEW
    assert cr.cr_number in note.message and "waiting for review" in note.message
    assert notes("requester@cms.local", cr) == []  # not about your own action
    assert notes("engineer1@cms.local", cr) == []


def test_assigning_notifies_engineer_and_requester(seeded):
    cr = approved_cr()
    assignment_service.assign(cr, user("engineer1@cms.local"), user("reviewer@cms.local"))

    [to_engineer] = notes("engineer1@cms.local", cr)
    assert to_engineer.kind == Notification.ASSIGNED
    assert "assigned to you" in to_engineer.message
    assigned_to_requester = [n for n in notes("requester@cms.local", cr) if n.kind == Notification.ASSIGNED]
    assert len(assigned_to_requester) == 1
    assert "Eshan Engineer" in assigned_to_requester[0].message
    # The move to Assigned is announced once, not again as a status change.
    assert [n.kind for n in notes("requester@cms.local", cr)].count(Notification.STATUS) == 2  # review, approve


def test_reassigning_tells_both_engineers(seeded):
    cr = approved_cr()
    reviewer = user("reviewer@cms.local")
    assignment_service.assign(cr, user("engineer1@cms.local"), reviewer)
    assignment_service.assign(cr, user("engineer2@cms.local"), reviewer)

    assert "reassigned to Meera Engineer" in notes("engineer1@cms.local", cr)[-1].message
    assert "assigned to you" in notes("engineer2@cms.local", cr)[-1].message


def test_status_changes_notify_requester_and_assignee_but_not_the_actor(seeded):
    cr = approved_cr()
    engineer = user("engineer1@cms.local")
    assignment_service.assign(cr, engineer, user("reviewer@cms.local"))
    before_engineer = len(notes("engineer1@cms.local", cr))

    workflow_service.transition(cr, Status.IN_PROGRESS, engineer)
    assert len(notes("engineer1@cms.local", cr)) == before_engineer  # own action
    latest = notes("requester@cms.local", cr)[-1]
    assert latest.kind == Notification.STATUS
    assert "from Assigned to In Progress" in latest.message

    workflow_service.transition(cr, Status.RESOLVED, engineer, resolution_summary="Fixed.")
    workflow_service.transition(cr, Status.REOPENED, user("requester@cms.local"), reason="Still broken on Safari")
    reopened = notes("engineer1@cms.local", cr)[-1]
    assert "to Reopened" in reopened.message and "Still broken on Safari" in reopened.message


def test_failed_transition_leaves_no_notification(seeded):
    cr = new_cr()
    count = Notification.query.count()
    try:
        workflow_service.transition(cr, Status.REJECTED, user("reviewer@cms.local"))  # not allowed from Submitted
    except workflow_service.WorkflowError:
        pass
    assert Notification.query.count() == count


def test_comment_hook_for_cms10(seeded):
    cr = approved_cr()
    engineer = user("engineer1@cms.local")
    assignment_service.assign(cr, engineer, user("reviewer@cms.local"))

    created = notification_service.comment_added(cr, engineer)
    db.session.commit()
    assert [n.user.email for n in created] == ["requester@cms.local"]  # author is skipped
    assert created[0].kind == Notification.COMMENT
    assert "Eshan Engineer commented on" in created[0].message


def test_same_person_as_requester_and_assignee_is_told_once(seeded):
    cr = new_cr()
    cr.assignee = cr.requester  # unusual, but must not double-notify
    created = notification_service.status_changed(cr, Status.SUBMITTED, Status.UNDER_REVIEW, user("reviewer@cms.local"))
    assert len(created) == 1


# ---------- unread count, list and read state ----------

def test_unread_count_and_mark_all_read(seeded):
    new_cr()
    new_cr()
    reviewer = user("reviewer@cms.local")
    assert notification_service.unread_count(reviewer) == 2
    assert notification_service.mark_all_read(reviewer) == 2
    assert notification_service.unread_count(reviewer) == 0


def test_list_shows_unread_first(seeded):
    first, second = new_cr(), new_cr()
    reviewer = user("reviewer@cms.local")
    newest_note = notes("reviewer@cms.local", second)[0]
    newest_note.read = True
    db.session.commit()
    ordered = notification_service.for_user(reviewer)
    assert [n.change_request_id for n in ordered] == [first.id, second.id]


def test_bell_shows_unread_count(seeded, client, login):
    new_cr()
    login("reviewer@cms.local")
    page = client.get("/").get_data(as_text=True)
    assert 'data-test="notification-count">1<' in page


def test_no_badge_when_nothing_unread(seeded, client, login):
    login("engineer2@cms.local")
    page = client.get("/").get_data(as_text=True)
    assert 'href="/notifications' in page
    assert 'data-test="notification-count"' not in page


def test_notifications_page_lists_only_my_notifications(seeded, client, login):
    cr = new_cr()
    login("reviewer@cms.local")
    page = client.get("/notifications").get_data(as_text=True)
    assert cr.cr_number in page
    assert 'data-test="notification-unread"' in page

    client.post("/logout")
    login("engineer1@cms.local")
    page = client.get("/notifications").get_data(as_text=True)
    assert 'data-test="notifications-empty"' in page


def test_opening_a_notification_marks_it_read_and_goes_to_the_request(seeded, client, login):
    cr = new_cr()
    note = notes("reviewer@cms.local", cr)[0]
    login("reviewer@cms.local")
    response = client.post(f"/notifications/{note.id}/open")
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/change-requests/{cr.id}")
    db.session.expire_all()
    assert db.session.get(Notification, note.id).read is True


def test_cannot_open_someone_elses_notification(seeded, client, login):
    cr = new_cr()
    note = notes("reviewer@cms.local", cr)[0]
    login("engineer1@cms.local")
    assert client.post(f"/notifications/{note.id}/open").status_code == 404
    db.session.expire_all()
    assert db.session.get(Notification, note.id).read is False


def test_read_all_button(seeded, client, login):
    new_cr()
    login("reviewer@cms.local")
    response = client.post("/notifications/read-all", follow_redirects=True)
    assert "Marked 1 notification as read." in response.get_data(as_text=True)
    assert notification_service.unread_count(user("reviewer@cms.local")) == 0


def test_notifications_page_requires_login(client):
    response = client.get("/notifications")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# ---------- end to end through the real pages ----------

def test_engineer_sees_assignment_in_the_bell(seeded, client, login):
    cr = approved_cr()
    login("reviewer@cms.local")
    client.post(f"/change-requests/{cr.id}/assign", data={"assignee_id": str(user("engineer1@cms.local").id)})
    client.post("/logout")
    login("engineer1@cms.local")
    page = client.get("/").get_data(as_text=True)
    assert 'data-test="notification-count">1<' in page
    listing = client.get("/notifications").get_data(as_text=True)
    assert "assigned to you" in listing
    assert db.session.get(ChangeRequest, cr.id).assignee.email == "engineer1@cms.local"
