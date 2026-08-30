import json
import os
import sys
from datetime import datetime
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
    get_wake_alarm,
)

from routine.daily_context_resolver import (
    resolve_day_context,
)

from routine.routine_store import (
    get_recent_context,
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

def get_today_date():
    """
    Return today's local date according to Mairon's
    configured timezone.
    """

    return datetime.now(
        LOCAL_TIMEZONE
    ).date().isoformat()


# --------------------------------------------------
# Alarm helpers
# --------------------------------------------------

def describe_alarm_state(
    alarm_result
):
    """
    Convert Alarm Manager output into a small predictable
    structure for the morning workflow.
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
# Bedtime helpers
# --------------------------------------------------

def get_latest_bedtime_for_date(
    date
):
    """
    Find the newest non-expired bedtime event whose
    next_date matches the requested morning.

    This prevents an unrelated bedtime record from another
    night being treated as today's bedtime context.
    """

    recent_result = (
        get_recent_context()
    )

    if not recent_result.get(
        "success"
    ):
        return {
            "success": False,
            "found": False,
            "event": None,
            "message": recent_result.get(
                "message",
                "Could not read recent context."
            )
        }

    events = recent_result.get(
        "events",
        []
    )

    matching_events = []

    for event in events:

        if event.get(
            "event_type"
        ) != "bedtime":
            continue

        details = (
            event.get("details")
            or {}
        )

        if details.get(
            "next_date"
        ) != date:
            continue

        matching_events.append(
            event
        )

    if not matching_events:
        return {
            "success": True,
            "found": False,
            "event": None
        }

    matching_events.sort(
        key=lambda event: event.get(
            "occurred_at",
            ""
        ),
        reverse=True
    )

    return {
        "success": True,
        "found": True,
        "event": matching_events[0]
    }


# --------------------------------------------------
# Sleep calculation
# --------------------------------------------------

def calculate_sleep_opportunity(
    target_date,
    bedtime_event,
    alarm_state
):
    """
    Calculate the maximum time between the recorded
    bedtime and the enabled wake alarm.

    IMPORTANT:

    This is sleep OPPORTUNITY, not measured sleep.

    Mairon knows when Oliver said he was going to bed and
    when the alarm was scheduled. It does not know exactly
    when Oliver actually fell asleep or woke up.

    Therefore Mairon must never describe this value as
    verified hours slept.
    """

    if not bedtime_event:
        return {
            "available": False,
            "minutes": None,
            "hours": None,
            "display": None,
            "reason": (
                "No matching bedtime event was recorded."
            )
        }

    if not alarm_state.get(
        "exists"
    ):
        return {
            "available": False,
            "minutes": None,
            "hours": None,
            "display": None,
            "reason": (
                "No wake alarm exists for this morning."
            )
        }

    if not alarm_state.get(
        "enabled"
    ):
        return {
            "available": False,
            "minutes": None,
            "hours": None,
            "display": None,
            "reason": (
                "The wake alarm for this morning is disabled."
            )
        }

    alarm_time = alarm_state.get(
        "time"
    )

    if not alarm_time:
        return {
            "available": False,
            "minutes": None,
            "hours": None,
            "display": None,
            "reason": (
                "The wake alarm does not contain a valid time."
            )
        }

    occurred_at = bedtime_event.get(
        "occurred_at"
    )

    if not occurred_at:
        return {
            "available": False,
            "minutes": None,
            "hours": None,
            "display": None,
            "reason": (
                "The bedtime event has no timestamp."
            )
        }

    try:

        bedtime = datetime.fromisoformat(
            occurred_at
        )

        if bedtime.tzinfo is None:
            bedtime = bedtime.replace(
                tzinfo=LOCAL_TIMEZONE
            )

        else:
            bedtime = bedtime.astimezone(
                LOCAL_TIMEZONE
            )

        alarm_datetime = datetime.strptime(
            f"{target_date} {alarm_time}",
            "%Y-%m-%d %H:%M"
        ).replace(
            tzinfo=LOCAL_TIMEZONE
        )

    except ValueError:

        return {
            "available": False,
            "minutes": None,
            "hours": None,
            "display": None,
            "reason": (
                "Bedtime or alarm time could not be parsed."
            )
        }

    difference = (
        alarm_datetime
        - bedtime
    )

    total_minutes = int(
        difference.total_seconds()
        // 60
    )

    if total_minutes < 0:
        return {
            "available": False,
            "minutes": None,
            "hours": None,
            "display": None,
            "reason": (
                "The recorded bedtime occurs after the "
                "scheduled alarm."
            )
        }

    hours = (
        total_minutes
        // 60
    )

    minutes = (
        total_minutes
        % 60
    )

    if minutes == 0:
        display = (
            f"{hours}h"
        )

    else:
        display = (
            f"{hours}h {minutes}m"
        )

    return {
        "available": True,
        "minutes": total_minutes,
        "hours": round(
            total_minutes / 60,
            2
        ),
        "display": display,
        "bedtime": bedtime.isoformat(),
        "alarm_datetime": (
            alarm_datetime.isoformat()
        ),
        "reason": (
            "Calculated from recorded bedtime to the "
            "enabled wake alarm."
        )
    }


# --------------------------------------------------
# Morning routine
# --------------------------------------------------

def prepare_morning_routine(
    date=None
):
    """
    Build Mairon's authoritative morning context.

    This function performs no writes.

    It combines:

        today's repeating routine
        today's one-day context
        today's actual wake alarm
        last night's matching bedtime context
        calculated sleep opportunity

    Calendar, weather, inbox, and commute are deliberately
    left to the higher-level morning briefing workflow.
    """

    target_date = (
        date
        or get_today_date()
    )

    # --------------------------------------------------
    # Routine
    # --------------------------------------------------

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
                "Could not resolve morning routine."
            )
        }

    # --------------------------------------------------
    # Alarm
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
    # Last night's bedtime
    # --------------------------------------------------

    bedtime_result = (
        get_latest_bedtime_for_date(
            target_date
        )
    )

    bedtime_event = (
        bedtime_result.get(
            "event"
        )
        if bedtime_result.get(
            "found"
        )
        else None
    )

    # --------------------------------------------------
    # Sleep opportunity
    # --------------------------------------------------

    sleep_opportunity = (
        calculate_sleep_opportunity(
            target_date=target_date,
            bedtime_event=bedtime_event,
            alarm_state=alarm_state
        )
    )

    # --------------------------------------------------
    # Final morning state
    # --------------------------------------------------

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
        "work_location": routine_context.get(
            "work_location"
        ),
        "recommended_wake_time": (
            routine_context.get(
                "recommended_wake_time"
            )
        ),
        "alarm": alarm_state,
        "bedtime": (
            {
                "found": True,
                "occurred_at": (
                    bedtime_event.get(
                        "occurred_at"
                    )
                ),
                "details": (
                    bedtime_event.get(
                        "details",
                        {}
                    )
                )
            }
            if bedtime_event
            else {
                "found": False,
                "occurred_at": None,
                "details": {}
            }
        ),
        "sleep_opportunity": (
            sleep_opportunity
        ),
        "routine_context": (
            routine_context
        )
    }


# --------------------------------------------------
# Standalone test
# --------------------------------------------------

if __name__ == "__main__":

    # We deliberately test the morning AFTER the bedtime
    # record created during the Night Routine test.
    #
    # This is read-only and does not alter any stored data.

    test_date = "2026-08-31"

    print(
        "--- Morning routine ---"
    )

    result = (
        prepare_morning_routine(
            date=test_date
        )
    )

    print(
        json.dumps(
            result,
            indent=2
        )
    )

    print()

    # --------------------------------------------------
    # Human-readable sanity checks
    # --------------------------------------------------

    print(
        "--- Sanity checks ---"
    )

    print(
        f"Date: {result.get('date')}"
    )

    print(
        f"Day type: {result.get('day_type')}"
    )

    print(
        "Work location: "
        f"{result.get('work_location')}"
    )

    alarm = (
        result.get("alarm")
        or {}
    )

    print(
        "Actual alarm: "
        f"{alarm.get('time')}"
    )

    print(
        "Alarm enabled: "
        f"{alarm.get('enabled')}"
    )

    bedtime = (
        result.get("bedtime")
        or {}
    )

    print(
        "Bedtime found: "
        f"{bedtime.get('found')}"
    )

    print(
        "Bedtime timestamp: "
        f"{bedtime.get('occurred_at')}"
    )

    sleep = (
        result.get(
            "sleep_opportunity"
        )
        or {}
    )

    print(
        "Sleep opportunity: "
        f"{sleep.get('display')}"
    )

    print(
        "Sleep opportunity minutes: "
        f"{sleep.get('minutes')}"
    )