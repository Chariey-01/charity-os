"""Truthful progress (planning/progress.py, GET /api/v1/progress).

Every timestamp is set explicitly: the user is in Nairobi, weeks start on
Monday, "now" is Thursday 26 Nov 2026 and the week under test, W, is
Mon 16 - Sun 22 Nov. Later changes (reopening, archiving, deferring) are
made in the following week and must not rewrite W.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from rest_framework.test import APIClient

from execution.models import FocusSession
from planning.models import Area, DailyPlan, PlanningEvent, Task
from planning.progress import progress
from planning.services import (
    add_plan_item,
    archive_task,
    carry_over,
    record_due_change,
    transition_task,
)
from records.models import Accomplishment, Evidence
from roadmaps.models import Roadmap, RoadmapNode
from scheduling.models import ScheduleEntry

TZ = ZoneInfo("Africa/Nairobi")
W = date(2026, 11, 18)  # any day of Mon 16 - Sun 22 Nov


def at(day, hour=12):
    return datetime.combine(date.fromisoformat(day), time(hour), TZ)


NOW = at("2026-11-26", 15)

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    user = django_user_model.objects.create_user("owner@example.com", "pw-123456-abc")
    user.timezone = "Africa/Nairobi"
    user.week_starts_on = 1
    user.save()
    return user


@pytest.fixture
def learning(user):
    return Area.objects.create(
        user=user,
        name="Learning and Education",
        slug="learning-and-education",
        color="#1D4ED8",
    )


def make(user, title, *, created="2026-11-15", due=None, area=None):
    task = Task.objects.create(
        user=user,
        title=title,
        area=area,
        due_date=date.fromisoformat(due) if due else None,
    )
    Task.objects.filter(pk=task.pk).update(created_at=at(created, 8))
    task.refresh_from_db()
    return task


def _last_event_at(task, when):
    event = PlanningEvent.objects.filter(task=task).order_by("-created_at").first()
    PlanningEvent.objects.filter(pk=event.pk).update(created_at=when)


def complete(user, task, when):
    transition_task(user=user, task=task, target="done")
    _last_event_at(task, when)
    Task.objects.filter(pk=task.pk).update(completed_at=when)


def reopen(user, task, when):
    transition_task(user=user, task=task, target="todo")
    _last_event_at(task, when)


def defer(user, task, new_due, when):
    task.refresh_from_db()
    previous = task.due_date
    task.due_date = date.fromisoformat(new_due) if new_due else None
    task.save()
    record_due_change(user=user, task=task, previous=previous)
    _last_event_at(task, when)


def archive(user, task, when):
    archive_task(user=user, task=task)
    _last_event_at(task, when)
    Task.objects.filter(pk=task.pk).update(archived_at=when)


def entry(user, task, day, status="scheduled", area=None):
    start = at(day, 9)
    return ScheduleEntry.objects.create(
        user=user,
        title=task.title,
        task=task,
        area=area,
        start_at=start,
        end_at=start + timedelta(hours=1),
        timezone_name="Africa/Nairobi",
        local_date=date.fromisoformat(day),
        status=status,
        closed_at=None if status == "scheduled" else start + timedelta(hours=1),
    )


def weekly(user, day=W):
    return progress(user, day, now=NOW)["weekly"]


def test_with_no_tasks_there_is_no_percentage(user):
    data = progress(user, W, now=NOW)

    assert data["weekly"]["planned"] == 0
    assert data["weekly"]["completion_percent"] is None
    assert data["overall"]["completion_percent"] is None
    assert data["week"]["start"] == date(2026, 11, 16)
    assert data["week"]["end"] == date(2026, 11, 22)


def test_a_week_counts_its_planned_workload_once_per_task(user):
    due = make(user, "Due Wednesday", due="2026-11-18")
    both = make(user, "Due and scheduled", due="2026-11-19")
    entry(user, both, "2026-11-19")
    scheduled = make(user, "Scheduled only")
    entry(user, scheduled, "2026-11-20")
    make(user, "Due next week", due="2026-11-25")
    make(user, "No date")
    complete(user, due, at("2026-11-18", 10))

    week = weekly(user)

    assert week["planned"] == 3
    assert week["completed"] == 1
    assert week["outstanding"] == 2
    assert week["completion_percent"] == 33


def test_unplanned_completions_are_reported_but_not_in_the_percentage(user):
    planned = make(user, "Planned", due="2026-11-17")
    extra = make(user, "Came up")
    complete(user, planned, at("2026-11-17"))
    complete(user, extra, at("2026-11-19"))

    week = weekly(user)

    assert (week["planned"], week["completed"], week["completion_percent"]) == (
        1,
        1,
        100,
    )
    assert week["unplanned_completed"] == 1
    assert week["completed_total"] == 2


def test_monday_stays_in_mondays_week_whatever_happens_later(user):
    task = make(user, "Monday task", due="2026-11-16")
    complete(user, task, at("2026-11-16", 10))
    before = weekly(user)

    reopen(user, task, at("2026-11-24"))
    archive(user, task, at("2026-11-25"))
    after = weekly(user)

    assert before == after
    assert (after["planned"], after["completed"], after["completion_percent"]) == (
        1,
        1,
        100,
    )
    completed = progress(user, W, now=NOW)["tasks"]["completed"]
    assert [row["completed_on"] for row in completed] == [date(2026, 11, 16)]


def test_deferring_after_the_week_does_not_rewrite_it(user):
    task = make(user, "Essay", due="2026-11-20")
    defer(user, task, "2026-11-27", at("2026-11-24"))

    assert weekly(user)["outstanding"] == 1
    assert weekly(user, date(2026, 11, 25))["planned"] == 1


def test_deferring_during_the_week_moves_the_work_out_of_it(user):
    task = make(user, "Essay", due="2026-11-20")
    defer(user, task, "2026-11-25", at("2026-11-18"))

    assert weekly(user)["planned"] == 0
    assert weekly(user, date(2026, 11, 25))["planned"] == 1


def test_work_finished_before_the_week_is_not_part_of_it(user):
    early = make(user, "Done early", due="2026-11-18")
    complete(user, early, at("2026-11-13"))

    assert weekly(user)["planned"] == 0


def test_cancelled_and_archived_work_leaves_the_workload(user):
    cancelled = make(user, "Dropped", due="2026-11-18")
    transition_task(user=user, task=cancelled, target="cancelled")
    _last_event_at(cancelled, at("2026-11-17"))
    archived = make(user, "Removed", due="2026-11-18")
    archive(user, archived, at("2026-11-17"))

    assert weekly(user)["planned"] == 0


def test_tasks_created_after_the_week_are_not_in_it(user):
    make(user, "Created later", created="2026-11-24", due="2026-11-18")

    assert weekly(user)["planned"] == 0


def test_a_schedule_entry_moved_away_after_the_week_still_counts(user):
    task = make(user, "Call client")
    old = entry(user, task, "2026-11-19", status="rescheduled")
    moved = entry(user, task, "2026-11-25")
    ScheduleEntry.objects.filter(pk=moved.pk).update(
        rescheduled_from=old, created_at=at("2026-11-24")
    )

    assert weekly(user)["planned"] == 1


def test_a_schedule_entry_moved_away_during_the_week_does_not(user):
    task = make(user, "Call client")
    old = entry(user, task, "2026-11-19", status="rescheduled")
    moved = entry(user, task, "2026-11-25")
    ScheduleEntry.objects.filter(pk=moved.pk).update(
        rescheduled_from=old, created_at=at("2026-11-18")
    )

    assert weekly(user)["planned"] == 0


def test_daily_plan_items_count_until_carried_over(user):
    kept = make(user, "Kept")
    carried_late = make(user, "Carried after the week")
    carried_early = make(user, "Carried within the week")
    plan = DailyPlan.objects.create(
        user=user, local_date=date(2026, 11, 20), timezone_name="Africa/Nairobi"
    )
    add_plan_item(user=user, plan=plan, task=kept, kind="secondary")
    late = add_plan_item(user=user, plan=plan, task=carried_late, kind="secondary")
    early = add_plan_item(user=user, plan=plan, task=carried_early, kind="secondary")
    carry_over(user=user, item=late, destination_date=date(2026, 11, 23))
    PlanningEvent.objects.filter(event_type="carried_over", source_item=late).update(
        created_at=at("2026-11-23")
    )
    carry_over(user=user, item=early, destination_date=date(2026, 11, 30))
    PlanningEvent.objects.filter(event_type="carried_over", source_item=early).update(
        created_at=at("2026-11-20", 20)
    )

    assert weekly(user)["planned"] == 2


def test_the_previous_week_is_compared(user):
    last = make(user, "Last week", due="2026-11-11")
    complete(user, last, at("2026-11-11"))
    make(user, "This week", due="2026-11-18")

    data = progress(user, W, now=NOW)["weekly"]

    assert data["previous"]["planned"] == 1
    assert data["previous"]["completion_percent"] == 100
    assert data["completion_percent"] == 0


def test_overall_counts_active_work_only(user):
    done = make(user, "Done")
    complete(user, done, at("2026-11-20"))
    make(user, "Overdue", due="2026-11-20")
    make(user, "Due today", due="2026-11-26")
    make(user, "Open")
    cancelled = make(user, "Cancelled")
    transition_task(user=user, task=cancelled, target="cancelled")
    gone = make(user, "Archived")
    archive_task(user=user, task=gone)

    overall = progress(user, W, now=NOW)["overall"]

    assert overall["completed"] == 1
    assert overall["remaining"] == 3
    assert overall["completion_percent"] == 25
    assert (overall["overdue"], overall["due_today"]) == (1, 1)


def test_workstreams_split_completed_work_and_time_separately(user, learning):
    admin = Area.objects.create(
        user=user, name="Personal Administration", slug="personal-administration"
    )
    for title in ("Course", "Exercise set"):
        complete(user, make(user, title, area=learning), at("2026-11-17"))
    complete(user, make(user, "Pay rent", area=admin), at("2026-11-18"))
    FocusSession.objects.create(
        user=user,
        area=admin,
        title="Invoices",
        is_deep_work=False,
        started_at=at("2026-11-19", 9),
        ended_at=at("2026-11-19", 11),
        duration_seconds=7200,
        status="completed",
        timezone_snapshot="Africa/Nairobi",
        area_label_snapshot=admin.name,
    )

    streams = progress(user, W, now=NOW)["workstreams"]

    assert [(row["label"], row["count"]) for row in streams["completed_tasks"]] == [
        ("Learning and Education", 2),
        ("Personal Administration", 1),
    ]
    assert [(row["label"], row["actual_minutes"]) for row in streams["time"]] == [
        ("Personal Administration", 120)
    ]


def test_accomplishments_describe_the_week(user, learning):
    roadmap = Roadmap.objects.create(user=user, title="TypeScript")
    node = RoadmapNode.objects.create(
        user=user, roadmap=roadmap, title="Generics", node_type="item"
    )
    RoadmapNode.objects.filter(pk=node.pk).update(
        state="completed", completed_at=at("2026-11-19")
    )
    task = make(user, "Generics exercise", area=learning)
    Task.objects.filter(pk=task.pk).update(roadmap_item=node)
    complete(user, task, at("2026-11-19"))
    Evidence.objects.create(user=user, kind="note", text="Notes", task=task)
    Evidence.objects.filter(task=task).update(created_at=at("2026-11-19"))
    Accomplishment.objects.create(
        user=user,
        title="Shipped",
        local_date=date(2026, 11, 21),
        timezone_name="Africa/Nairobi",
    )
    Accomplishment.objects.create(
        user=user,
        title="Later",
        local_date=date(2026, 11, 24),
        timezone_name="Africa/Nairobi",
    )

    done = progress(user, W, now=NOW)["accomplishments"]

    assert [row["title"] for row in done["completed_tasks"]] == ["Generics exercise"]
    assert [(row["title"], row["roadmap"]) for row in done["milestones"]] == [
        ("Generics", "TypeScript")
    ]
    assert done["roadmaps_advanced"] == ["TypeScript"]
    assert done["learning"] == {
        "roadmap_items_completed": 1,
        "roadmap_tasks_completed": 1,
    }
    assert done["evidence_recorded"] == 1
    assert [row["title"] for row in done["accomplishments"]] == ["Shipped"]


def test_the_endpoint(user):
    client = APIClient()
    client.force_authenticate(user)
    make(user, "Essay", due="2026-11-18")

    response = client.get("/api/v1/progress?week=2026-11-18")
    bad = client.get("/api/v1/progress?week=next-tuesday")
    anonymous = APIClient().get("/api/v1/progress")

    assert response.status_code == 200
    body = response.json()
    assert body["week"]["start"] == "2026-11-16"
    assert body["weekly"]["planned"] == 1
    assert set(body) == {
        "today",
        "week",
        "overall",
        "weekly",
        "workstreams",
        "tasks",
        "accomplishments",
    }
    assert bad.status_code == 400
    assert anonymous.json()["error"]["code"] == "not_authenticated"


def test_another_users_records_never_appear(user, django_user_model, learning):
    other = django_user_model.objects.create_user("other@example.com", "pw-123456-abc")
    other.timezone = "Africa/Nairobi"
    other.save()
    theirs = make(other, "Their task", due="2026-11-18")
    complete(other, theirs, at("2026-11-18"))
    entry(other, make(other, "Their scheduled task"), "2026-11-19")
    their_area = Area.objects.create(user=other, name="Theirs", slug="theirs")
    FocusSession.objects.create(
        user=other,
        area=their_area,
        title="Theirs",
        is_deep_work=False,
        started_at=at("2026-11-19", 9),
        ended_at=at("2026-11-19", 10),
        duration_seconds=3600,
        status="completed",
        timezone_snapshot="Africa/Nairobi",
        area_label_snapshot="Theirs",
    )

    data = progress(user, W, now=NOW)

    assert data["weekly"]["planned"] == data["weekly"]["completed_total"] == 0
    assert data["overall"]["completed"] == 0
    assert data["workstreams"] == {"completed_tasks": [], "time": []}
    assert data["accomplishments"]["focus_minutes"] == 0


def test_reopened_later_in_the_same_week_is_not_completed(user):
    task = make(user, "Essay", due="2026-11-18")
    complete(user, task, at("2026-11-17"))
    reopen(user, task, at("2026-11-19"))

    week = weekly(user)

    assert (week["planned"], week["completed"], week["outstanding"]) == (1, 0, 1)


def test_archiving_during_the_week_removes_it_archiving_afterwards_does_not(user):
    during = make(user, "Archived Wednesday", due="2026-11-17")
    complete(user, during, at("2026-11-17"))
    archive(user, during, at("2026-11-18"))
    after = make(user, "Archived next week", due="2026-11-17")
    complete(user, after, at("2026-11-17"))
    archive(user, after, at("2026-11-24"))

    week = progress(user, W, now=NOW)

    assert [row["title"] for row in week["tasks"]["completed"]] == [
        "Archived next week"
    ]
    assert week["weekly"]["planned"] == 1


def test_one_task_planned_three_ways_counts_once(user):
    task = make(user, "Client call", due="2026-11-19")
    entry(user, task, "2026-11-18")
    entry(user, task, "2026-11-19")
    complete(user, task, at("2026-11-19", 16))

    week = weekly(user)

    assert (week["planned"], week["completed"], week["completed_total"]) == (1, 1, 1)
