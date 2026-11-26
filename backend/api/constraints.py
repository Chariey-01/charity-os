"""User-facing errors for database constraints (Phase 0B, B3).

Serializers validate every model constraint before saving (see
OwnedModelSerializer), and the exception handler maps any IntegrityError that
still slips through (a race between two requests) with the same table. The API
therefore answers a field error or a 409, never a 500, and its rules are
exactly the database's.
"""

NON_FIELD = "non_field_errors"

# constraint name -> (field, message)
MESSAGES = {
    "challenges_challenge_active_name_ci_unique": (
        "name",
        "You already have an active challenge with this name.",
    ),
    "challenges_challenge_one_primary_per_user": (
        "is_primary",
        "Another challenge is already your primary one. Use set-primary to switch.",
    ),
    "challenges_challenge_dates_valid": (
        "end_date",
        "The end date cannot be before the start date.",
    ),
    "challenges_challenge_status_valid": ("status", "Choose a valid status."),
    "challenges_challenge_archived_not_primary": (
        "is_primary",
        "An archived challenge cannot be primary.",
    ),
    "planning_area_health_kind_valid": (
        "health_kind",
        "Choose exercise, sleep or none.",
    ),
    "planning_area_active_name_ci_unique": (
        "name",
        "You already have an active category with this name.",
    ),
    "planning_area_user_slug_unique": (
        "slug",
        "You already have a category with this slug.",
    ),
    "planning_area_color_valid": ("color", "Use a hex colour such as #64748B."),
    "planning_area_sort_order_nonnegative": (
        "sort_order",
        "Sort order cannot be negative.",
    ),
    "planning_capacity_user_date_unique": (
        "local_date",
        "You already set your capacity for this day.",
    ),
    "planning_capacity_available_valid": (
        "available_minutes",
        "Minutes must be between 0 and 1440.",
    ),
    "planning_capacity_deep_work_valid": (
        "deep_work_minutes",
        "Minutes must be between 0 and 1440.",
    ),
    "planning_capacity_deep_lte_available": (
        "deep_work_minutes",
        "Deep-work minutes cannot exceed available minutes.",
    ),
    "planning_task_status_valid": ("status", "Unknown task status."),
    "planning_task_terminal_fields_valid": (
        "status",
        "This status does not match the task's completion dates.",
    ),
    "planning_plan_user_date_unique": (
        "local_date",
        "You already have a plan for this day.",
    ),
    "planning_item_one_current_per_task": (
        "task",
        "This task is already on a plan. Carry it over instead.",
    ),
    "planning_item_current_position_unique": (
        "position",
        "Another item already holds this position.",
    ),
    "roadmaps_node_not_self_parent": ("parent", "A node cannot be its own parent."),
    "roadmaps_prerequisite_unique": (
        "prerequisite",
        "This prerequisite is already linked.",
    ),
    "roadmaps_prerequisite_not_self": (
        "prerequisite",
        "A node cannot be its own prerequisite.",
    ),
    "roadmaps_resource_position_unique": (
        "position",
        "Another resource already holds this position.",
    ),
    "records_evidence_exactly_one_parent": (
        NON_FIELD,
        "Attach evidence to exactly one task, session, roadmap item or accomplishment.",
    ),
    "health_sleep_order_valid": ("woke_at", "Waking must come after falling asleep."),
    "health_sleep_no_overlap": (
        "started_at",
        "This overlaps a sleep you already logged.",
    ),
    "health_exercise_order_valid": ("ended_at", "The end must come after the start."),
    "health_exercise_no_overlap": (
        "started_at",
        "This overlaps exercise you already logged.",
    ),
    "health_water_user_date_unique": (
        "local_date",
        "You already logged water for this day.",
    ),
    "health_nutrition_user_date_unique": (
        "local_date",
        "You already rated nutrition for this day.",
    ),
    "health_nutrition_rating_valid": ("rating", "Choose a rating from 1 to 5."),
    "reflections_daily_user_date_unique": (
        "local_date",
        "You already wrote a reflection for this day.",
    ),
    "reflections_weekly_user_start_unique": (
        "week_start_date",
        "You already reviewed this week.",
    ),
    "execution_one_open_session_per_user": (
        NON_FIELD,
        "Finish or pause your current focus session first.",
    ),
    "execution_one_open_pause_per_session": (
        NON_FIELD,
        "This session is already paused.",
    ),
    "execution_session_terminal_valid": (
        "status",
        "This status does not match the session's end.",
    ),
}
DEFAULT = (NON_FIELD, "This conflicts with one of your existing records.")


def describe(constraint_name):
    """(field, message) for a constraint, or a generic conflict message."""
    return MESSAGES.get(constraint_name, DEFAULT)
