from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import DailyPlan, DailyPlanItem, PlanningEvent, Task


@transaction.atomic
def add_plan_item(*, user, plan, task, kind, position):
    plan = DailyPlan.objects.select_for_update().get(pk=plan.pk, user=user)
    task = Task.objects.select_for_update().get(pk=task.pk, user=user)
    if task.status not in Task.OPEN_STATUSES:
        raise ValidationError("Only open tasks can be added to a plan.")
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
    position = destination.items.filter(state=DailyPlanItem.State.CURRENT).count()
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
