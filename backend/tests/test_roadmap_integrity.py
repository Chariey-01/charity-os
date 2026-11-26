"""Phase 0B, B1: roadmap trees stay trees."""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection
from rest_framework.test import APIClient

import roadmaps.services as roadmap_services
from planning.models import Area
from roadmaps.models import Roadmap, RoadmapNode

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("tree@example.com", "password")


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def roadmap(user):
    return Roadmap.objects.create(user=user, title="Python")


def node(user, roadmap, title, parent=None):
    return RoadmapNode.objects.create(
        user=user, roadmap=roadmap, parent=parent, title=title, node_type="item"
    )


def move(client, child, parent):
    return client.patch(
        f"/api/v1/roadmap-nodes/{child.id}",
        {"parent": str(parent.id) if parent else None},
        format="json",
    )


def test_audit_probe_two_node_cycle_is_refused(client, user, roadmap):
    """2026-11-24 audit: n1 under n2, then n2 under n1, both answered 200."""
    first = node(user, roadmap, "n1")
    second = node(user, roadmap, "n2")

    assert move(client, first, second).status_code == 200
    refused = move(client, second, first)

    assert refused.status_code == 400
    assert "parent" in refused.json()["error"]["fields"]
    second.refresh_from_db()
    assert second.parent_id is None
    tree = client.get(f"/api/v1/roadmaps/{roadmap.id}/tree").json()["nodes"]
    assert [row["title"] for row in tree] == ["n2"]
    assert [row["title"] for row in tree[0]["children"]] == ["n1"]


def test_self_and_descendant_parents_are_refused(client, user, roadmap):
    top = node(user, roadmap, "top")
    middle = node(user, roadmap, "middle", parent=top)
    leaf = node(user, roadmap, "leaf", parent=middle)

    assert move(client, top, top).status_code == 400
    assert move(client, top, leaf).status_code == 400
    assert move(client, top, middle).status_code == 400
    assert move(client, leaf, top).status_code == 200  # a valid move
    assert move(client, leaf, None).status_code == 200  # back to a root
    top.refresh_from_db()
    assert top.parent_id is None


def test_parents_must_be_in_the_same_roadmap(client, user, roadmap):
    other_roadmap = Roadmap.objects.create(user=user, title="Go")
    elsewhere = node(user, other_roadmap, "elsewhere")
    here = node(user, roadmap, "here")

    moved = move(client, here, elsewhere)
    created = client.post(
        "/api/v1/roadmap-nodes",
        {
            "roadmap": str(roadmap.id),
            "parent": str(elsewhere.id),
            "title": "new",
            "node_type": "item",
        },
        format="json",
    )
    switched = client.patch(
        f"/api/v1/roadmap-nodes/{here.id}",
        {"roadmap": str(other_roadmap.id)},
        format="json",
    )

    assert moved.status_code == created.status_code == switched.status_code == 400
    assert "roadmap" in switched.json()
    assert RoadmapNode.objects.filter(title="new").count() == 0
    here.refresh_from_db()
    assert (here.roadmap_id, here.parent_id) == (roadmap.id, None)


def test_archived_parents_are_refused(client, user, roadmap):
    parent = node(user, roadmap, "parent")
    child = node(user, roadmap, "child")
    client.post(f"/api/v1/roadmap-nodes/{parent.id}/archive")

    assert move(client, child, parent).status_code == 400


def test_another_users_parent_is_refused(client, user, roadmap, django_user_model):
    other = django_user_model.objects.create_user("other@example.com", "password")
    theirs = node(other, Roadmap.objects.create(user=other, title="T"), "theirs")

    assert move(client, node(user, roadmap, "mine"), theirs).status_code == 400


def test_cycles_already_in_old_data_are_contained(client, user, roadmap):
    first = node(user, roadmap, "A")
    second = node(user, roadmap, "B", parent=first)
    RoadmapNode.objects.filter(pk=first.pk).update(parent=second)  # legacy cycle
    outsider = node(user, roadmap, "C")
    area = Area.objects.create(user=user, name="Study", slug="study")

    attached = move(client, outsider, first)
    tree = client.get(f"/api/v1/roadmaps/{roadmap.id}/tree")
    started = client.post(
        "/api/v1/sessions/start",
        {
            "id": str(uuid.uuid4()),
            "title": "Focus",
            "area": str(area.id),
            "is_deep_work": True,
            "roadmap_item": str(first.id),
        },
        format="json",
    )

    assert attached.status_code == 400
    assert tree.status_code == 200
    assert started.status_code == 201  # ancestry no longer loops forever
    assert len(started.json()["roadmap_ancestry_snapshot"]) == 2


@pytest.mark.django_db(transaction=True)
def test_concurrent_opposite_moves_cannot_create_a_cycle(
    user, roadmap, monkeypatch, django_user_model
):
    first = node(user, roadmap, "A")
    second = node(user, roadmap, "B")
    real = roadmap_services._reaches

    def slow_reaches(start, target_pk):
        result = real(start, target_pk)
        time.sleep(0.4)  # widen the race window between check and write
        return result

    monkeypatch.setattr(roadmap_services, "_reaches", slow_reaches)

    def attempt(child, parent):
        try:
            api = APIClient()
            api.force_authenticate(user)
            return move(api, child, parent).status_code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(
            pool.map(lambda pair: attempt(*pair), [(first, second), (second, first)])
        )

    assert results == [200, 400]
    first.refresh_from_db()
    second.refresh_from_db()
    assert not (first.parent_id == second.pk and second.parent_id == first.pk)
