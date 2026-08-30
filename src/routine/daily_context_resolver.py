from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

try:
    from routine.routine_store import (
        get_day_context,
        list_routine_preferences,
        set_daily_context,
    )
except ModuleNotFoundError:
    from routine_store import (
        get_day_context,
        list_routine_preferences,
        set_daily_context,
    )


TIMEZONE_NAME = "Australia/Sydney"

LOCAL_TIMEZONE = ZoneInfo(
    TIMEZONE_NAME
)


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def get_categories(
    routine_rules
):
    """
    Return unique active routine categories for a day.
    """

    categories = []

    for rule in routine_rules:
        category = rule.get(
            "category"
        )

        if (
            category
            and category not in categories
        ):
            categories.append(
                category
            )

    return categories


def get_preference_value(
    preferences,
    key,
    default=None
):
    """
    Safely read one routine preference.
    """

    return preferences.get(
        key,
        default
    )


# --------------------------------------------------
# Main resolver
# --------------------------------------------------

def resolve_day_context(
    date_string
):
    """
    Resolve Mairon's current understanding of a date.

    Combines:

        repeating routine
        +
        one-day context
        +
        persistent routine preferences

    This function does not modify anything.
    """

    day_result = get_day_context(
        date_string
    )

    if not day_result.get(
        "success"
    ):
        return day_result

    preference_result = (
        list_routine_preferences()
    )

    if not preference_result.get(
        "success"
    ):
        return preference_result

    routine_rules = day_result.get(
        "routine",
        []
    )

    daily_context = day_result.get(
        "daily_context",
        {}
    )

    preferences = preference_result.get(
        "preferences",
        {}
    )

    categories = get_categories(
        routine_rules
    )

    # --------------------------------------------------
    # Work day
    # --------------------------------------------------

    if "work" in categories:

        work_location = daily_context.get(
            "work_location"
        )

        result = {
            "success": True,
            "date": date_string,
            "weekday": day_result["weekday"],
            "day_type": "work",
            "routine": routine_rules,
            "daily_context": daily_context,
            "work_location": work_location,
            "recommended_wake_time": None,
            "wake_reason": None,
            "needs_input": False,
            "missing_context": [],
            "question": None,
        }

        if work_location == "office":

            wake_time = get_preference_value(
                preferences,
                "office_wake_time"
            )

            result[
                "recommended_wake_time"
            ] = wake_time

            result[
                "wake_reason"
            ] = (
                "Normal office workday wake preference."
            )

            return result

        if work_location == "home":

            wake_time = get_preference_value(
                preferences,
                "wfh_wake_time"
            )

            result[
                "recommended_wake_time"
            ] = wake_time

            result[
                "wake_reason"
            ] = (
                "Normal work-from-home wake preference."
            )

            return result

        # Workday exists, but location is not yet known.
        result[
            "needs_input"
        ] = True

        result[
            "missing_context"
        ] = [
            "work_location"
        ]

        result[
            "question"
        ] = (
            "Are you working from home or going "
            "into the office?"
        )

        return result

    # --------------------------------------------------
    # University day
    # --------------------------------------------------

    if "university" in categories:

        return {
            "success": True,
            "date": date_string,
            "weekday": day_result["weekday"],
            "day_type": "university",
            "routine": routine_rules,
            "daily_context": daily_context,
            "work_location": None,
            "recommended_wake_time": None,
            "wake_reason": (
                "University wake time should eventually "
                "be resolved from the day's calendar."
            ),
            "needs_input": False,
            "missing_context": [],
            "question": None,
        }

    # --------------------------------------------------
    # No recurring work / university routine
    # --------------------------------------------------

    return {
        "success": True,
        "date": date_string,
        "weekday": day_result["weekday"],
        "day_type": "free",
        "routine": routine_rules,
        "daily_context": daily_context,
        "work_location": None,
        "recommended_wake_time": None,
        "wake_reason": None,
        "needs_input": False,
        "missing_context": [],
        "question": None,
    }


# --------------------------------------------------
# Daily work-location update
# --------------------------------------------------

def set_work_location_for_date(
    date_string,
    location
):
    """
    Set whether a specific workday is office or WFH.

    This modifies only the specified date.
    It does not alter the repeating weekly routine.
    """

    location = (
        location
        or ""
    ).strip().lower()

    aliases = {
        "office": "office",
        "work": "office",
        "in office": "office",
        "the office": "office",

        "home": "home",
        "wfh": "home",
        "work from home": "home",
        "working from home": "home",
    }

    resolved_location = aliases.get(
        location
    )

    if not resolved_location:
        return {
            "success": False,
            "message": (
                "Work location must be either "
                "'office' or 'home'."
            )
        }

    current_day = resolve_day_context(
        date_string
    )

    if not current_day.get(
        "success"
    ):
        return current_day

    if current_day.get(
        "day_type"
    ) != "work":
        return {
            "success": False,
            "message": (
                f"{date_string} is not currently "
                "configured as a normal workday."
            )
        }

    save_result = set_daily_context(
        date_string=date_string,
        key="work_location",
        value=resolved_location
    )

    if not save_result.get(
        "success"
    ):
        return save_result

    return resolve_day_context(
        date_string
    )


# --------------------------------------------------
# Convenience helpers
# --------------------------------------------------

def resolve_today_context():
    """
    Resolve today's context.
    """

    today = datetime.now(
        LOCAL_TIMEZONE
    ).date()

    return resolve_day_context(
        today.isoformat()
    )


def resolve_tomorrow_context():
    """
    Resolve tomorrow's context.
    """

    tomorrow = (
        datetime.now(
            LOCAL_TIMEZONE
        ).date()
        + timedelta(
            days=1
        )
    )

    return resolve_day_context(
        tomorrow.isoformat()
    )


# --------------------------------------------------
# Standalone test
# --------------------------------------------------

if __name__ == "__main__":

    import json

    print(
        "--- Tomorrow ---"
    )

    print(
        json.dumps(
            resolve_tomorrow_context(),
            indent=2
        )
    )

    print()

    print(
        "--- Wednesday example ---"
    )

    print(
        json.dumps(
            resolve_day_context(
                "2026-09-02"
            ),
            indent=2
        )
    )