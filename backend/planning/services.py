from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import DailyPlan, DailyPlanItem, PlanningEvent, Task


def next_position(plan):
    """One past the plan's last current item, so appends never collide."""
    last = plan.items.filter(state=DailyPlanItem.State.CURRENT).aggregate(
        last=Max("position")
    )["last"]
    return 0 if last is None else last + 1


@transaction.atomic
def add_plan_item(*, user, plan, task, kind, position=None):
    plan = DailyPlan.objects.select_for_update().get(pk=plan.pk, user=user)
    task = Task.objects.select_for_update().get(pk=task.pk, user=user)
    if task.status not in Task.OPEN_STATUSES:
        raise ValidationError("Only open tasks can be added to a plan.")
    if DailyPlanItem.objects.filter(
        task=task, state=DailyPlanItem.State.CURRENT
    ).exists():
        raise ValidationError(
            {"task": "This task is already on a plan. Carry it over instead."}
        )
    if position is None:
        position = next_position(plan)
    elif plan.items.filter(
        state=DailyPlanItem.State.CURRENT, position=position
    ).exists():
        raise ValidationError({"position": "Another item already holds this position."})
    if (
        kind == DailyPlanItem.Kind.PRIMARY
        and plan.items.filter(kind=kind, state=DailyPlanItem.State.CURRENT).count() >= 3
    ):
        raise ValidationError("A daily plan can have at most three primary outcomes.")
    item = DailyPlanItem.objects.create(
        user=user,
        plan=plan,
        task=task,
        kind=kind,
        position=position,
        title_snapshot=task.title,
        area_label_snapshot=task.area.name if task.area else "",
    )
    PlanningEvent.objects.create(
        user=user,
        event_type=PlanningEvent.EventType.PLANNED,
        task=task,
        destination_item=item,
        snapshot={"title": task.title},
    )
    return item


@transaction.atomic
def carry_over(*, user, item, destination_date):
    item = (
        DailyPlanItem.objects.select_for_update()
        .select_related("task", "plan")
        .get(pk=item.pk, user=user)
    )
    existing = (
        PlanningEvent.objects.filter(
            user=user, event_type=PlanningEvent.EventType.CARRIED_OVER, source_item=item
        )
        .select_related("destination_item")
        .first()
    )
    if existing:
        return existing.destination_item
    if (
        item.state != DailyPlanItem.State.CURRENT
        or item.task.status not in Task.OPEN_STATUSES
    ):
        raise ValidationError("Only a current unfinished task can be carried forward.")
    destination, _ = DailyPlan.objects.get_or_create(
        user=user,
        local_date=destination_date,
        defaults={"timezone_name": item.plan.timezone_name},
    )
    destination = DailyPlan.objects.select_for_update().get(pk=destination.pk)
    position = next_position(destination)
    item.state = DailyPlanItem.State.CARRIED_FORWARD
    item.save(update_fields=("state", "updated_at"))
    new_item = DailyPlanItem.objects.create(
        user=user,
        plan=destination,
        task=item.task,
        kind=item.kind,
        position=position,
        title_snapshot=item.title_snapshot,
        area_label_snapshot=item.area_label_snapshot,
    )
    PlanningEvent.objects.create(
        user=user,
        event_type=PlanningEvent.EventType.CARRIED_OVER,
        task=item.task,
        source_item=item,
        destination_item=new_item,
        snapshot={"from": str(item.plan.local_date), "to": str(destination_date)},
    )
    return new_item


def _event_for(previous, target):
    """History event name for a transition.

    The names that existed before the workflow (completed, skipped,
    reopened) are still used for those transitions so history reads the
    same; moves between open states are recorded as status_changed.
    """
    if target == Task.Status.DONE:
        return PlanningEvent.EventType.COMPLETED
    if target == Task.Status.CANCELLED:
        return PlanningEvent.EventType.SKIPPED
    if previous not in Task.OPEN_STATUSES:
        return PlanningEvent.EventType.REOPENED
    return PlanningEvent.EventType.STATUS_CHANGED


@transaction.atomic
def transition_task(*, user, task, target, reason=""):
    """Move a task to ``target`` (any workflow status or a legacy name).

    Idempotent: a task already in ``target`` is returned unchanged and no
    event is written, so a repeated "complete" keeps the original
    completion time. Every real change appends a PlanningEvent with the
    previous and new status; existing events are never modified.
    """
    target = Task.LEGACY_TO_STATUS.get(target, target)
    if target not in Task.Status.values:
        raise ValidationError({"status": f"Unknown task status: {target}."})
    task = Task.objects.select_for_update().get(pk=task.pk, user=user)
    previous = task.status
    if previous == target:
        return task
    now = timezone.now()
    task.status = target
    task.completed_at = now if target == Task.Status.DONE else None
    task.cancelled_at = now if target == Task.Status.CANCELLED else None
    task.save(update_fields=("status", "completed_at", "cancelled_at", "updated_at"))
    snapshot = {"title": task.title, "from": previous, "to": target}
    if reason.strip():
        snapshot["reason"] = reason.strip()
    PlanningEvent.objects.create(
        user=user,
        event_type=_event_for(previous, target),
        task=task,
        snapshot=snapshot,
    )
    return task


def record_due_change(*, user, task, previous):
    """Append a due_changed event when ``task.due_date`` is not ``previous``.

    Due dates are mutable, so a past week's workload can only be
    reconstructed from these append-only events (planning/progress.py).
    """
    if previous == task.due_date:
        return None
    return PlanningEvent.objects.create(
        user=user,
        event_type=PlanningEvent.EventType.DUE_CHANGED,
        task=task,
        snapshot={
            "title": task.title,
            "from": previous.isoformat() if previous else None,
            "to": task.due_date.isoformat() if task.due_date else None,
        },
    )


@transaction.atomic
def archive_task(*, user, task):
    """Hide a task from working views. Nothing is deleted.

    Its plan items, focus sessions, schedule entries, evidence and history
    stay linked and keep counting wherever they counted before. Idempotent:
    archiving an archived task changes nothing and writes no event.
    """
    task = Task.objects.select_for_update().get(pk=task.pk, user=user)
    if task.archived_at is not None:
        return task
    task.archived_at = timezone.now()
    task.save(update_fields=("archived_at", "updated_at"))
    PlanningEvent.objects.create(
        user=user,
        event_type=PlanningEvent.EventType.ARCHIVED,
        task=task,
        snapshot={"title": task.title, "status": task.status},
    )
    return task


@transaction.atomic
def restore_task(*, user, task):
    """Return an archived task to working views. Idempotent."""
    task = Task.objects.select_for_update().get(pk=task.pk, user=user)
    if task.archived_at is None:
        return task
    task.archived_at = None
    task.save(update_fields=("archived_at", "updated_at"))
    PlanningEvent.objects.create(
        user=user,
        event_type=PlanningEvent.EventType.RESTORED,
        task=task,
        snapshot={"title": task.title, "status": task.status},
    )
    return task


@transaction.atomic
def remove_plan_item(*, user, item, reason=""):
    """Take an item off its plan without deleting anything.

    The item stays in the plan's history in state "removed" and a REMOVED
    event records it. Only a current item can be removed; removing a removed
    item changes nothing.
    """
    item = (
        DailyPlanItem.objects.select_for_update(of=("self",))
        .select_related("plan", "task")
        .get(pk=item.pk, user=user)
    )
    if item.state == DailyPlanItem.State.REMOVED:
        return item
    if item.state != DailyPlanItem.State.CURRENT:
        raise ValidationError("Only a current plan item can be removed.")
    item.state = DailyPlanItem.State.REMOVED
    item.save(update_fields=("state", "updated_at"))
    snapshot = {"title": item.title_snapshot, "date": str(item.plan.local_date)}
    if reason.strip():
        snapshot["reason"] = reason.strip()
    PlanningEvent.objects.create(
        user=user,
        event_type=PlanningEvent.EventType.REMOVED,
        task=item.task,
        source_item=item,
        snapshot=snapshot,
    )
    return item


@transaction.atomic
def add_node_to_today(*, user, node, local_date, focus=None):
    """Plan a roadmap item for a day in one transaction (Phase 0B, B4).

    Reuses the item's open task (repeated taps used to create duplicates) and
    creates one only when there is none. Puts it on the day's plan after the
    last item, or carries it over if it is planned for another day. With
    ``focus`` ({"id": uuid, "area": Area}) it also starts the focus session.
    Any failure rolls back every write: no stray task, plan or plan item.
    """
    from execution.services import start_session
    from roadmaps.models import RoadmapNode

    node = (
        RoadmapNode.objects.select_for_update(of=("self",))
        .select_related("roadmap")
        .get(pk=node.pk, user=user)
    )
    if node.archived_at is not None or node.roadmap.archived_at is not None:
        raise ValidationError("This roadmap item is archived. Restore it first.")
    plan, _ = DailyPlan.objects.get_or_create(
        user=user, local_date=local_date, defaults={"timezone_name": user.timezone}
    )
    plan = DailyPlan.objects.select_for_update().get(pk=plan.pk)
    task = (
        Task.objects.filter(
            user=user,
            roadmap_item=node,
            status__in=Task.OPEN_STATUSES,
            archived_at__isnull=True,
        )
        .order_by("created_at")
        .first()
    )
    created_task = task is None
    if created_task:
        task = Task.objects.create(
            user=user, title=node.title, roadmap_item=node, is_deep_work_default=True
        )
    current = (
        DailyPlanItem.objects.filter(task=task, state=DailyPlanItem.State.CURRENT)
        .select_related("plan")
        .first()
    )
    if current is not None and current.plan_id == plan.pk:
        item = current
    elif current is not None:
        item = carry_over(user=user, item=current, destination_date=local_date)
    else:
        item = add_plan_item(
            user=user, plan=plan, task=task, kind=DailyPlanItem.Kind.SECONDARY
        )
    session = None
    if focus is not None:
        area = focus["area"]
        if area.user_id != user.id or area.archived_at is not None:
            raise ValidationError({"area": "Choose one of your active categories."})
        session = start_session(
            user=user,
            session_id=focus["id"],
            area=area,
            title=task.title,
            is_deep_work=True,
            task=task,
            roadmap_item=node,
        )
    return {
        "task": task,
        "item": item,
        "session": session,
        "created_task": created_task,
    }
