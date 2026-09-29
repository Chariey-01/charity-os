from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter(trailing_slash=False)
for prefix, view in (
    ("challenges", views.ChallengeViewSet),
    ("areas", views.AreaViewSet),
    ("capacities", views.CapacityViewSet),
    ("daily-plans", views.DailyPlanViewSet),
    ("daily-plan-items", views.PlanItemViewSet),
    ("tasks", views.TaskViewSet),
    ("roadmaps", views.RoadmapViewSet),
    ("roadmap-nodes", views.RoadmapNodeViewSet),
    ("roadmap-prerequisites", views.RoadmapPrerequisiteViewSet),
    ("roadmap-resources", views.RoadmapResourceViewSet),
    ("sessions", views.SessionViewSet),
    ("evidence", views.EvidenceViewSet),
    ("accomplishments", views.AccomplishmentViewSet),
    ("sleep-logs", views.SleepLogViewSet),
    ("exercise-logs", views.ExerciseLogViewSet),
    ("meal-logs", views.MealLogViewSet),
    ("water", views.WaterViewSet),
    ("nutrition", views.NutritionViewSet),
    ("daily-reflections", views.DailyReflectionViewSet),
    ("weekly-reviews", views.WeeklyReviewViewSet),
):
    router.register(prefix, view, basename=prefix)
urlpatterns = [
    path("auth/csrf", views.csrf),
    path("auth/login", views.login_view),
    path("auth/logout", views.logout_view),
    path("me", views.me),
    path("analytics/metrics", views.metrics),
] + router.urls
