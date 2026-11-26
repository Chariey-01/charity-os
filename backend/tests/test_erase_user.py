"""manage.py erase_user: dry run first, exact, and never touches other users."""

from io import StringIO

import pytest
from django.apps import apps
from django.core.management import CommandError, call_command

from planning.models import Task
from tests.history_graph import OWNED_MODELS, build_history, owned_counts

pytestmark = pytest.mark.django_db


@pytest.fixture
def people(django_user_model):
    keep = django_user_model.objects.create_user("keep@example.com", "password")
    gone = django_user_model.objects.create_user("Gone@Example.com", "password")
    build_history(keep, label="k")
    graph = build_history(gone, label="g")
    return keep, gone, graph


def rows_of(user_id):
    snapshot = {}
    for name in OWNED_MODELS:
        model = apps.get_model(name)
        columns = [field.attname for field in model._meta.concrete_fields]
        snapshot[name] = list(
            model.objects.filter(user_id=user_id).order_by("pk").values_list(*columns)
        )
    return snapshot


def erase(*args):
    out = StringIO()
    call_command("erase_user", *args, stdout=out)
    return out.getvalue()


def test_dry_run_is_the_default_and_lists_exactly_what_would_go(people):
    keep, gone, _ = people
    before = rows_of(gone.pk)

    output = erase("gone@example.com")

    assert "DRY RUN: nothing was deleted." in output
    assert rows_of(gone.pk) == before
    for name, count in owned_counts(gone).items():
        assert f"  {name}" in output and str(count) in output
    assert "users.User " in output


def test_wrong_confirmation_deletes_nothing(people):
    _, gone, _ = people
    before = rows_of(gone.pk)

    with pytest.raises(CommandError, match="does not match"):
        erase("gone@example.com", "--confirm", "keep@example.com")

    assert rows_of(gone.pk) == before


def test_unknown_account_is_an_error(people):
    with pytest.raises(CommandError, match="No account"):
        erase("nobody@example.com")


def test_confirmed_erasure_removes_everything_of_one_user_only(
    people, django_user_model
):
    keep, gone, _ = people
    kept_before = rows_of(keep.pk)
    gone_id = gone.pk
    total = sum(owned_counts(gone).values()) + 1  # their rows plus the account

    output = erase("gone@example.com", "--confirm", "GONE@example.com")

    assert f"Erased gone@example.com: {total} rows." in output  # stored lowercased
    assert not django_user_model.objects.filter(pk=gone_id).exists()
    assert set(owned_counts(gone_id).values()) == {0}
    assert rows_of(keep.pk) == kept_before
    assert django_user_model.objects.filter(pk=keep.pk).exists()


def test_refuses_when_another_users_record_points_into_the_account(people):
    keep, gone, graph = people
    # Inconsistent legacy data: keep's task filed under gone's category.
    Task.objects.create(user=keep, title="Cross-linked", area=graph["area"])
    before = (rows_of(gone.pk), rows_of(keep.pk))

    with pytest.raises(CommandError, match="Refusing"):
        erase("gone@example.com", "--confirm", "gone@example.com")

    assert (rows_of(gone.pk), rows_of(keep.pk)) == before


def test_any_difference_from_the_plan_rolls_everything_back(people, monkeypatch):
    from users.management.commands import erase_user as command

    keep, gone, _ = people
    before = (rows_of(gone.pk), rows_of(keep.pk))
    real_plan = command.erasure_plan
    monkeypatch.setattr(
        command,
        "erasure_plan",
        lambda user: {**real_plan(user), "planning.Task": 99},
    )

    with pytest.raises(CommandError, match="Rolled back"):
        erase("gone@example.com", "--confirm", "gone@example.com")

    assert (rows_of(gone.pk), rows_of(keep.pk)) == before
