"""Private beta sign-up, password reset, feedback and accountability partners."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient

from community.models import BetaInvite, Cheer, Partnership
from community.services import create_invite, reset_link_parts
from growth.models import Goal, JournalEntry, Milestone, Project
from planning.models import Area, Task
from reflections.models import WeeklyReview

pytestmark = pytest.mark.django_db
API = "/api/v1"
STRONG = "a-Long-unique-passphrase-91"


def make(email, staff=False):
    return get_user_model().objects.create_user(
        email, STRONG, timezone="Africa/Nairobi", display_name=email.split("@")[0], is_staff=staff
    )


def as_user(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def admin():
    return make("owner@example.com", staff=True)


def csrf_client():
    client = APIClient(enforce_csrf_checks=True)
    token = client.get(f"{API}/auth/csrf").data["csrf_token"]
    client.credentials(HTTP_X_CSRFTOKEN=token)
    return client


def test_signup_needs_a_valid_unused_invite_and_logs_in(admin):
    invite, code = create_invite(created_by=admin, note="Amina")
    client = csrf_client()
    body = {"email": "amina@example.com", "password": STRONG, "display_name": "Amina", "timezone": "Africa/Nairobi"}
    assert client.post(f"{API}/auth/signup", {**body, "invite_code": "nope"}, format="json").status_code == 400
    weak = client.post(f"{API}/auth/signup", {**body, "invite_code": code, "password": "123"}, format="json")
    assert weak.status_code == 400
    ok = client.post(f"{API}/auth/signup", {**body, "invite_code": code}, format="json")
    assert ok.status_code == 201, ok.data
    assert client.get(f"{API}/me").data["email"] == "amina@example.com"
    assert Area.objects.filter(user__email="amina@example.com").exists()
    again = csrf_client().post(
        f"{API}/auth/signup", {**body, "email": "b@example.com", "invite_code": code}, format="json"
    )
    assert again.status_code == 400
    invite.refresh_from_db()
    assert invite.uses == 1


def test_signup_requires_csrf_and_respects_bound_email_and_closed_mode(admin, settings):
    _, code = create_invite(created_by=admin, email="only@example.com")
    no_csrf = APIClient(enforce_csrf_checks=True)
    assert no_csrf.post(f"{API}/auth/signup", {"invite_code": code}, format="json").status_code == 403
    wrong = csrf_client().post(
        f"{API}/auth/signup", {"invite_code": code, "email": "other@example.com", "password": STRONG}, format="json"
    )
    assert wrong.status_code == 400
    settings.CHARITYOS_SIGNUP_MODE = "closed"
    closed = csrf_client().post(
        f"{API}/auth/signup", {"invite_code": code, "email": "only@example.com", "password": STRONG}, format="json"
    )
    assert closed.status_code == 403


def test_only_beta_admins_manage_invites_users_and_feedback(admin):
    friend = make("friend@example.com")
    assert as_user(friend).post(f"{API}/beta/invites", {}, format="json").status_code == 403
    assert as_user(friend).get(f"{API}/beta/users").status_code == 403
    assert as_user(friend).get(f"{API}/beta/feedback").status_code == 403
    created = as_user(admin).post(f"{API}/beta/invites", {"note": "Brian", "days": 7}, format="json")
    assert created.status_code == 201 and len(created.data["code"]) > 20
    listed = as_user(admin).get(f"{API}/beta/invites").data
    assert "code" not in listed[0]
    assert BetaInvite.objects.get().code_hash != created.data["code"]
    revoked = as_user(admin).post(f"{API}/beta/invites/{created.data['id']}/revoke")
    assert revoked.data["status"] == "revoked"


def test_password_reset_link_works_once(admin):
    friend = make("friend@example.com")
    uid, token = reset_link_parts(friend)
    client = csrf_client()
    ok = client.post(f"{API}/auth/password/reset", {"uid": uid, "token": token, "password": "another-Good-phrase-72"}, format="json")
    assert ok.status_code == 200
    reused = csrf_client().post(f"{API}/auth/password/reset", {"uid": uid, "token": token, "password": "third-Good-phrase-73"}, format="json")
    assert reused.status_code == 400
    friend.refresh_from_db()
    assert friend.check_password("another-Good-phrase-72")
    link = as_user(admin).post(f"{API}/beta/users/{friend.pk}/reset-link").data["path"]
    assert link.startswith("/#/reset?uid=")


def test_change_password_needs_the_current_one(admin):
    client = as_user(admin)
    assert client.post(f"{API}/auth/password", {"current_password": "wrong", "new_password": "x-New-phrase-1234"}, format="json").status_code == 400
    assert client.post(f"{API}/auth/password", {"current_password": STRONG, "new_password": "x-New-phrase-1234"}, format="json").status_code == 200


def test_feedback_is_private_to_its_author_and_the_beta_admin(admin):
    a, b = make("a@example.com"), make("b@example.com")
    assert as_user(a).post(f"{API}/feedback", {"kind": "bug", "message": "hi"}, format="json").status_code == 400
    as_user(a).post(f"{API}/feedback", {"kind": "bug", "message": "The board overflows", "page": "#/projects"}, format="json")
    assert as_user(b).get(f"{API}/feedback").data == []
    assert [row["message"] for row in as_user(admin).get(f"{API}/beta/feedback").data] == ["The board overflows"]


@pytest.fixture
def pair():
    owner, partner, stranger = make("owner2@example.com"), make("partner@example.com"), make("stranger@example.com")
    area = Area.objects.create(user=owner, name="Learning", slug="learning")
    shared = Goal.objects.create(user=owner, title="Shared goal", why="PRIVATE WHY", description="PRIVATE DESC", area=area)
    Milestone.objects.create(user=owner, goal=shared, title="First talk")
    hidden = Goal.objects.create(user=owner, title="Hidden goal")
    Project.objects.create(user=owner, name="Secret project")
    JournalEntry.objects.create(user=owner, title="Private journal", local_date=date(2026, 11, 20))
    Task.objects.create(user=owner, title="Private task", goal=hidden)
    return owner, partner, stranger, shared, hidden


def test_partner_sees_only_what_was_shared_after_accepting(pair):
    owner, partner, stranger, shared, hidden = pair
    invite = as_user(owner).post(f"{API}/partners", {"email": "PARTNER@example.com"}, format="json")
    assert invite.status_code == 201
    pid = invite.data["id"]
    assert as_user(owner).post(f"{API}/partners", {"email": "owner2@example.com"}, format="json").status_code == 400
    # Not visible before accepting, and a stranger cannot accept it.
    assert as_user(partner).get(f"{API}/partners/{pid}/view").status_code == 404
    assert as_user(stranger).post(f"{API}/partners/{pid}/accept").status_code == 404
    assert [i["id"] for i in as_user(partner).get(f"{API}/partners").data["invitations"]] == [pid]
    assert as_user(partner).post(f"{API}/partners/{pid}/accept").status_code == 200
    as_user(owner).patch(f"{API}/partners/{pid}", {"goals": [str(shared.pk)]}, format="json")
    view = as_user(partner).get(f"{API}/partners/{pid}/view").data
    text = str(view)
    assert [g["title"] for g in view["goals"]] == ["Shared goal"]
    assert view["goals"][0]["milestones"][0]["title"] == "First talk"
    for secret in ("PRIVATE WHY", "PRIVATE DESC", "Hidden goal", "Secret project", "Private journal", "Private task", "owner2@example.com"):
        assert secret not in text
    assert "summary" in view and "achievements" not in view


def test_partner_cannot_edit_or_select_others_records(pair):
    owner, partner, stranger, shared, hidden = pair
    pid = as_user(owner).post(f"{API}/partners", {"email": "partner@example.com"}, format="json").data["id"]
    as_user(partner).post(f"{API}/partners/{pid}/accept")
    assert as_user(partner).patch(f"{API}/partners/{pid}", {"goals": [str(shared.pk)]}, format="json").status_code == 404
    assert as_user(partner).patch(f"{API}/goals/{shared.pk}", {"title": "hacked"}, format="json").status_code == 404
    strangers_goal = Goal.objects.create(user=stranger, title="Not yours")
    bad = as_user(owner).patch(f"{API}/partners/{pid}", {"goals": [str(strangers_goal.pk)]}, format="json")
    assert bad.status_code == 400
    review = WeeklyReview.objects.create(user=stranger, week_start_date=date(2026, 11, 23), week_end_date=date(2026, 11, 29), timezone_name="UTC")
    assert as_user(owner).patch(f"{API}/partners/{pid}", {"weekly_reviews": [str(review.pk)]}, format="json").status_code == 400
    Goal.objects.filter(pk=shared.pk).update()
    assert Goal.objects.get(pk=shared.pk).title == "Shared goal"


def test_pause_end_and_cheers(pair):
    owner, partner, stranger, shared, hidden = pair
    pid = as_user(owner).post(f"{API}/partners", {"email": "partner@example.com", "share_achievements": True}, format="json").data["id"]
    as_user(partner).post(f"{API}/partners/{pid}/accept")
    as_user(owner).patch(f"{API}/partners/{pid}", {"goals": [str(shared.pk)]}, format="json")
    ok = as_user(partner).post(f"{API}/partners/{pid}/cheer", {"kind": "cheer", "message": "Go!", "about": f"goal:{shared.pk}"}, format="json")
    assert ok.status_code == 201
    not_shared = as_user(partner).post(f"{API}/partners/{pid}/cheer", {"about": f"goal:{hidden.pk}"}, format="json")
    assert not_shared.status_code == 400
    assert as_user(owner).get(f"{API}/partners").data["sharing"][0]["cheers"][0]["message"] == "Go!"
    as_user(owner).patch(f"{API}/partners/{pid}", {"paused": True}, format="json")
    paused = as_user(partner).get(f"{API}/partners/{pid}/view").data
    assert paused["paused"] is True and "goals" not in paused
    assert as_user(partner).post(f"{API}/partners/{pid}/cheer", {}, format="json").status_code == 400
    assert as_user(stranger).post(f"{API}/partners/{pid}/end").status_code == 404
    assert as_user(partner).post(f"{API}/partners/{pid}/end").data["status"] == "ended"
    assert as_user(partner).get(f"{API}/partners/{pid}/view").status_code == 404
    assert Cheer.objects.count() == 1


def test_management_commands(admin, capsys):
    friend = make("friend@example.com")
    call_command("grant_beta_admin", "--email", friend.email)
    friend.refresh_from_db()
    assert friend.is_staff
    call_command("create_beta_invite", "--by", admin.email, "--note", "x")
    call_command("issue_password_reset", "--email", friend.email)
    out = capsys.readouterr().out
    assert "Invite code:" in out and "/#/reset?uid=" in out


def test_erase_user_removes_community_records(pair, admin):
    owner, partner, stranger, shared, hidden = pair
    pid = as_user(owner).post(f"{API}/partners", {"email": "partner@example.com"}, format="json").data["id"]
    as_user(partner).post(f"{API}/partners/{pid}/accept")
    as_user(partner).post(f"{API}/partners/{pid}/cheer", {"message": "hi"}, format="json")
    as_user(owner).post(f"{API}/feedback", {"message": "Something broke"}, format="json")
    call_command("erase_user", owner.email, "--confirm", owner.email)
    assert not Partnership.objects.exists() and not Cheer.objects.exists()
    assert get_user_model().objects.filter(pk=partner.pk).exists()


def test_erasing_the_partner_ends_the_relationship_and_keeps_the_owners_records(pair):
    owner, partner, stranger, shared, hidden = pair
    pid = as_user(owner).post(f"{API}/partners", {"email": "partner@example.com"}, format="json").data["id"]
    as_user(partner).post(f"{API}/partners/{pid}/accept")
    as_user(owner).patch(f"{API}/partners/{pid}", {"goals": [str(shared.pk)]}, format="json")
    as_user(partner).post(f"{API}/partners/{pid}/cheer", {"message": "You can do it"}, format="json")
    call_command("erase_user", partner.email, "--confirm", partner.email)
    assert not Partnership.objects.exists() and not Cheer.objects.exists()
    assert Goal.objects.filter(pk=shared.pk, user=owner).exists()
    assert Milestone.objects.filter(goal=shared).count() == 1
