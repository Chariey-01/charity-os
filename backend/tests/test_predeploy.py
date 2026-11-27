"""The pre-deploy step and its approval gate for migrations over real data."""

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from api.management.commands import predeploy


@pytest.fixture
def gate(monkeypatch):
    """Replace checks, the pending list, accounts and migrate with recorders."""
    state = {"labels": [], "accounts": False, "migrated": 0, "checked": 0}

    def check():
        state["checked"] += 1

    def migrate():
        state["migrated"] += 1

    monkeypatch.setattr(predeploy, "run_checks", check)
    monkeypatch.setattr(predeploy, "pending_migrations", lambda: state["labels"])
    monkeypatch.setattr(predeploy, "has_accounts", lambda: state["accounts"])
    monkeypatch.setattr(predeploy, "migrate", migrate)
    monkeypatch.delenv(predeploy.APPROVAL_VARIABLE, raising=False)
    return state


def test_nothing_to_migrate_only_checks(gate, capsys):
    call_command("predeploy")
    assert (gate["checked"], gate["migrated"]) == (1, 0)
    assert "no migrations to apply" in capsys.readouterr().out


def test_first_deployment_migrates_an_empty_database(gate):
    gate["labels"] = ["users.0001_initial", "planning.0001_initial"]
    call_command("predeploy")
    assert gate["migrated"] == 1


def test_migrations_over_real_accounts_need_the_matching_approval(gate, monkeypatch):
    gate["labels"] = ["planning.0012_example"]
    gate["accounts"] = True
    with pytest.raises(CommandError) as refused:
        call_command("predeploy")
    assert gate["migrated"] == 0
    code = predeploy.approval_code(["planning.0012_example"])
    assert "planning.0012_example" in str(refused.value)
    assert f"CHARITYOS_APPROVE_MIGRATIONS={code}" in str(refused.value)

    # An approval for another set of migrations does not carry over.
    monkeypatch.setenv(
        predeploy.APPROVAL_VARIABLE, predeploy.approval_code(["planning.0011_x"])
    )
    with pytest.raises(CommandError):
        call_command("predeploy")
    assert gate["migrated"] == 0

    monkeypatch.setenv(predeploy.APPROVAL_VARIABLE, code)
    call_command("predeploy")
    assert gate["migrated"] == 1


@pytest.mark.django_db
def test_real_helpers_see_a_fully_migrated_database_and_its_accounts():
    assert predeploy.pending_migrations() == []
    assert predeploy.has_accounts() is False
    get_user_model().objects.create_user(email="owner@example.com", password="x")
    assert predeploy.has_accounts() is True
