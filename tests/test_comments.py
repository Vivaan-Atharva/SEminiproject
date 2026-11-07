"""Tests for comments, work notes and the activity timeline (CMS-10)."""

from datetime import datetime

import pytest

from cms.constants import Status
from cms.extensions import db
from cms.models import AssignmentHistory, ChangeRequest, Comment, Notification, StatusHistory, User
from cms.services import assignment_service, comment_service
from cms.services.comment_service import CommentError, CommentPermissionDenied

COMMENTS = "/change-requests/{}/comments"
DETAIL = "/change-requests/{}"


def _cr(number):
    return ChangeRequest.query.filter_by(cr_number=number).one()


def _user(email):
    return User.query.filter_by(email=email).one()


def _notes(email):
    return Notification.query.filter_by(user_id=_user(email).id, kind=Notification.COMMENT).all()


# --- service: adding ---------------------------------------------------------


def test_add_comment_is_saved_trimmed(seeded):
    cr, reviewer = _cr("CR-0006"), _user("reviewer@cms.local")

    comment = comment_service.add_comment(cr, reviewer, "   Please check the staging server too.  ")

    saved = Comment.query.one()
    assert saved.id == comment.id
    assert saved.body == "Please check the staging server too."
    assert saved.author_id == reviewer.id
    assert saved.change_request_id == cr.id
    assert saved.is_work_note is False
    assert saved.created_at is not None
    assert [c.id for c in _cr("CR-0006").comments] == [saved.id]


@pytest.mark.parametrize("body", [None, "", "   ", "\n\t "])
def test_empty_comment_is_refused(seeded, body):
    with pytest.raises(CommentError):
        comment_service.add_comment(_cr("CR-0006"), _user("reviewer@cms.local"), body)
    assert Comment.query.count() == 0
    assert Notification.query.filter_by(kind=Notification.COMMENT).count() == 0


def test_length_limit_is_2000_characters(seeded):
    cr, reviewer = _cr("CR-0006"), _user("reviewer@cms.local")

    comment_service.add_comment(cr, reviewer, "a" * 2000)  # exactly at the limit is fine
    with pytest.raises(CommentError):
        comment_service.add_comment(cr, reviewer, "a" * 2001)

    assert Comment.query.count() == 1


def test_the_limit_counts_the_trimmed_text(seeded):
    comment_service.add_comment(_cr("CR-0006"), _user("reviewer@cms.local"), "  " + "a" * 2000 + "  ")
    assert Comment.query.count() == 1


# --- service: who may comment ------------------------------------------------


def test_requester_comments_on_their_own_cr(seeded):
    comment_service.add_comment(_cr("CR-0006"), _user("requester@cms.local"), "Any update?")
    assert Comment.query.count() == 1


def test_requester_cannot_comment_on_someone_elses_cr(seeded):
    with pytest.raises(CommentPermissionDenied):
        comment_service.add_comment(_cr("CR-0006"), _user("requester2@cms.local"), "Hello")  # not their CR
    assert Comment.query.count() == 0


@pytest.mark.parametrize("email", ["reviewer@cms.local", "engineer2@cms.local", "admin@cms.local"])
def test_staff_comment_on_any_cr(seeded, email):
    comment_service.add_comment(_cr("CR-0006"), _user(email), "Looking at it")
    assert Comment.query.count() == 1


def test_anonymous_cannot_comment(seeded):
    with pytest.raises(CommentPermissionDenied):
        comment_service.add_comment(_cr("CR-0006"), None, "Hello")


# --- service: work notes -----------------------------------------------------


@pytest.mark.parametrize("email", ["engineer1@cms.local", "reviewer@cms.local", "admin@cms.local"])
def test_staff_may_write_work_notes(seeded, email):
    comment = comment_service.add_comment(_cr("CR-0006"), _user(email), "Restarted the service", is_work_note=True)
    assert comment.is_work_note is True
    assert Comment.query.one().is_work_note is True


def test_requester_cannot_write_a_work_note(seeded):
    with pytest.raises(CommentPermissionDenied):
        comment_service.add_comment(_cr("CR-0006"), _user("requester@cms.local"), "secret", is_work_note=True)
    assert Comment.query.count() == 0


# --- service: notifications ----------------------------------------------------


def test_comment_notifies_requester_and_assignee_but_not_the_author(seeded):
    cr = _cr("CR-0006")  # requester@cms.local, assigned to engineer1@cms.local

    comment_service.add_comment(cr, _user("reviewer@cms.local"), "Checking in")

    assert len(_notes("requester@cms.local")) == 1
    assert len(_notes("engineer1@cms.local")) == 1
    assert _notes("reviewer@cms.local") == []
    assert "Riya Reviewer" in _notes("requester@cms.local")[0].message


def test_authors_own_comment_does_not_notify_them(seeded):
    comment_service.add_comment(_cr("CR-0006"), _user("requester@cms.local"), "Any update?")

    assert _notes("requester@cms.local") == []
    assert len(_notes("engineer1@cms.local")) == 1


def test_refused_comment_creates_no_notifications(seeded):
    with pytest.raises(CommentError):
        comment_service.add_comment(_cr("CR-0006"), _user("reviewer@cms.local"), "  ")
    with pytest.raises(CommentPermissionDenied):
        comment_service.add_comment(_cr("CR-0006"), _user("requester2@cms.local"), "Hello")
    assert Notification.query.count() == 0


# --- service: timeline ---------------------------------------------------------


def test_timeline_merges_status_assignment_and_comments_in_time_order(seeded):
    cr = _cr("CR-0001")
    reviewer, engineer = _user("reviewer@cms.local"), _user("engineer1@cms.local")
    # Added out of order on purpose, with explicit times.
    db.session.add(Comment(change_request=cr, author=engineer, body="Third", created_at=datetime(2026, 1, 3, 9)))
    db.session.add(
        StatusHistory(
            change_request=cr, from_status=Status.APPROVED, to_status=Status.ASSIGNED,
            user_id=reviewer.id, created_at=datetime(2026, 1, 2, 9),
        )
    )
    db.session.add(
        AssignmentHistory(
            change_request=cr, from_user_id=None, to_user_id=engineer.id,
            assigned_by_id=reviewer.id, created_at=datetime(2026, 1, 1, 9),
        )
    )
    db.session.commit()

    items = comment_service.timeline(_cr("CR-0001"))

    assert [i.kind for i in items] == ["assignment", "status", "comment"]
    assert [i.when for i in items] == sorted(i.when for i in items)
    assert items[0].who == "Riya Reviewer" and items[0].text == "Assigned to Eshan Engineer"
    assert items[1].who == "Riya Reviewer" and items[1].text == "Approved → Assigned"
    assert (items[1].from_status, items[1].to_status) == (Status.APPROVED, Status.ASSIGNED)
    assert items[2].who == "Eshan Engineer" and items[2].text == "Third"


def test_timeline_marks_work_notes_and_reassignments(seeded):
    cr = _cr("CR-0001")
    reviewer, old, new = _user("reviewer@cms.local"), _user("engineer1@cms.local"), _user("engineer2@cms.local")
    db.session.add(
        Comment(change_request=cr, author=old, body="Note", is_work_note=True, created_at=datetime(2026, 1, 2, 9))
    )
    db.session.add(
        AssignmentHistory(
            change_request=cr, from_user_id=old.id, to_user_id=new.id,
            assigned_by_id=reviewer.id, created_at=datetime(2026, 1, 1, 9),
        )
    )
    db.session.commit()

    items = comment_service.timeline(_cr("CR-0001"))

    assert [i.kind for i in items] == ["assignment", "work note"]
    assert items[0].text == "Reassigned from Eshan Engineer to Meera Engineer"


def test_timeline_of_a_fresh_cr_is_empty(seeded):
    assert comment_service.timeline(_cr("CR-0001")) == []


def test_timeline_after_real_actions(seeded):
    cr = _cr("CR-0003")  # Approved
    assignment_service.assign(cr, _user("engineer1@cms.local"), _user("reviewer@cms.local"))
    comment_service.add_comment(_cr("CR-0003"), _user("engineer1@cms.local"), "On it")

    items = comment_service.timeline(_cr("CR-0003"))

    assert sorted(i.kind for i in items[:2]) == ["assignment", "status"]
    assert items[-1].kind == "comment" and items[-1].text == "On it"
    assert [i.when for i in items] == sorted(i.when for i in items)


# --- route -----------------------------------------------------------------------


def test_reviewer_adds_a_comment_through_the_page(seeded, client, login):
    login("reviewer@cms.local")
    cr = _cr("CR-0006")

    response = client.post(COMMENTS.format(cr.id), data={"body": "Please add a rollback plan."})

    assert response.status_code == 302
    assert response.headers["Location"].endswith(DETAIL.format(cr.id))
    assert Comment.query.one().body == "Please add a rollback plan."
    page = client.get(DETAIL.format(cr.id)).data
    assert b"Please add a rollback plan." in page
    assert b"Riya Reviewer" in page


def test_success_and_error_messages_are_flashed(seeded, client, login):
    login("reviewer@cms.local")
    cr = _cr("CR-0006")

    ok = client.post(COMMENTS.format(cr.id), data={"body": "Hello"}, follow_redirects=True)
    bad = client.post(COMMENTS.format(cr.id), data={"body": "   "}, follow_redirects=True)

    assert b"alert-success" in ok.data
    assert b"alert-danger" in bad.data
    assert Comment.query.count() == 1


def test_overlong_comment_is_refused_by_the_route(seeded, client, login):
    login("reviewer@cms.local")
    cr = _cr("CR-0006")

    response = client.post(COMMENTS.format(cr.id), data={"body": "a" * 2001}, follow_redirects=True)

    assert b"alert-danger" in response.data
    assert Comment.query.count() == 0


def test_requester_comments_on_their_own_cr_through_the_page(seeded, client, login):
    login("requester@cms.local")
    cr = _cr("CR-0006")

    client.post(COMMENTS.format(cr.id), data={"body": "Thanks for the update"})

    assert Comment.query.one().author.email == "requester@cms.local"


def test_other_requester_gets_403(seeded, client, login):
    login("requester2@cms.local")
    cr = _cr("CR-0006")  # belongs to requester@cms.local

    response = client.post(COMMENTS.format(cr.id), data={"body": "Hello"})

    assert response.status_code == 403
    assert Comment.query.count() == 0


def test_requester_work_note_is_refused_with_403(seeded, client, login):
    login("requester@cms.local")
    cr = _cr("CR-0006")

    response = client.post(COMMENTS.format(cr.id), data={"body": "secret", "is_work_note": "on"})

    assert response.status_code == 403
    assert Comment.query.count() == 0


def test_engineer_adds_a_work_note_through_the_page(seeded, client, login):
    login("engineer1@cms.local")
    cr = _cr("CR-0006")

    client.post(COMMENTS.format(cr.id), data={"body": "Cert renewed on node 2", "is_work_note": "on"})

    assert Comment.query.one().is_work_note is True
    page = client.get(DETAIL.format(cr.id)).data
    assert b"Work note" in page and b"Cert renewed on node 2" in page


def test_unticked_work_note_box_gives_a_normal_comment(seeded, client, login):
    login("engineer1@cms.local")
    client.post(COMMENTS.format(_cr("CR-0006").id), data={"body": "Plain comment"})
    assert Comment.query.one().is_work_note is False


def test_anonymous_user_is_sent_to_login(seeded, client):
    response = client.post(COMMENTS.format(_cr("CR-0006").id), data={"body": "Hello"})
    assert response.status_code == 302 and "/login" in response.headers["Location"]
    assert Comment.query.count() == 0


def test_unknown_cr_returns_404(seeded, client, login):
    login("reviewer@cms.local")
    assert client.post(COMMENTS.format(9999), data={"body": "Hello"}).status_code == 404


def test_comment_notifies_the_right_people_through_the_page(seeded, client, login):
    login("reviewer@cms.local")
    client.post(COMMENTS.format(_cr("CR-0006").id), data={"body": "Checking in"})

    assert len(_notes("requester@cms.local")) == 1
    assert len(_notes("engineer1@cms.local")) == 1


def test_csrf_token_is_required_when_csrf_is_on(seeded, app, client, login):
    login("reviewer@cms.local")
    app.config["CSRF_ENABLED"] = True

    response = client.post(COMMENTS.format(_cr("CR-0006").id), data={"body": "Hello"})

    assert response.status_code == 400
    assert Comment.query.count() == 0


# --- script text is shown as text ------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    ["<script>alert(1)</script>", '<img src=x onerror="alert(1)">', "<b>bold</b> & more"],
)
def test_html_in_a_comment_is_escaped_not_executed(seeded, client, login, payload):
    login("reviewer@cms.local")
    cr = _cr("CR-0006")

    client.post(COMMENTS.format(cr.id), data={"body": payload})
    page = client.get(DETAIL.format(cr.id)).data

    assert payload.encode() not in page
    assert b"&lt;" in page


def test_script_text_is_visible_as_plain_text(seeded, client, login):
    login("reviewer@cms.local")
    cr = _cr("CR-0006")

    client.post(COMMENTS.format(cr.id), data={"body": "<script>alert(1)</script>"})
    page = client.get(DETAIL.format(cr.id)).data

    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert b"<script>alert(1)</script>" not in page


# --- what the page shows -----------------------------------------------------------


@pytest.mark.parametrize("email", ["requester@cms.local", "engineer1@cms.local", "reviewer@cms.local", "admin@cms.local"])
def test_everyone_who_can_see_the_cr_gets_the_comment_form(seeded, client, login, email):
    login(email)
    page = client.get(DETAIL.format(_cr("CR-0006").id)).data
    assert COMMENTS.format(_cr("CR-0006").id).encode() in page
    assert b'name="body"' in page


def test_work_note_checkbox_is_for_staff_only(seeded, client, login, logout):
    cr_id = _cr("CR-0006").id

    login("requester@cms.local")
    assert b'name="is_work_note"' not in client.get(DETAIL.format(cr_id)).data
    logout()

    for email in ["engineer1@cms.local", "reviewer@cms.local", "admin@cms.local"]:
        login(email)
        assert b'name="is_work_note"' in client.get(DETAIL.format(cr_id)).data
        logout()


def test_timeline_shows_who_what_and_when_in_order(seeded, client, login):
    login("reviewer@cms.local")
    cr = _cr("CR-0003")
    client.post(f"/change-requests/{cr.id}/assign", data={"assignee_id": _user("engineer1@cms.local").id})
    client.post(COMMENTS.format(cr.id), data={"body": "First comment"})
    client.post(COMMENTS.format(cr.id), data={"body": "Second comment"})

    page = client.get(DETAIL.format(cr.id)).data.decode()

    assert "Activity timeline" in page
    assert "Assigned to Eshan Engineer" in page
    assert "Approved &rarr; <strong>Assigned</strong>" in page
    assert page.index("First comment") < page.index("Second comment")
    assert page.index("Assigned to Eshan Engineer") < page.index("First comment")
    assert "by Riya Reviewer" in page


def test_timeline_message_when_nothing_has_happened(seeded, client, login):
    login("reviewer@cms.local")
    page = client.get(DETAIL.format(_cr("CR-0001").id)).data
    assert b"Activity timeline" in page and b"No activity recorded yet." in page