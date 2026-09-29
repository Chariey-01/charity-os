import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient

from planning.models import Area, Task
from roadmaps.models import Roadmap, RoadmapNode
from roadmaps.services import next_actions

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return get_user_model().objects.create_user("roadmaps@example.com", "password")


def test_personal_roadmap_seed_is_idempotent_and_does_not_overwrite(user):
    call_command("seed_personal_roadmaps", email=user.email)
    assert Roadmap.objects.filter(user=user).count() == 13
    first = Roadmap.objects.get(user=user, title="TypeScript")
    first_description = first.description
    item_count = RoadmapNode.objects.filter(roadmap=first, node_type="item").count()
    call_command("seed_personal_roadmaps", email=user.email)
    assert Roadmap.objects.filter(user=user).count() == 13
    assert Roadmap.objects.get(pk=first.pk).description == first_description
    assert (
        RoadmapNode.objects.filter(roadmap=first, node_type="item").count()
        == item_count
    )


def test_progress_excludes_skipped_items_and_tree_is_nested(user):
    roadmap = Roadmap.objects.create(user=user, title="Test", description="Purpose")
    section = RoadmapNode.objects.create(
        user=user, roadmap=roadmap, title="Section", node_type="section", position=0
    )
    RoadmapNode.objects.create(
        user=user,
        roadmap=roadmap,
        parent=section,
        title="Done",
        node_type="item",
        state="completed",
        position=0,
    )
    RoadmapNode.objects.create(
        user=user,
        roadmap=roadmap,
        parent=section,
        title="Skipped",
        node_type="item",
        state="skipped",
        position=1,
    )
    RoadmapNode.objects.create(
        user=user,
        roadmap=roadmap,
        parent=section,
        title="Next",
        node_type="item",
        position=2,
    )
    assert roadmap.progress() == {
        "completed_eligible_items": 1,
        "eligible_items": 2,
        "skipped_items": 1,
        "progress_ratio": 0.5,
    }
    client = APIClient()
    client.force_authenticate(user)
    tree = client.get(f"/api/v1/roadmaps/{roadmap.id}/tree")
    assert tree.status_code == 200
    assert tree.json()["nodes"][0]["children"][0]["title"] == "Done"


def test_next_actions_prioritizes_planned_task_and_excludes_blocked(user):
    area = Area.objects.create(user=user, name="Career", slug="career")
    roadmap = Roadmap.objects.create(user=user, title="Next", description="Purpose")
    ready = RoadmapNode.objects.create(
        user=user,
        roadmap=roadmap,
        title="Practise union types",
        node_type="item",
        position=0,
    )
    blocked = RoadmapNode.objects.create(
        user=user, roadmap=roadmap, title="Future topic", node_type="item", position=1
    )
    prerequisite = RoadmapNode.objects.create(
        user=user,
        roadmap=roadmap,
        title="Prerequisite",
        node_type="item",
        state="planned",
        position=2,
    )
    from roadmaps.models import RoadmapNodePrerequisite

    RoadmapNodePrerequisite.objects.create(
        user=user, node=blocked, prerequisite=prerequisite
    )
    Task.objects.create(
        user=user, area=area, roadmap_item=ready, title=ready.title, priority=3
    )
    actions = next_actions(user)
    assert actions[0]["title"] == "Practise union types"
    assert all(action["title"] != "Future topic" for action in actions)


def test_roadmap_ownership_isolation(user):
    other = get_user_model().objects.create_user(
        "other-roadmap@example.com", "password"
    )
    roadmap = Roadmap.objects.create(user=user, title="Private")
    client = APIClient()
    client.force_authenticate(other)
    assert client.get(f"/api/v1/roadmaps/{roadmap.id}").status_code == 404
    assert client.get("/api/v1/roadmaps/next-actions").json() == []
