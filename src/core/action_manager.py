import os
from datetime import datetime
from zoneinfo import ZoneInfo

from tools.calendar_tools import create_calendar_event, calendar_creation_unknown
from core.action_approval import authorised_calendar_effect


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


def execute_approved_action(action, *, approval_ticket=None):
    """
    Execute an action only after the user has approved it.

    The AI model never calls this function directly.
    """

    if not isinstance(action, dict) or not action:
        return {
            "success": False,
            "status": "not_attempted",
            "dispatch_attempted": False,
            "message": "No pending action exists."
        }

    action_type = action.get(
        "type"
    )

    if action_type == "create_calendar_event":
        with authorised_calendar_effect(approval_ticket, action) as permitted:
            if not permitted:
                return {
                    "success": False,
                    "status": "not_attempted",
                    "dispatch_attempted": False,
                    "approval_rejected": True,
                    "retryable": False,
                    "message": "Calendar action approval is missing, changed, expired or already used.",
                }
            try:
                return create_calendar_event(
                    summary=action.get("summary"),
                    start_time=action.get("start_time"),
                    end_time=action.get("end_time"),
                    location=action.get("location"),
                    description=action.get("description"),
                )
            except Exception:
                # A replacement adapter escaping its own guard cannot prove
                # non-execution. Keep the approval spent and suppress details.
                return calendar_creation_unknown()

    return {
        "success": False,
        "status": "not_attempted",
        "dispatch_attempted": False,
        "message": (
            f"Action type '{action_type}' "
            "is not approved by Mairon Core."
        )
    }


def calendar_action_outcome(result):
    """One conservative interpretation for visible text and application state."""
    if isinstance(result, dict):
        if (result.get("status") == "confirmed_created" and result.get("success") is True
                and result.get("dispatch_attempted") is True):
            return "confirmed_created"
        if (result.get("status") == "not_attempted" and result.get("success") is False
                and result.get("dispatch_attempted") is False):
            return "not_attempted"
    return "outcome_unknown"


def format_action_result(
    action,
    result
):
    """
    Turn the result of an approved action into a
    concise response for Oliver.
    """

    if not isinstance(result, dict) or result.get("status") == "outcome_unknown":
        return calendar_creation_unknown()["message"]
    if isinstance(action, dict) and action.get("type") == "create_calendar_event":
        if calendar_action_outcome(result) == "outcome_unknown":
            return calendar_creation_unknown()["message"]
    if not result.get("success") and result.get("status") != "not_attempted":
        # Unclassified old/custom adapter failures are not proof of no effect.
        return calendar_creation_unknown()["message"]
    if result.get("approval_rejected"):
        # A spent approval may already have created an event. Do not negate
        # that earlier outcome when refusing a replay.
        return "No additional calendar insertion was attempted. " + result["message"]

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

        answer = (
            f"Added {summary} to your calendar "
            f"for {start_time}."
        )
        if result.get("details_unavailable"):
            answer += " Additional event details are unavailable."
        return answer

    return result.get(
        "message",
        "Action completed."
    )
