"""Vision, goals, milestones, projects, journal and My Journey (growth app)."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient

from growth.models import ActivityEvent, Goal, Milestone, Project, VisionItem
from planning.models import Area, Task
from roadmaps.models import Roadmap, RoadmapNode

pytestmark = pytest.mark.django_db
API = "/api/v1"


def make_user(email):
    return get_user_model().objects.create_user(email, "password", timezone="Africa/Nairobi")


@pytest.fixture
def user():
    return make_user("owner@example.com")


@pytest.fixture
def other():
    return make_user("friend@example.com")


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def other_client(other):
    api = APIClient()
    api.force_authenticate(other)
    return api


def test_vision_is_an_intention_until_evidence_or_confirmation(client):
    created = client.post(
        f"{API}/vision",
        {"kind": "manifestation", "title": "I lead an AI product team", "theme": "Career"},
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.data["status"] == "active"
    vid = created.data["id"]

    refused = client.post(f"{API}/vision/{vid}/realise", {"note": "felt close"}, format="json")
    assert refused.status_code == 400
    assert VisionItem.objects.get(pk=vid).status == "active"

    bad_link = client.post(
        f"{API}/vision/{vid}/realise", {"evidence_url": "http://x.test"}, format="json"
    )
    assert bad_link.status_code == 400

    ok = client.post(
        f"{API}/vision/{vid}/realise",
        {"evidence_url": "https://example.com/offer", "note": "Offer letter"},
        format="json",
    )
    assert ok.status_code == 200
    assert ok.data["status"] == "realised"
    assert ActivityEvent.objects.filter(subject_id=vid, kind="realised").count() == 1


def test_status_cannot_be_set_through_patch(client):
    vid = client.post(f"{API}/vision", {"title": "Calm and strong"}, format="json").data["id"]
    assert client.patch(f"{API}/vision/{vid}", {"status": "realised"}, format="json").data[
        "status"
    ] == "active"
    goal = client.post(f"{API}/goals", {"title": "Ship CharityOS"}, format="json").data
    response = client.patch(f"{API}/goals/{goal['id']}", {"status": "completed"}, format="json")
    assert response.status_code == 400
    assert Goal.objects.get(pk=goal["id"]).status == "active"


def test_revising_a_vision_keeps_the_previous_wording(client):
    vid = client.post(
        f"{API}/vision", {"title": "Engineer", "statement": "v1"}, format="json"
    ).data["id"]
    client.patch(f"{API}/vision/{vid}", {"statement": "v2"}, format="json")
    client.patch(f"{API}/vision/{vid}", {"theme": "Career"}, format="json")  # no wording change
    revisions = client.get(f"{API}/vision/{vid}/revisions").data
    assert [r["statement"] for r in revisions] == ["v1"]
    assert VisionItem.objects.get(pk=vid).version == 2


def test_goal_progress_is_never_invented(client):
    goal = client.post(f"{API}/goals", {"title": "Learn AI"}, format="json").data
    assert goal["progress"]["ratio"] is None
    assert goal["progress"]["basis"] == "none"

    measurable = client.post(
        f"{API}/goals",
        {"title": "Run 100 km", "kind": "measurable", "metric_unit": "km", "target_value": "100"},
        format="json",
    ).data
    assert measurable["progress"]["ratio"] is None
    refused = client.post(f"{API}/goals/{measurable['id']}/checkins", {"note": "ran"}, format="json")
    assert refused.status_code == 400
    client.post(f"{API}/goals/{measurable['id']}/checkins", {"value": "25"}, format="json")
    after = client.get(f"{API}/goals/{measurable['id']}").data
    assert after["progress"]["ratio"] == 0.25
    assert after["progress"]["basis"] == "measure"

    missing_target = client.post(
        f"{API}/goals", {"title": "x", "kind": "measurable"}, format="json"
    )
    assert missing_target.status_code == 400


def test_milestones_drive_qualitative_progress_and_record_history(client):
    goal = client.post(f"{API}/goals", {"title": "Become a confident speaker"}, format="json").data
    ids = [
        client.post(f"{API}/milestones", {"goal": goal["id"], "title": t}, format="json").data["id"]
        for t in ("First talk", "Second talk")
    ]
    done = client.post(f"{API}/milestones/{ids[0]}/status", {"status": "done"}, format="json")
    assert done.status_code == 200
    assert done.data["status"] == "done"
    overview = client.get(f"{API}/goals/{goal['id']}/overview").data
    assert overview["goal"]["progress"]["ratio"] == 0.5
    assert overview["goal"]["progress"]["basis"] == "milestones"
    event = ActivityEvent.objects.get(subject_id=ids[0], kind="completed")
    assert event.data["goal"] == "Become a confident speaker"

    moved = client.patch(f"{API}/milestones/{ids[0]}", {"goal": None}, format="json")
    assert moved.status_code == 400


def test_milestone_needs_exactly_one_parent(client):
    response = client.post(f"{API}/milestones", {"title": "Orphan"}, format="json")
    assert response.status_code == 400


def test_projects_are_independent_workspaces(client):
    a = client.post(f"{API}/projects", {"name": "QUAHAXTON"}, format="json").data
    b = client.post(f"{API}/projects", {"name": "FundBridge"}, format="json").data
    dup = client.post(f"{API}/projects", {"name": "quahaxton"}, format="json")
    assert dup.status_code == 400
    client.post(f"{API}/tasks", {"title": "Pitch deck", "project": a["id"]}, format="json")
    client.post(f"{API}/tasks", {"title": "Grant form", "project": b["id"]}, format="json")
    board_a = client.get(f"{API}/projects/{a['id']}/overview").data
    assert [t["title"] for t in board_a["tasks"]] == ["Pitch deck"]
    done = client.post(f"{API}/projects/{a['id']}/status", {"status": "completed"}, format="json")
    assert done.data["status"] == "completed" and done.data["completed_at"]
    assert Project.objects.get(pk=b["id"]).status == "active"


def test_task_takes_its_milestones_parent_and_refuses_a_mismatch(client):
    project = client.post(f"{API}/projects", {"name": "Client site"}, format="json").data
    other = client.post(f"{API}/projects", {"name": "Portfolio"}, format="json").data
    milestone = client.post(
        f"{API}/milestones", {"project": project["id"], "title": "Launch"}, format="json"
    ).data
    task = client.post(
        f"{API}/tasks", {"title": "Deploy", "milestone": milestone["id"]}, format="json"
    )
    assert task.status_code == 201
    assert str(task.data["project"]) == project["id"]
    clash = client.post(
        f"{API}/tasks",
        {"title": "x", "milestone": milestone["id"], "project": other["id"]},
        format="json",
    )
    assert clash.status_code == 400


def test_task_checklist_is_validated(client):
    ok = client.post(
        f"{API}/tasks",
        {"title": "Write post", "checklist": [{"id": "a", "text": "Outline", "done": False}]},
        format="json",
    )
    assert ok.status_code == 201
    assert ok.data["checklist"] == [{"id": "a", "text": "Outline", "done": False}]
    bad = client.post(
        f"{API}/tasks", {"title": "x", "checklist": [{"text": ""}]}, format="json"
    )
    assert bad.status_code == 400


def test_other_users_records_are_invisible_and_unlinkable(client, other_client, user):
    goal = client.post(f"{API}/goals", {"title": "Private goal"}, format="json").data
    project = client.post(f"{API}/projects", {"name": "Private"}, format="json").data
    vision = client.post(f"{API}/vision", {"title": "Private dream"}, format="json").data
    for path in (f"goals/{goal['id']}", f"projects/{project['id']}", f"vision/{vision['id']}"):
        assert other_client.get(f"{API}/{path}").status_code == 404
    assert other_client.get(f"{API}/goals").data == []
    assert other_client.post(f"{API}/goals/{goal['id']}/status", {"status": "completed"}, format="json").status_code == 404
    linked = other_client.post(
        f"{API}/tasks", {"title": "Steal", "goal": goal["id"]}, format="json"
    )
    assert linked.status_code == 400
    milestone = other_client.post(
        f"{API}/milestones", {"goal": goal["id"], "title": "x"}, format="json"
    )
    assert milestone.status_code == 400
    journey = other_client.get(f"{API}/journey").data
    assert journey["entries"] == []


def test_archive_instead_of_delete(client):
    goal = client.post(f"{API}/goals", {"title": "Archive me"}, format="json").data
    assert client.delete(f"{API}/goals/{goal['id']}").status_code == 405
    client.post(f"{API}/goals/{goal['id']}/archive")
    assert client.get(f"{API}/goals").data == []
    assert len(client.get(f"{API}/goals?archived=only").data) == 1
    client.post(f"{API}/goals/{goal['id']}/restore")
    assert len(client.get(f"{API}/goals").data) == 1


def test_journey_keeps_completion_snapshots_after_renames(client, user):
    goal = client.post(f"{API}/goals", {"title": "Original title"}, format="json").data
    client.post(f"{API}/goals/{goal['id']}/status", {"status": "completed", "note": "Done!"}, format="json")
    client.patch(f"{API}/goals/{goal['id']}", {"title": "Renamed later"}, format="json")
    client.post(
        f"{API}/journal",
        {"kind": "decision", "title": "Chose AI engineering", "local_date": date.today().isoformat()},
        format="json",
    )
    data = client.get(f"{API}/journey").data
    titles = {(e["type"], e["title"]) for e in data["entries"]}
    assert ("goal_completed", "Original title") in titles
    assert ("journal_decision", "Chose AI engineering") in titles
    assert data["summary"]["goals_completed"] == 1
    assert data["years"][0] == data["year"]


def test_journal_edits_keep_previous_wording(client):
    entry = client.post(
        f"{API}/journal",
        {"kind": "lesson", "title": "Ship small", "body": "v1", "local_date": "2026-11-20"},
        format="json",
    ).data
    client.patch(f"{API}/journal/{entry['id']}", {"body": "v2"}, format="json")
    after = client.get(f"{API}/journal/{entry['id']}").data
    assert after["body"] == "v2"
    assert [r["body"] for r in after["revisions"]] == ["v1"]


def test_task_completion_snapshots_the_workstream(client, user):
    """TD-1: moving a done task later does not move it in past weeks."""
    study = Area.objects.create(user=user, name="Study", slug="study")
    work = Area.objects.create(user=user, name="Work", slug="work")
    task = client.post(
        f"{API}/tasks", {"title": "Chapter 1", "area": str(study.pk)}, format="json"
    ).data
    client.patch(f"{API}/tasks/{task['id']}", {"status": "done"}, format="json")
    client.patch(f"{API}/tasks/{task['id']}", {"area": str(work.pk)}, format="json")
    progress = client.get(f"{API}/progress").data
    rows = [t for t in progress["tasks"]["completed"] if t["id"] == task["id"]]
    assert rows and rows[0]["label"] == "Study"
    labels = [row["label"] for row in progress["workstreams"]["completed_tasks"]]
    assert "Study" in labels and "Work" not in labels


def test_roadmap_template_creates_an_editable_plan_with_no_progress(client, user):
    templates = client.get(f"{API}/roadmap-templates").data
    assert templates[0]["key"] == "ai-engineering"
    assert len(templates[0]["stages"]) == 16
    created = client.post(
        f"{API}/roadmaps/from-template", {"template": "ai-engineering"}, format="json"
    )
    assert created.status_code == 201
    roadmap = Roadmap.objects.get(pk=created.data["id"])
    nodes = RoadmapNode.objects.filter(roadmap=roadmap)
    assert nodes.filter(node_type="section").count() == 16
    assert not nodes.filter(state="completed").exists()
    assert roadmap.progress()["completed_eligible_items"] == 0
    item = nodes.filter(node_type="item").first()
    client.patch(f"{API}/roadmap-nodes/{item.pk}", {"title": "My own item"}, format="json")
    assert RoadmapNode.objects.get(pk=item.pk).title == "My own item"
    client.patch(f"{API}/roadmap-nodes/{item.pk}", {"state": "completed"}, format="json")
    assert ActivityEvent.objects.filter(subject_id=item.pk, kind="completed").exists()
    roadmap_paused = client.patch(f"{API}/roadmaps/{roadmap.pk}", {"status": "paused"}, format="json")
    assert roadmap_paused.data["status"] == "paused"


def test_challenge_can_pause_and_resume(client):
    challenge = client.post(
        f"{API}/challenges",
        {"name": "Annual plan 2027", "start_date": "2027-01-01", "end_date": "2027-12-31", "status": "active"},
        format="json",
    ).data
    paused = client.patch(f"{API}/challenges/{challenge['id']}", {"status": "paused"}, format="json")
    assert paused.status_code == 200 and paused.data["status"] == "paused"
    resumed = client.patch(f"{API}/challenges/{challenge['id']}", {"status": "active"}, format="json")
    assert resumed.data["status"] == "active"


def test_carry_forward_is_deliberate_and_recorded(client):
    goal = client.post(
        f"{API}/goals", {"title": "Finish course", "target_date": "2026-12-31"}, format="json"
    ).data
    candidates = client.get(f"{API}/journey/year-end?year=2026").data["goals"]
    assert [g["id"] for g in candidates] == [goal["id"]]
    moved = client.post(
        f"{API}/goals/{goal['id']}/carry-forward", {"target_date": "2027-03-31"}, format="json"
    )
    assert moved.data["target_date"] == "2027-03-31"
    assert ActivityEvent.objects.filter(subject_id=goal["id"], kind="carried_forward").exists()


def test_erase_user_removes_growth_records(user, other, client):
    goal = client.post(f"{API}/goals", {"title": "G"}, format="json").data
    vision = client.post(f"{API}/vision", {"title": "V"}, format="json").data
    client.patch(f"{API}/goals/{goal['id']}", {"vision": vision["id"]}, format="json")
    project = client.post(f"{API}/projects", {"name": "P", "goal": goal["id"]}, format="json").data
    milestone = client.post(f"{API}/milestones", {"project": project["id"], "title": "M"}, format="json").data
    client.post(f"{API}/tasks", {"title": "T", "milestone": milestone["id"]}, format="json")
    client.post(f"{API}/goals/{goal['id']}/status", {"status": "completed"}, format="json")
    call_command("erase_user", user.email, "--confirm", user.email)
    assert not Goal.objects.exists() and not Milestone.objects.exists()
    assert not Task.objects.filter(user_id=user.pk).exists()
    assert get_user_model().objects.filter(pk=other.pk).exists()


def test_direction_insights_show_movement_and_what_keeps_slipping(client, user):
    goal = client.post(f"{API}/goals", {"title": "Ship portfolio"}, format="json").data
    client.post(f"{API}/milestones", {"goal": goal["id"], "title": "Case study"}, format="json")
    task = client.post(
        f"{API}/tasks", {"title": "Write case study", "due_date": "2026-11-20"}, format="json"
    ).data
    for later in ("2026-11-22", "2026-11-25", "2026-11-28"):
        client.patch(f"{API}/tasks/{task['id']}", {"due_date": later}, format="json")
    client.patch(f"{API}/tasks/{task['id']}", {"due_date": "2026-11-21"}, format="json")  # earlier: not a postponement
    data = client.get(f"{API}/insights/direction").data
    assert [g["title"] for g in data["goals"]] == ["Ship portfolio"]
    assert data["goals"][0]["ratio"] == 0.0 and data["goals"][0]["basis"] == "milestones"
    assert data["postponed"] == [
        {"id": task["id"], "title": "Write case study", "times": 3, "status": "todo"}
    ]


def test_insights_accept_six_months(client):
    assert client.get(f"{API}/insights?period=180d").status_code == 200
