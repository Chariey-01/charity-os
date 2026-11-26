"""A delete blocked by history answers 409, never 500 (backstop for S4)."""

import pytest
from django.db.models import RestrictedError
from rest_framework.test import APIRequestFactory

from api.exceptions import exception_handler
from tests.history_graph import build_history

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("parent", ["area", "task", "session"])
def test_blocked_deletes_become_409_with_what_blocks_them(django_user_model, parent):
    user = django_user_model.objects.create_user("owner@example.com", "password")
    graph = build_history(user)
    with pytest.raises(RestrictedError) as caught:
        graph[parent].delete()
    request = APIRequestFactory().delete("/api/v1/anything")

    response = exception_handler(caught.value, {"request": request, "view": None})

    assert response.status_code == 409
    error = response.data["error"]
    assert error["code"] == "has_history"
    assert response.data["detail"] == error["message"]
    assert error["blocking"]
    assert all(
        set(row) == {"model", "count"} and row["count"] > 0 for row in error["blocking"]
    )


def test_blocking_list_names_kinds_not_records(django_user_model):
    user = django_user_model.objects.create_user("owner@example.com", "password")
    graph = build_history(user)
    with pytest.raises(RestrictedError) as caught:
        graph["plan"].delete()

    response = exception_handler(caught.value, {"request": None, "view": None})

    assert response.data["error"]["blocking"] == [
        {"model": "daily plan items", "count": 1}
    ]
