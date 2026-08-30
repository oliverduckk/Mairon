import json
import sys
from pathlib import Path


# --------------------------------------------------
# Import setup
# --------------------------------------------------

SRC_ROOT = Path(__file__).resolve().parents[1]

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(SRC_ROOT)
    )


from alarms.alarm_manager import (
    delete_wake_alarm,
    disable_wake_alarm,
    get_wake_alarm,
    set_wake_alarm,
)

from routine.daily_context_resolver import (
    resolve_day_context,
    set_work_location_for_date,
)

from routine.routine_store import (
    clear_daily_context,
)


# --------------------------------------------------
# Read day context
# --------------------------------------------------

def get_routine_context(
    date
):
    """
    Get Mairon's current understanding of a specific day.

    Includes:

        normal repeating routine
        one-day overrides
        resolved day type
        work location
        recommended wake time
        missing information

    date must use YYYY-MM-DD.
    """

    return resolve_day_context(
        date
    )


# --------------------------------------------------
# Routine alarm synchronisation
# --------------------------------------------------

def sync_routine_wake_alarm(
    date,
    resolved_context
):
    """
    Synchronise a workday's routine-derived wake alarm.

    Priority rules:

        manual alarm > routine recommendation

        explicitly disabled alarm > routine recommendation

        otherwise routine recommendation is scheduled

    This prevents later routine processing from destroying
    an explicit choice Oliver already made.
    """

    recommended_wake_time = (
        resolved_context.get(
            "recommended_wake_time"
        )
    )

    if not recommended_wake_time:
        return {
            "success": True,
            "action": "none",
            "reason": (
                "No routine wake time is currently "
                "recommended for this date."
            ),
            "alarm": None
        }

    existing_result = get_wake_alarm(
        date
    )

    if not existing_result.get(
        "success"
    ):
        return existing_result

    existing_alarm = (
        existing_result.get(
            "alarm"
        )
        if existing_result.get(
            "found"
        )
        else None
    )

    # --------------------------------------------------
    # Explicitly disabled alarm wins
    # --------------------------------------------------

    if (
        existing_alarm
        and not existing_alarm.get(
            "enabled",
            True
        )
    ):
        return {
            "success": True,
            "action": "preserved_disabled",
            "reason": (
                "A wake alarm for this date was explicitly "
                "disabled, so the routine did not re-enable it."
            ),
            "recommended_wake_time": (
                recommended_wake_time
            ),
            "alarm": existing_alarm
        }

    # --------------------------------------------------
    # Explicit manual alarm wins
    # --------------------------------------------------

    if (
        existing_alarm
        and existing_alarm.get(
            "source"
        ) == "manual"
    ):
        return {
            "success": True,
            "action": "preserved_manual",
            "reason": (
                "An explicit manual wake alarm already exists, "
                "so the routine recommendation did not overwrite it."
            ),
            "recommended_wake_time": (
                recommended_wake_time
            ),
            "alarm": existing_alarm
        }

    # --------------------------------------------------
    # Routine alarm
    # --------------------------------------------------

    work_location = resolved_context.get(
        "work_location"
    )

    if work_location == "office":
        label = "Work - Office"

    elif work_location == "home":
        label = "Work - Home"

    else:
        label = "Wake up"

    alarm_result = set_wake_alarm(
        date=date,
        time=recommended_wake_time,
        label=label,
        source="routine",
        metadata={
            "work_location": work_location,
            "routine_day_type": (
                resolved_context.get(
                    "day_type"
                )
            )
        }
    )

    if not alarm_result.get(
        "success"
    ):
        return alarm_result

    return {
        "success": True,
        "action": (
            "routine_alarm_synchronised"
        ),
        "recommended_wake_time": (
            recommended_wake_time
        ),
        "alarm": alarm_result.get(
            "alarm"
        )
    }


# --------------------------------------------------
# Set work location
# --------------------------------------------------

def set_work_location(
    date,
    location
):
    """
    Set office vs work-from-home for one specific workday.

    This modifies only the specified date.

    Once the daily context has been updated, Mairon
    synchronises the corresponding routine wake alarm.

    Manual or explicitly disabled alarms are preserved.
    """

    context_result = (
        set_work_location_for_date(
            date_string=date,
            location=location
        )
    )

    if not context_result.get(
        "success"
    ):
        return context_result

    alarm_sync_result = (
        sync_routine_wake_alarm(
            date=date,
            resolved_context=context_result
        )
    )

    result = dict(
        context_result
    )

    result[
        "alarm_sync"
    ] = alarm_sync_result

    return result


# --------------------------------------------------
# Standalone test
# --------------------------------------------------

if __name__ == "__main__":

    # Friday 4 September 2026 is a normal workday.
    #
    # Everything created here is cleaned up at the end.

    test_date = "2026-09-04"

    # Start from a known clean state.
    clear_daily_context(
        date_string=test_date,
        key="work_location"
    )

    delete_wake_alarm(
        test_date
    )

    print(
        "--- Before ---"
    )

    print(
        json.dumps(
            get_routine_context(
                test_date
            ),
            indent=2
        )
    )

    print()

    # --------------------------------------------------
    # Office:
    # routine should create 06:30 alarm
    # --------------------------------------------------

    print(
        "--- Set office ---"
    )

    print(
        json.dumps(
            set_work_location(
                date=test_date,
                location="office"
            ),
            indent=2
        )
    )

    print()

    print(
        "--- Office alarm ---"
    )

    print(
        json.dumps(
            get_wake_alarm(
                test_date
            ),
            indent=2
        )
    )

    print()

    # --------------------------------------------------
    # WFH:
    # same routine alarm should update to 08:00
    # --------------------------------------------------

    print(
        "--- Change to WFH ---"
    )

    print(
        json.dumps(
            set_work_location(
                date=test_date,
                location="home"
            ),
            indent=2
        )
    )

    print()

    print(
        "--- WFH alarm ---"
    )

    print(
        json.dumps(
            get_wake_alarm(
                test_date
            ),
            indent=2
        )
    )

    print()

    # --------------------------------------------------
    # Manual override:
    # explicit 07:00 must survive routine changes
    # --------------------------------------------------

    print(
        "--- Manual override to 07:00 ---"
    )

    print(
        json.dumps(
            set_wake_alarm(
                date=test_date,
                time="07:00",
                label="Wake up",
                source="manual",
                metadata={
                    "reason": (
                        "Standalone routine/alarm "
                        "priority test."
                    )
                }
            ),
            indent=2
        )
    )

    print()

    print(
        "--- Change back to office ---"
    )

    print(
        json.dumps(
            set_work_location(
                date=test_date,
                location="office"
            ),
            indent=2
        )
    )

    print()

    print(
        "--- Manual alarm should still be 07:00 ---"
    )

    print(
        json.dumps(
            get_wake_alarm(
                test_date
            ),
            indent=2
        )
    )

    print()

    # --------------------------------------------------
    # Disabled alarm:
    # routine must not resurrect it
    # --------------------------------------------------

    print(
        "--- Disable alarm ---"
    )

    print(
        json.dumps(
            disable_wake_alarm(
                test_date
            ),
            indent=2
        )
    )

    print()

    print(
        "--- Change to WFH while disabled ---"
    )

    print(
        json.dumps(
            set_work_location(
                date=test_date,
                location="home"
            ),
            indent=2
        )
    )

    print()

    print(
        "--- Alarm should remain disabled ---"
    )

    print(
        json.dumps(
            get_wake_alarm(
                test_date
            ),
            indent=2
        )
    )

    print()

    # --------------------------------------------------
    # Cleanup
    # --------------------------------------------------

    print(
        "--- Cleanup ---"
    )

    clear_result = clear_daily_context(
        date_string=test_date,
        key="work_location"
    )

    alarm_delete_result = (
        delete_wake_alarm(
            test_date
        )
    )

    print(
        json.dumps(
            {
                "daily_context": (
                    clear_result
                ),
                "alarm": (
                    alarm_delete_result
                )
            },
            indent=2
        )
    )

    print()

    print(
        "--- After cleanup ---"
    )

    print(
        json.dumps(
            {
                "routine": (
                    get_routine_context(
                        test_date
                    )
                ),
                "alarm": (
                    get_wake_alarm(
                        test_date
                    )
                )
            },
            indent=2
        )
    )