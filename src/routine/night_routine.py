import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


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
    record_recent_context,
)

from tools.routine_tools import (
    sync_routine_wake_alarm,
)


# --------------------------------------------------
# Timezone
# --------------------------------------------------

TIMEZONE_NAME = os.getenv(
    "MAIRON_TIMEZONE",
    "Australia/Sydney"
)

LOCAL_TIMEZONE = ZoneInfo(
    TIMEZONE_NAME
)


# --------------------------------------------------
# Date helpers
# --------------------------------------------------

def get_tomorrow_date():
    """
    Return tomorrow's date using Mairon's configured
    local timezone.
    """

    today = datetime.now(
        LOCAL_TIMEZONE
    ).date()

    tomorrow = (
        today
        + timedelta(days=1)
    )

    return tomorrow.isoformat()


# --------------------------------------------------
# Alarm helpers
# --------------------------------------------------

def describe_alarm_state(
    alarm_result
):
    """
    Convert the stored alarm result into a small,
    predictable description for higher-level workflows.
    """

    if not alarm_result.get(
        "success"
    ):
        return {
            "exists": False,
            "enabled": False,
            "time": None,
            "source": None,
            "label": None,
            "error": alarm_result.get(
                "message"
            )
        }

    if not alarm_result.get(
        "found"
    ):
        return {
            "exists": False,
            "enabled": False,
            "time": None,
            "source": None,
            "label": None
        }

    alarm = (
        alarm_result.get("alarm")
        or {}
    )

    return {
        "exists": True,
        "enabled": bool(
            alarm.get("enabled")
        ),
        "time": alarm.get(
            "alarm_time"
        ),
        "source": alarm.get(
            "source"
        ),
        "label": alarm.get(
            "label"
        )
    }


# --------------------------------------------------
# Night routine preparation
# --------------------------------------------------

def prepare_night_routine(
    date=None,
    record_bedtime=True
):
    """
    Resolve everything Mairon needs to know before Oliver
    goes to bed.

    This does NOT control lights, the PC, PS5, or speakers
    yet.

    It currently handles:

        tomorrow's routine
        work-location requirement
        routine wake recommendation
        actual stored alarm
        manual-alarm priority
        disabled-alarm priority
        optional bedtime recent-context recording

    If a workday requires Oliver's location, the workflow
    returns needs_input rather than guessing.
    """

    target_date = (
        date
        or get_tomorrow_date()
    )

    routine_context = (
        resolve_day_context(
            target_date
        )
    )

    if not routine_context.get(
        "success"
    ):
        return {
            "success": False,
            "status": "error",
            "date": target_date,
            "message": routine_context.get(
                "message",
                "Could not resolve tomorrow's routine."
            )
        }

    # --------------------------------------------------
    # Missing work location
    # --------------------------------------------------

    if (
        routine_context.get(
            "day_type"
        ) == "work"
        and not routine_context.get(
            "work_location"
        )
    ):
        return {
            "success": True,
            "status": "needs_input",
            "date": target_date,
            "weekday": routine_context.get(
                "weekday"
            ),
            "day_type": "work",
            "missing_context": [
                "work_location"
            ],
            "question": (
                "Are you working from home or "
                "going into the office tomorrow?"
            ),
            "routine_context": routine_context,
            "alarm": None
        }

    # --------------------------------------------------
    # Synchronise routine-derived alarm
    # --------------------------------------------------

    alarm_sync = None

    recommended_wake_time = (
        routine_context.get(
            "recommended_wake_time"
        )
    )

    if recommended_wake_time:

        alarm_sync = (
            sync_routine_wake_alarm(
                date=target_date,
                resolved_context=(
                    routine_context
                )
            )
        )

    # --------------------------------------------------
    # Read authoritative alarm state
    # --------------------------------------------------

    alarm_result = (
        get_wake_alarm(
            target_date
        )
    )

    alarm_state = (
        describe_alarm_state(
            alarm_result
        )
    )

    # --------------------------------------------------
    # Record bedtime context
    # --------------------------------------------------

    bedtime_context = None

    if record_bedtime:

        bedtime_context = (
            record_recent_context(
                event_type="bedtime",
                details={
                    "next_date": (
                        target_date
                    ),
                    "next_day_type": (
                        routine_context.get(
                            "day_type"
                        )
                    ),
                    "work_location": (
                        routine_context.get(
                            "work_location"
                        )
                    ),
                    "recommended_wake_time": (
                        recommended_wake_time
                    ),
                    "alarm_time": (
                        alarm_state.get(
                            "time"
                        )
                    ),
                    "alarm_enabled": (
                        alarm_state.get(
                            "enabled"
                        )
                    ),
                    "alarm_source": (
                        alarm_state.get(
                            "source"
                        )
                    )
                },
                retention_hours=36
            )
        )

    return {
        "success": True,
        "status": "ready",
        "date": target_date,
        "weekday": routine_context.get(
            "weekday"
        ),
        "day_type": routine_context.get(
            "day_type"
        ),
        "work_location": (
            routine_context.get(
                "work_location"
            )
        ),
        "recommended_wake_time": (
            recommended_wake_time
        ),
        "alarm": alarm_state,
        "alarm_sync": alarm_sync,
        "routine_context": (
            routine_context
        ),
        "bedtime_context": (
            bedtime_context
        )
    }


# --------------------------------------------------
# Complete missing work-location context
# --------------------------------------------------

def complete_night_routine_work_location(
    date,
    location,
    record_bedtime=True
):
    """
    Complete a night routine that was blocked because
    tomorrow's work location was unknown.

    Example:

        Mairon:
            Office or home tomorrow?

        Oliver:
            Office.

    The location is stored only for the specified date.
    Then the normal night-routine preparation continues.
    """

    location_result = (
        set_work_location_for_date(
            date_string=date,
            location=location
        )
    )

    if not location_result.get(
        "success"
    ):
        return {
            "success": False,
            "status": "error",
            "date": date,
            "message": location_result.get(
                "message",
                "Could not set work location."
            )
        }

    return prepare_night_routine(
        date=date,
        record_bedtime=record_bedtime
    )


# --------------------------------------------------
# Standalone test
# --------------------------------------------------

if __name__ == "__main__":

    # Friday = normal workday.
    #
    # We deliberately use a disposable date rather than
    # tomorrow so this test cannot interfere with Oliver's
    # actual next-day context.
    #
    # record_bedtime=False prevents the test from polluting
    # Mairon's recent-context history.

    test_date = "2026-09-04"

    # --------------------------------------------------
    # Clean starting point
    # --------------------------------------------------

    clear_daily_context(
        date_string=test_date,
        key="work_location"
    )

    delete_wake_alarm(
        test_date
    )

    print(
        "--- Unknown work location ---"
    )

    print(
        json.dumps(
            prepare_night_routine(
                date=test_date,
                record_bedtime=False
            ),
            indent=2
        )
    )

    print()

    # --------------------------------------------------
    # Answer "office"
    # --------------------------------------------------

    print(
        "--- Complete with office ---"
    )

    print(
        json.dumps(
            complete_night_routine_work_location(
                date=test_date,
                location="office",
                record_bedtime=False
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
    # Manual override must survive bedtime workflow
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
                        "Night routine standalone test."
                    )
                }
            ),
            indent=2
        )
    )

    print()

    print(
        "--- Night routine with manual override ---"
    )

    print(
        json.dumps(
            prepare_night_routine(
                date=test_date,
                record_bedtime=False
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
    # Disabled alarm must survive bedtime workflow
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
        "--- Night routine with disabled alarm ---"
    )

    print(
        json.dumps(
            prepare_night_routine(
                date=test_date,
                record_bedtime=False
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

    context_cleanup = (
        clear_daily_context(
            date_string=test_date,
            key="work_location"
        )
    )

    alarm_cleanup = (
        delete_wake_alarm(
            test_date
        )
    )

    print(
        json.dumps(
            {
                "daily_context": (
                    context_cleanup
                ),
                "alarm": (
                    alarm_cleanup
                )
            },
            indent=2
        )
    )