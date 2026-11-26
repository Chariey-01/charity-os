"""One of every history-bearing record, all linked together, for one user.

``registry`` is ``django.apps.apps`` for today's models or a migration
state's apps for historical models, so the same graph serves model tests,
migration tests and the erasure command's tests.
"""

from datetime import UTC, date, datetime, timedelta

from django.apps import apps as current_apps

T0 = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
DAY = date(2026, 11, 20)

# Every model that holds per-user data (has a ``user`` foreign key).
OWNED_MODELS = (
    "users.UserPreferences",
    "challenges.Challenge",
    "planning.Area",
    "planning.DailyCapacity",
    "planning.Task",
    "planning.DailyPlan",
    "planning.DailyPlanItem",
    "planning.PlanningEvent",
    "roadmaps.Roadmap",
    "roadmaps.RoadmapNode",
    "roadmaps.RoadmapNodePrerequisite",
    "roadmaps.RoadmapResource",
    "execution.FocusSession",
    "execution.SessionPause",
    "execution.FocusSessionCorrection",
    "records.Accomplishment",
    "records.Evidence",
    "reflections.DailyReflection",
    "reflections.WeeklyReview",
    "reflections.ReflectionRevision",
    "health.SleepLog",
    "health.ExerciseLog",
    "health.MealLog",
    "health.DailyWaterTotal",
    "health.DailyNutritionRating",
    "scheduling.ScheduleEntry",
)


def build_history(user, registry=current_apps, label="a"):
    def model(name):
        return registry.get_model(name)

    model("users.UserPreferences").objects.get_or_create(user=user)
    area = model("planning.Area").objects.create(
        user=user, name=f"Study {label}", slug=f"study-{label}"
    )
    challenge = model("challenges.Challenge").objects.create(
        user=user,
        name=f"Challenge {label}",
        start_date=DAY,
        end_date=DAY + timedelta(days=95),
        status="active",
    )
    model("planning.DailyCapacity").objects.create(
        user=user, local_date=DAY, timezone_name="UTC", available_minutes=300
    )
    roadmap = model("roadmaps.Roadmap").objects.create(
        user=user, title="Python", area=area
    )
    Node = model("roadmaps.RoadmapNode")
    section = Node.objects.create(
        user=user, roadmap=roadmap, title="Basics", node_type="section"
    )
    node = Node.objects.create(
        user=user, roadmap=roadmap, parent=section, title="Loops", node_type="item"
    )
    first = Node.objects.create(
        user=user, roadmap=roadmap, title="Syntax", node_type="item"
    )
    model("roadmaps.RoadmapNodePrerequisite").objects.create(
        user=user, node=node, prerequisite=first
    )
    model("roadmaps.RoadmapResource").objects.create(
        user=user, node=node, label="Docs", url="https://docs.python.org"
    )
    task = model("planning.Task").objects.create(
        user=user, title="Practise loops", area=area, roadmap_item=node
    )
    plan = model("planning.DailyPlan").objects.create(
        user=user, local_date=DAY, timezone_name="UTC", challenge=challenge
    )
    item = model("planning.DailyPlanItem").objects.create(
        user=user, plan=plan, task=task, title_snapshot=task.title
    )
    model("planning.PlanningEvent").objects.create(
        user=user, event_type="planned", task=task, destination_item=item
    )
    session = model("execution.FocusSession").objects.create(
        user=user,
        area=area,
        task=task,
        roadmap_item=node,
        title="Loops",
        is_deep_work=True,
        started_at=T0,
        ended_at=T0 + timedelta(hours=1),
        duration_seconds=3300,
        status="completed",
        timezone_snapshot="UTC",
        area_label_snapshot=area.name,
    )
    model("execution.SessionPause").objects.create(
        user=user,
        session=session,
        started_at=T0 + timedelta(minutes=20),
        ended_at=T0 + timedelta(minutes=25),
    )
    model("execution.FocusSessionCorrection").objects.create(
        user=user, session=session, reason="Started late", before={}, after={}
    )
    win = model("records.Accomplishment").objects.create(
        user=user,
        local_date=DAY,
        timezone_name="UTC",
        title="Loops done",
        area=area,
        task=task,
        session=session,
    )
    Evidence = model("records.Evidence")
    for parent in ({"task": task}, {"session": session}, {"roadmap_node": node}):
        Evidence.objects.create(user=user, kind="note", text="proof", **parent)
    Evidence.objects.create(user=user, kind="note", text="proof", accomplishment=win)
    Entry = model("scheduling.ScheduleEntry")
    moved = Entry.objects.create(
        user=user,
        title="Loops",
        area=area,
        task=task,
        roadmap_node=node,
        start_at=T0 - timedelta(days=1),
        end_at=T0 - timedelta(days=1) + timedelta(hours=1),
        timezone_name="UTC",
        local_date=DAY - timedelta(days=1),
        status="rescheduled",
        closed_at=T0 - timedelta(days=1),
    )
    Entry.objects.create(
        user=user,
        title="Loops",
        area=area,
        task=task,
        roadmap_node=node,
        focus_session=session,
        rescheduled_from=moved,
        start_at=T0,
        end_at=T0 + timedelta(hours=1),
        timezone_name="UTC",
        local_date=DAY,
        tracking="focus",
        status="completed",  # mirrors its completed session, as the app keeps it
        closed_at=T0 + timedelta(hours=1),
    )
    model("health.ExerciseLog").objects.create(
        user=user,
        session=session,
        started_at=T0 + timedelta(hours=3),
        ended_at=T0 + timedelta(hours=4),
        activity="Run",
    )
    model("health.SleepLog").objects.create(
        user=user,
        started_at=T0 - timedelta(hours=9),
        woke_at=T0 - timedelta(hours=1),
        timezone_name="UTC",
        wake_local_date=DAY,
    )
    model("health.MealLog").objects.create(
        user=user,
        local_date=DAY,
        timezone_name="UTC",
        meal_type="lunch",
        description="Rice",
    )
    model("health.DailyWaterTotal").objects.create(
        user=user, local_date=DAY, timezone_name="UTC", total_ml=1500
    )
    model("health.DailyNutritionRating").objects.create(
        user=user, local_date=DAY, timezone_name="UTC", rating=4
    )
    reflection = model("reflections.DailyReflection").objects.create(
        user=user, local_date=DAY, timezone_name="UTC", went_well="Focus"
    )
    try:  # absent in migration states before reflections.0003
        Revision = model("reflections.ReflectionRevision")
    except LookupError:
        Revision = None
    if Revision is not None:
        Revision.objects.create(
            user=user,
            daily_reflection=reflection,
            version=1,
            content={"went_well": "First words"},
        )
    model("reflections.WeeklyReview").objects.create(
        user=user,
        week_start_date=date(2026, 11, 16),
        week_end_date=date(2026, 11, 22),
        timezone_name="UTC",
    )
    return {
        "area": area,
        "challenge": challenge,
        "roadmap": roadmap,
        "section": section,
        "node": node,
        "task": task,
        "plan": plan,
        "session": session,
        "win": win,
    }


def _models(registry, names):
    for name in names:
        try:
            yield name, registry.get_model(name)
        except LookupError:  # not yet created in this migration state
            continue


def owned_counts(user, registry=current_apps):
    return {
        name: model.objects.filter(user=user).count()
        for name, model in _models(registry, OWNED_MODELS)
    }


def table_rows(registry=current_apps):
    """Every column of every row in every owned table (plus users)."""
    snapshot = {}
    for name, model in _models(registry, ("users.User", *OWNED_MODELS)):
        columns = [field.attname for field in model._meta.concrete_fields]
        snapshot[name] = list(model.objects.order_by("pk").values_list(*columns))
    return snapshot
