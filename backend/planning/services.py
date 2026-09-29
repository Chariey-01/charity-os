from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import DailyPlan, DailyPlanItem, PlanningEvent, Task


@transaction.atomic
def add_plan_item(*, user, plan, task, kind, position):
    plan = DailyPlan.objects.select_for_update().get(pk=plan.pk, user=user)
    task = Task.objects.select_for_update().get(pk=task.pk, user=user)
    if task.status != Task.Status.PLANNED:
        raise ValidationError("Only planned tasks can be added to a plan.")
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
        or item.task.status != Task.Status.PLANNED
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


@transaction.atomic
def transition_task(*, user, task, target):
    task = Task.objects.select_for_update().get(pk=task.pk, user=user)
    now = timezone.now()
    if target == Task.Status.COMPLETED:
        task.status, task.completed_at, task.skipped_at = target, now, None
    elif target == Task.Status.SKIPPED:
        task.status, task.completed_at, task.skipped_at = target, None, now
    elif target == Task.Status.PLANNED:
        task.status, task.completed_at, task.skipped_at = target, None, None
    else:
        raise ValidationError("Invalid task transition.")
    task.save(update_fields=("status", "completed_at", "skipped_at", "updated_at"))
    PlanningEvent.objects.create(
        user=user,
        event_type={
            "completed": "completed",
            "skipped": "skipped",
            "planned": "reopened",
        }[target],
        task=task,
        snapshot={"title": task.title},
    )
    return task
