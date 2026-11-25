from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from execution.models import FocusSession
from planning.models import Task

from .models import RoadmapNode


class ParentArchivedError(Exception):
    """A node cannot be restored while its parent is archived."""


def _active(queryset, include_archived):
    return queryset if include_archived else queryset.filter(archived_at__isnull=True)


def node_detail(node, include_archived=False):
    task_ids = list(
        _active(node.tasks.all(), include_archived).values_list("id", flat=True)
    )
    seconds = (
        FocusSession.objects.filter(
            user=node.user, roadmap_item=node, status="completed"
        ).aggregate(total=Sum("duration_seconds"))["total"]
        or 0
    )
    return {
        "id": str(node.id),
        "title": node.title,
        "description": node.description,
        "node_type": node.node_type,
        "state": node.state,
        "position": node.position,
        "archived_at": node.archived_at,
        "time_invested_seconds": seconds,
        "linked_task_ids": [str(value) for value in task_ids],
        "resources": [
            {"id": str(resource.id), "label": resource.label, "url": resource.url}
            for resource in _active(node.resources.all(), include_archived).order_by(
                "position"
            )
        ],
        "evidence_count": _active(node.evidence.all(), include_archived).count(),
        "prerequisite_ids": [
            str(edge.prerequisite_id) for edge in node.prerequisite_edges.all()
        ],
        "children": [
            node_detail(child, include_archived)
            for child in _active(node.children.all(), include_archived).order_by(
                "position", "title"
            )
        ],
    }


def roadmap_tree(roadmap, include_archived=False):
    roots = _active(roadmap.nodes.filter(parent__isnull=True), include_archived)
    return [
        node_detail(node, include_archived)
        for node in roots.order_by("position", "title")
    ]


def next_actions(user, limit=5):
    candidates = (
        RoadmapNode.objects.filter(
            user=user,
            node_type=RoadmapNode.NodeType.ITEM,
            state=RoadmapNode.State.PLANNED,
            archived_at__isnull=True,
            roadmap__archived_at__isnull=True,
        )
        .select_related("roadmap")
        .prefetch_related("prerequisite_edges__prerequisite", "tasks")
    )
    ranked = []
    for node in candidates:
        prerequisites = list(node.prerequisite_edges.all())
        # An archived prerequisite has left the plan and no longer blocks.
        if any(
            edge.prerequisite.state != RoadmapNode.State.COMPLETED
            and edge.prerequisite.archived_at is None
            for edge in prerequisites
        ):
            continue
        tasks = list(
            node.tasks.filter(
                status__in=Task.OPEN_STATUSES, archived_at__isnull=True
            ).order_by("-priority", "created_at")
        )
        priority = tasks[0].priority if tasks else 0
        ranked.append(
            (
                -(priority > 0),
                -priority,
                node.roadmap.title.lower(),
                node.position,
                node.title.lower(),
                node,
                tasks[0] if tasks else None,
            )
        )
    ranked.sort(key=lambda row: row[:5])
    return [
        {
            "roadmap_id": str(node.roadmap_id),
            "roadmap_title": node.roadmap.title,
            "node_id": str(node.id),
            "title": node.title,
            "description": node.description,
            "linked_task_id": str(task.id) if task else None,
            "reason": "planned task" if task else "prerequisite-ready item",
        }
        for *_, node, task in ranked[:limit]
    ]


def _descendant_ids(node):
    """Every descendant of ``node``. Stops at nodes already seen, so a parent
    cycle left in old data cannot loop forever."""
    seen = {node.pk}
    frontier = [node.pk]
    while frontier:
        frontier = [
            pk
            for pk in RoadmapNode.objects.filter(parent_id__in=frontier).values_list(
                "pk", flat=True
            )
            if pk not in seen
        ]
        seen.update(frontier)
    seen.discard(node.pk)
    return seen


@transaction.atomic
def archive_node(*, user, node):
    """Archive a node and its not-yet-archived descendants with one timestamp.

    Nothing is deleted: tasks, sessions, evidence and resources stay linked.
    Idempotent.
    """
    node = RoadmapNode.objects.select_for_update().get(pk=node.pk, user=user)
    if node.archived_at is not None:
        return node
    now = timezone.now()
    RoadmapNode.objects.filter(
        user=user,
        pk__in={node.pk, *_descendant_ids(node)},
        archived_at__isnull=True,
    ).update(archived_at=now, updated_at=now)
    node.refresh_from_db()
    return node


@transaction.atomic
def restore_node(*, user, node):
    """Restore a node and the descendants that were archived together with it.

    Descendants archived earlier, on their own, stay archived. A node whose
    parent is archived cannot be restored. Idempotent.
    """
    node = RoadmapNode.objects.select_for_update().get(pk=node.pk, user=user)
    if node.archived_at is None:
        return node
    if RoadmapNode.objects.filter(
        pk=node.parent_id, archived_at__isnull=False
    ).exists():
        raise ParentArchivedError()
    RoadmapNode.objects.filter(
        user=user,
        pk__in={node.pk, *_descendant_ids(node)},
        archived_at=node.archived_at,
    ).update(archived_at=None, updated_at=timezone.now())
    node.refresh_from_db()
    return node
