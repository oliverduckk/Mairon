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
# Set work location
# --------------------------------------------------

def set_work_location(
    date,
    location
):
    """
    Set office vs work-from-home for one specific workday.

    This is a temporary daily override only.

    It does NOT modify Oliver's normal weekly routine.
    """

    return set_work_location_for_date(
        date_string=date,
        location=location
    )


# --------------------------------------------------
# Standalone test
# --------------------------------------------------

if __name__ == "__main__":

    # Thursday 3 September 2026 is a normal workday.
    #
    # We use it only as disposable test data, then delete
    # the override before exiting.

    test_date = "2026-09-03"

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

    print(
        "--- Set WFH ---"
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
        "--- After ---"
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

    print(
        "--- Cleanup ---"
    )

    print(
        json.dumps(
            clear_daily_context(
                date_string=test_date,
                key="work_location"
            ),
            indent=2
        )
    )

    print()

    print(
        "--- After cleanup ---"
    )

    print(
        json.dumps(
            get_routine_context(
                test_date
            ),
            indent=2
        )
    )