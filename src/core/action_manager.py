import os
from datetime import datetime
from zoneinfo import ZoneInfo

from tools.calendar_tools import create_calendar_event


MAIRON_TIMEZONE = os.getenv(
    "MAIRON_TIMEZONE",
    "Australia/Sydney"
)

LOCAL_TIMEZONE = ZoneInfo(
    MAIRON_TIMEZONE
)


def parse_action_datetime(value):
    """
    Parse an ISO datetime supplied by the AI.

    If no timezone was supplied, interpret it using
    Mairon's configured local timezone.
    """

    dt = datetime.fromisoformat(value)

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=LOCAL_TIMEZONE
        )

    return dt.astimezone(
        LOCAL_TIMEZONE
    )


def format_datetime(value):
    """
    Produce a human-readable local datetime for
    permission prompts and confirmations.
    """

    try:
        dt = parse_action_datetime(
            value
        )

        return dt.strftime(
            "%A %d %B %Y at %I:%M %p"
        ).replace(
            " 0",
            " "
        )

    except Exception:
        return value


def describe_action(action):
    """
    Return a human-readable preview of a pending action.
    """

    if not action:
        return "Unknown action."

    action_type = action.get(
        "type"
    )

    if action_type == "create_calendar_event":
        summary = action.get(
            "summary",
            "(No title)"
        )

        start_time = format_datetime(
            action.get(
                "start_time",
                ""
            )
        )

        end_time = format_datetime(
            action.get(
                "end_time",
                ""
            )
        )

        lines = [
            f"Event: {summary}",
            f"Starts: {start_time}",
            f"Ends:   {end_time}",
        ]

        location = action.get(
            "location"
        )

        if location:
            lines.append(
                f"Location: {location}"
            )

        description = action.get(
            "description"
        )

        if description:
            lines.append(
                f"Description: {description}"
            )

        return "\n".join(
            lines
        )

    return (
        f"Unknown action type: {action_type}"
    )


def execute_approved_action(action):
    """
    Execute an action only after the user has approved it.

    The AI model never calls this function directly.
    """

    if not action:
        return {
            "success": False,
            "message": "No pending action exists."
        }

    action_type = action.get(
        "type"
    )

    if action_type == "create_calendar_event":
        return create_calendar_event(
            summary=action.get(
                "summary"
            ),
            start_time=action.get(
                "start_time"
            ),
            end_time=action.get(
                "end_time"
            ),
            location=action.get(
                "location"
            ),
            description=action.get(
                "description"
            ),
        )

    return {
        "success": False,
        "message": (
            f"Action type '{action_type}' "
            "is not approved by Mairon Core."
        )
    }


def format_action_result(
    action,
    result
):
    """
    Turn the result of an approved action into a
    concise response for Oliver.
    """

    if not result.get(
        "success"
    ):
        return (
            "The calendar event wasn't created. "
            f"{result.get('message', 'Unknown error.')}"
        )

    if action.get(
        "type"
    ) == "create_calendar_event":
        summary = action.get(
            "summary",
            "the event"
        )

        start_time = format_datetime(
            action.get(
                "start_time",
                ""
            )
        )

        return (
            f"Added {summary} to your calendar "
            f"for {start_time}."
        )

    return result.get(
        "message",
        "Action completed."
    )