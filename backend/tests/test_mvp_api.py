import uuid
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from execution.models import FocusSession
from execution.services import end_session, pause_session, resume_session, start_session
from planning.models import Area, DailyPlan, DailyPlanItem, Task
from planning.services import add_plan_item, carry_over

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return get_user_model().objects.create_user(
        "owner@example.com", "password", timezone="Africa/Nairobi"
    )


@pytest.fixture
def area(owner):
    return Area.objects.create(user=owner, name="Engineering", slug="engineering")


def test_session_auth_and_cross_user_isolation(owner):
    other = get_user_model().objects.create_user("other@example.com", "password")
    Area.objects.create(user=other, name="Private", slug="private")
    client = APIClient(enforce_csrf_checks=True)
    csrf_response = client.get("/api/v1/auth/csrf")
    token = csrf_response.cookies["csrftoken"].value
    response = client.post(
        "/api/v1/auth/login",
        {"email": owner.email, "password": "password"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200
    assert client.get("/api/v1/areas").json() == []
    token = client.cookies["csrftoken"].value
    assert client.post("/api/v1/auth/logout", HTTP_X_CSRFTOKEN=token).status_code == 204
    assert client.get("/api/v1/areas").status_code in (401, 403)


def test_plan_primary_limit_and_carry_over(owner, area):
    plan = DailyPlan.objects.create(
        user=owner, local_date=date.today(), timezone_name=owner.timezone
    )
    for position in range(3):
        task = Task.objects.create(user=owner, title=f"Task {position}", area=area)
        add_plan_item(
            user=owner, plan=plan, task=task, kind="primary", position=position
        )
    fourth = Task.objects.create(user=owner, title="Fourth", area=area)
    with pytest.raises(ValidationError):
        add_plan_item(user=owner, plan=plan, task=fourth, kind="primary", position=3)
    source = plan.items.first()
    destination = carry_over(
        user=owner, item=source, destination_date=date.today() + timedelta(days=1)
    )
    assert source.refresh_from_db() is None
    assert source.state == DailyPlanItem.State.CARRIED_FORWARD
    assert destination.task_id == source.task_id
    assert (
        carry_over(
            user=owner, item=source, destination_date=date.today() + timedelta(days=1)
        ).pk
        == destination.pk
    )


def test_focus_state_machine_and_timestamp_duration(owner, area):
    session = start_session(
        user=owner, session_id=uuid.uuid4(), area=area, title="Build", is_deep_work=True
    )
    session.started_at = timezone.now() - timedelta(minutes=10)
    session.save(update_fields=("started_at",))
    pause_session(
        user=owner, session_id=session.id, pause_id=uuid.uuid4(), expected_version=1
    )
    pause = session.pauses.get()
    pause.started_at = timezone.now() - timedelta(minutes=2)
    pause.save(update_fields=("started_at",))
    resumed = resume_session(user=owner, session_id=session.id, expected_version=2)
    finished = end_session(
        user=owner,
        session_id=session.id,
        target="completed",
        expected_version=resumed.version,
    )
    assert finished.status == "completed"
    assert 470 <= finished.duration_seconds <= 490
    with pytest.raises(ValidationError):
        pause_session(user=owner, session_id=session.id, pause_id=uuid.uuid4())


def test_database_allows_only_one_open_session(owner, area):
    start_session(
        user=owner, session_id=uuid.uuid4(), area=area, title="One", is_deep_work=False
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        FocusSession.objects.create(
            user=owner,
            area=area,
            title="Two",
            is_deep_work=False,
            started_at=timezone.now(),
            timezone_snapshot="UTC",
            area_label_snapshot=area.name,
        )


def test_session_ownership(owner, area):
    other = get_user_model().objects.create_user("other2@example.com", "password")
    session = start_session(
        user=owner,
        session_id=uuid.uuid4(),
        area=area,
        title="Private",
        is_deep_work=False,
    )
    with pytest.raises(FocusSession.DoesNotExist):
        pause_session(user=other, session_id=session.id, pause_id=uuid.uuid4())
