# ruff: noqa: DJ008
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from planning.models import Area


class Roadmap(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="roadmaps"
    )
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    area = models.ForeignKey(
        Area, null=True, blank=True, on_delete=models.SET_NULL, related_name="roadmaps"
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def progress(self):
        eligible = self.nodes.filter(node_type="item").exclude(state="skipped")
        total = eligible.count()
        completed = eligible.filter(state="completed").count()
        return {
            "completed_eligible_items": completed,
            "eligible_items": total,
            "skipped_items": self.nodes.filter(
                node_type="item", state="skipped"
            ).count(),
            "progress_ratio": completed / total if total else 0,
        }


class RoadmapNode(models.Model):
    class NodeType(models.TextChoices):
        SECTION = "section", "Section"
        TOPIC = "topic", "Topic"
        ITEM = "item", "Item"

    class State(models.TextChoices):
        PLANNED = "planned", "Planned"
        COMPLETED = "completed", "Completed"
        SKIPPED = "skipped", "Skipped"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="roadmap_nodes"
    )
    roadmap = models.ForeignKey(Roadmap, on_delete=models.CASCADE, related_name="nodes")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True, default="")
    node_type = models.CharField(max_length=10, choices=NodeType.choices)
    state = models.CharField(
        max_length=12, choices=State.choices, default=State.PLANNED
    )
    position = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(parent=models.F("id")),
                name="roadmaps_node_not_self_parent",
            )
        ]

    def clean(self):
        if self.parent and (
            self.parent.roadmap_id != self.roadmap_id
            or self.parent.user_id != self.user_id
        ):
            raise ValidationError({"parent": "Parent must belong to the same roadmap."})
        cursor = self.parent
        while cursor:
            if cursor.pk == self.pk:
                raise ValidationError({"parent": "A node cannot be its own ancestor."})
            cursor = cursor.parent


class RoadmapNodePrerequisite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    node = models.ForeignKey(
        RoadmapNode, on_delete=models.CASCADE, related_name="prerequisite_edges"
    )
    prerequisite = models.ForeignKey(
        RoadmapNode, on_delete=models.CASCADE, related_name="dependent_edges"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("node", "prerequisite"), name="roadmaps_prerequisite_unique"
            ),
            models.CheckConstraint(
                condition=~models.Q(node=models.F("prerequisite")),
                name="roadmaps_prerequisite_not_self",
            ),
        ]


class RoadmapResource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    node = models.ForeignKey(
        RoadmapNode, on_delete=models.CASCADE, related_name="resources"
    )
    label = models.CharField(max_length=120)
    url = models.URLField()
    position = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("node", "position"), name="roadmaps_resource_position_unique"
            )
        ]
