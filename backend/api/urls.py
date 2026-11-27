from django.urls import path
from rest_framework.routers import DefaultRouter

from . import growth_views, notification_views, schedule_views, views

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
    ("schedule-entries", schedule_views.ScheduleEntryViewSet),
    *growth_views.GROWTH_ROUTES,
    ("reminders", notification_views.ReminderViewSet),
):
    router.register(prefix, view, basename=prefix)
router.register("activity", growth_views.ActivityViewSet, basename="activity")
urlpatterns = [
    path("auth/csrf", views.csrf),
    path("auth/login", views.login_view),
    path("auth/logout", views.logout_view),
    path("me", views.me),
    path("analytics/metrics", views.metrics),
    path("schedule/day", schedule_views.schedule_day),
    path("insights", schedule_views.insights),
    path("preferences", schedule_views.preferences),
    path("areas/ensure-defaults", schedule_views.ensure_categories),
    path("areas/ensure-workstreams", schedule_views.ensure_workstreams_view),
    path("progress", views.progress_view),
    path("journey", growth_views.journey_view),
    path("journey/year-end", growth_views.year_end_view),
    path("roadmap-templates", growth_views.roadmap_templates),
    path("roadmaps/from-template", growth_views.roadmap_from_template),
    path("push/config", notification_views.push_config),
    path("push/subscriptions", notification_views.push_subscriptions),
    path("push/unsubscribe", notification_views.push_unsubscribe),
    path("push/test", notification_views.push_test),
    path("push/snooze", notification_views.push_snooze),
    path("internal/reminders/dispatch", notification_views.dispatch_view),
    path("calendar/feed", notification_views.calendar_feed),
    path("calendar/<str:token>.ics", notification_views.calendar_ics),
] + router.urls
