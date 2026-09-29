from django.db.models import Sum

from execution.models import FocusSession
from planning.models import Task

from .models import RoadmapNode


def node_detail(node):
    task_ids = list(node.tasks.values_list("id", flat=True))
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
        "time_invested_seconds": seconds,
        "linked_task_ids": [str(value) for value in task_ids],
        "resources": [
            {"id": str(resource.id), "label": resource.label, "url": resource.url}
            for resource in node.resources.order_by("position")
        ],
        "evidence_count": node.evidence.count(),
        "prerequisite_ids": [
            str(edge.prerequisite_id) for edge in node.prerequisite_edges.all()
        ],
        "children": [
            node_detail(child) for child in node.children.order_by("position", "title")
        ],
    }


def roadmap_tree(roadmap):
    return [
        node_detail(node)
        for node in roadmap.nodes.filter(parent__isnull=True).order_by(
            "position", "title"
        )
    ]


def next_actions(user, limit=5):
    candidates = (
        RoadmapNode.objects.filter(
            user=user,
            node_type=RoadmapNode.NodeType.ITEM,
            state=RoadmapNode.State.PLANNED,
        )
        .select_related("roadmap")
        .prefetch_related("prerequisite_edges__prerequisite", "tasks")
    )
    ranked = []
    for node in candidates:
        prerequisites = list(node.prerequisite_edges.all())
        if any(
            edge.prerequisite.state != RoadmapNode.State.COMPLETED
            for edge in prerequisites
        ):
            continue
        tasks = list(
            node.tasks.filter(status=Task.Status.PLANNED).order_by(
                "-priority", "created_at"
            )
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
