"""Phase 0B, B5: manage.py check_data_integrity is read-only and finds problems."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.db import connection

from planning.models import Area, Task
from roadmaps.models import Roadmap, RoadmapNode
from scheduling.models import ScheduleEntry
from tests.history_graph import build_history

pytestmark = pytest.mark.django_db


def check():
    out = StringIO()
    call_command("check_data_integrity", stdout=out)
    return out.getvalue()


@pytest.fixture
def two_histories(django_user_model):
    users = [
        django_user_model.objects.create_user(f"{name}@example.com", "password")
        for name in ("one", "two")
    ]
    graphs = [build_history(user, label=str(i)) for i, user in enumerate(users)]
    return users, graphs


def test_a_consistent_database_passes(two_histories):
    output = check()

    assert output.count("OK ") == 5
    assert "All integrity checks passed." in output


def test_each_kind_of_problem_is_found_and_left_untouched(two_histories):
    (one, two), (graph_one, graph_two) = two_histories
    loop_a = graph_one["node"]
    loop_b = RoadmapNode.objects.create(
        user=one,
        roadmap=graph_one["roadmap"],
        parent=loop_a,
        title="B",
        node_type="item",
    )
    RoadmapNode.objects.filter(pk=loop_a.pk).update(parent=loop_b)  # legacy cycle
    other_roadmap = Roadmap.objects.create(user=one, title="Elsewhere")
    stray = RoadmapNode.objects.create(
        user=one, roadmap=other_roadmap, title="Stray", node_type="item"
    )
    RoadmapNode.objects.filter(pk=stray.pk).update(parent=graph_one["section"])
    Task.objects.filter(pk=graph_one["task"].pk).update(area=graph_two["area"])
    linked = ScheduleEntry.objects.get(user=one, focus_session__isnull=False)
    elsewhere = Area.objects.create(user=one, name="Elsewhere", slug="elsewhere")
    ScheduleEntry.objects.filter(pk=linked.pk).update(
        area=elsewhere, status="cancelled", closed_at=linked.start_at
    )

    with pytest.raises(CommandError) as failure:
        out = StringIO()
        call_command("check_data_integrity", stdout=out)
    output = out.getvalue()

    assert failure.value.returncode == 1
    assert "FOUND    2  roadmap parent cycles" in output
    assert str(loop_a.id) in output and str(loop_b.id) in output
    assert f"parents in another roadmap: {stray.id}" in output
    assert f"planning.Task.area:{graph_one['task'].id}" in output
    assert "attributed differently from their session" in output
    assert "status does not mirror their session" in output
    task = Task.objects.get(pk=graph_one["task"].pk)
    assert task.area_id == graph_two["area"].id  # reported, never repaired


def test_it_only_reads(two_histories):
    statements = []

    def record(execute, sql, params, many, context):
        statements.append(sql.strip().split()[0].upper())
        return execute(sql, params, many, context)

    with connection.execute_wrapper(record):
        check()

    # Under pytest the command's transaction is a savepoint inside the test's;
    # at top level SET TRANSACTION READ ONLY is the first statement.
    work = [kind for kind in statements if kind not in {"SAVEPOINT", "RELEASE"}]
    assert work[0] == "SET"
    assert set(work[1:]) == {"SELECT"}


def test_a_linked_pair_without_task_or_node_is_consistent(django_user_model):
    """Regression: a negated ORM comparison flagged two NULL tasks as different
    (found on a migrated copy of charityos_acceptance)."""
    from datetime import UTC, datetime, timedelta

    from execution.models import FocusSession

    user = django_user_model.objects.create_user("bare@example.com", "password")
    area = Area.objects.create(user=user, name="Learning", slug="learning")
    t0 = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
    session = FocusSession.objects.create(
        user=user,
        area=area,
        title="Study",
        is_deep_work=True,
        started_at=t0,
        ended_at=t0 + timedelta(hours=1),
        duration_seconds=3600,
        status="completed",
        timezone_snapshot="UTC",
        area_label_snapshot="Learning",
    )
    ScheduleEntry.objects.create(
        user=user,
        title="Study",
        area=area,
        focus_session=session,
        start_at=t0,
        end_at=t0 + timedelta(hours=1),
        timezone_name="UTC",
        local_date=t0.date(),
        tracking="focus",
        status="completed",
        closed_at=t0 + timedelta(hours=1),
    )

    assert "All integrity checks passed." in check()
