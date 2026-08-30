import json
import sys
from pathlib import Path


# --------------------------------------------------
# Import setup
# --------------------------------------------------

# When this file is run directly:
#
#     python src/tools/alarm_tools.py
#
# Python normally sees src/tools as the import root,
# which means sibling packages such as src/alarms
# cannot be found.
#
# Add src/ explicitly so both standalone testing and
# normal Mairon imports behave consistently.

SRC_ROOT = Path(__file__).resolve().parents[1]

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(SRC_ROOT)
    )


from alarms.alarm_manager import (
    disable_wake_alarm,
    get_wake_alarm,
    list_upcoming_alarms,
    set_wake_alarm,
)


# --------------------------------------------------
# Read wake alarm
# --------------------------------------------------

def get_alarm_for_date(
    date
):
    """
    Get the wake alarm configured for one specific date.

    Returns both enabled and disabled alarms so Mairon
    can distinguish:

        no alarm exists

    from:

        an alarm exists but Oliver disabled it
    """

    return get_wake_alarm(
        date=date
    )


# --------------------------------------------------
# Set wake alarm
# --------------------------------------------------

def set_alarm_for_date(
    date,
    time,
    label="Wake up",
    source="manual"
):
    """
    Create or update one date's wake alarm.

    There can only be one wake alarm per date.

    If an alarm already exists, it is updated rather than
    duplicated.
    """

    return set_wake_alarm(
        date=date,
        time=time,
        label=label,
        source=source
    )


# --------------------------------------------------
# Disable wake alarm
# --------------------------------------------------

def disable_alarm_for_date(
    date
):
    """
    Disable one date's wake alarm.

    The alarm record remains stored so Mairon can remember
    that waking was deliberately disabled.
    """

    return disable_wake_alarm(
        date=date
    )


# --------------------------------------------------
# Upcoming alarms
# --------------------------------------------------

def get_upcoming_alarms(
    days=7
):
    """
    Return enabled alarms coming up during the requested
    number of days.
    """

    return list_upcoming_alarms(
        days=days,
        enabled_only=True
    )


# --------------------------------------------------
# Standalone test
# --------------------------------------------------

if __name__ == "__main__":

    test_date = "2026-09-03"

    print(
        "--- Set test alarm ---"
    )

    print(
        json.dumps(
            set_alarm_for_date(
                date=test_date,
                time="06:30",
                label="Work - Office",
                source="routine"
            ),
            indent=2
        )
    )

    print()

    print(
        "--- Read test alarm ---"
    )

    print(
        json.dumps(
            get_alarm_for_date(
                test_date
            ),
            indent=2
        )
    )

    print()

    print(
        "--- Upcoming alarms ---"
    )

    print(
        json.dumps(
            get_upcoming_alarms(
                days=7
            ),
            indent=2
        )
    )

    print()

    print(
        "--- Disable test alarm ---"
    )

    print(
        json.dumps(
            disable_alarm_for_date(
                test_date
            ),
            indent=2
        )
    )

    print()

    print(
        "--- Disabled state ---"
    )

    print(
        json.dumps(
            get_alarm_for_date(
                test_date
            ),
            indent=2
        )
    )