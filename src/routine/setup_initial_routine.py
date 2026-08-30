import json

from routine_store import (
    initialise_routine_store,
    set_routine_rule,
    set_routine_preference,
    get_day_context,
    list_routine_rules,
    list_routine_preferences,
)


def print_result(title, result):
    print()
    print(f"--- {title} ---")
    print(
        json.dumps(
            result,
            indent=2
        )
    )


# --------------------------------------------------
# Initialise database tables
# --------------------------------------------------

initialise_routine_store()


# --------------------------------------------------
# Normal weekly routine
# --------------------------------------------------

# Monday, Tuesday, Thursday, Friday
#
# Work location is deliberately NOT stored here because
# office vs work-from-home varies by day.
work_result = set_routine_rule(
    name="Work",
    category="work",
    days_of_week=[
        0,  # Monday
        1,  # Tuesday
        3,  # Thursday
        4,  # Friday
    ],
    start_time="08:00",
    end_time="17:00",
    details={
        "location_varies": True,
        "work_location_options": [
            "home",
            "office"
        ]
    }
)


# Wednesday
#
# Exact university events/classes can later come from
# Calendar. This rule simply tells Mairon that Wednesday
# is normally a university day.
uni_result = set_routine_rule(
    name="University",
    category="university",
    days_of_week=[
        2  # Wednesday
    ],
    start_time=None,
    end_time=None,
    details={
        "location": "Macquarie University",
        "calendar_should_supply_specific_events": True
    }
)


# --------------------------------------------------
# Wake preferences
# --------------------------------------------------

office_wake_result = set_routine_preference(
    key="office_wake_time",
    value="06:30"
)

wfh_wake_result = set_routine_preference(
    key="wfh_wake_time",
    value="08:00"
)


# --------------------------------------------------
# Results
# --------------------------------------------------

print_result(
    "Work routine",
    work_result
)

print_result(
    "University routine",
    uni_result
)

print_result(
    "Office wake preference",
    office_wake_result
)

print_result(
    "WFH wake preference",
    wfh_wake_result
)

print_result(
    "All routine rules",
    list_routine_rules()
)

print_result(
    "All routine preferences",
    list_routine_preferences()
)


# --------------------------------------------------
# Example day checks
# --------------------------------------------------

# Monday, 31 August 2026
print_result(
    "Monday example",
    get_day_context(
        "2026-08-31"
    )
)

# Wednesday, 2 September 2026
print_result(
    "Wednesday example",
    get_day_context(
        "2026-09-02"
    )
)