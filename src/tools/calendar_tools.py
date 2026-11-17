import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from core.action_approval import consume_calendar_effect

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


PROJECT_ROOT = Path(__file__).resolve().parents[2]

GOOGLE_DATA_DIR = PROJECT_ROOT / "data" / "google"

CREDENTIALS_PATH = GOOGLE_DATA_DIR / "credentials.json"
TOKEN_PATH = GOOGLE_DATA_DIR / "token.json"


# Allows Mairon to read and manage events on calendars
# owned by Oliver, without broader Calendar administration.
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events.owned"
]


MAIRON_TIMEZONE = os.getenv(
    "MAIRON_TIMEZONE",
    "Australia/Sydney"
)

LOCAL_TIMEZONE = ZoneInfo(
    MAIRON_TIMEZONE
)


def get_credentials():
    """
    Load Mairon's Google OAuth credentials.

    If no valid token exists, Google will ask Oliver
    to authorize the configured Calendar scope.
    """

    credentials = None

    if TOKEN_PATH.exists():
        credentials = Credentials.from_authorized_user_file(
            str(TOKEN_PATH),
            SCOPES
        )

    if not credentials or not credentials.valid:

        if (
            credentials
            and credentials.expired
            and credentials.refresh_token
        ):
            credentials.refresh(
                Request()
            )

        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    "Google OAuth credentials were not found at "
                    f"{CREDENTIALS_PATH}"
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH),
                SCOPES
            )

            credentials = flow.run_local_server(
                port=0
            )

        GOOGLE_DATA_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        TOKEN_PATH.write_text(
            credentials.to_json(),
            encoding="utf-8"
        )

    return credentials


def create_calendar_service():
    """
    Create an authenticated Google Calendar API client.
    """

    credentials = get_credentials()

    return build(
        "calendar",
        "v3",
        credentials=credentials
    )


def normalise_event(event):
    """
    Strip Google's event object down to information
    Mairon actually needs.
    """

    start_data = event.get(
        "start",
        {}
    )

    end_data = event.get(
        "end",
        {}
    )

    all_day = "date" in start_data

    start = start_data.get(
        "dateTime",
        start_data.get("date")
    )

    end = end_data.get(
        "dateTime",
        end_data.get("date")
    )

    result = {
        "summary": event.get(
            "summary",
            "(No title)"
        ),
        "start": start,
        "end": end,
        "all_day": all_day,
    }

    location = event.get(
        "location"
    )

    if location:
        result["location"] = location

    description = event.get(
        "description"
    )

    if description:
        result["description"] = (
            description[:1000]
        )

    return result


def fetch_events_between(
    start_time,
    end_time,
    max_results=50
):
    """
    Fetch events between two timezone-aware datetimes.
    """

    service = create_calendar_service()

    response = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=start_time.isoformat(),
            timeMax=end_time.isoformat(),
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
            showDeleted=False,
        )
        .execute()
    )

    events = response.get(
        "items",
        []
    )

    return [
        normalise_event(event)
        for event in events
    ]


def get_calendar_events(
    period="today"
):
    """
    Get calendar events for a useful human time period.

    Supported periods:
        today
        tomorrow
        next_7_days
        next_30_days
    """

    period = period.lower().strip()

    valid_periods = {
        "today",
        "tomorrow",
        "next_7_days",
        "next_30_days",
    }

    if period not in valid_periods:
        return {
            "success": False,
            "message": (
                f"Unsupported calendar period '{period}'."
            )
        }

    try:
        now = datetime.now(
            LOCAL_TIMEZONE
        )

        today_start = now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

        if period == "today":
            start_time = today_start
            end_time = (
                today_start
                + timedelta(days=1)
            )

        elif period == "tomorrow":
            start_time = (
                today_start
                + timedelta(days=1)
            )

            end_time = (
                start_time
                + timedelta(days=1)
            )

        elif period == "next_7_days":
            start_time = now
            end_time = (
                now
                + timedelta(days=7)
            )

        else:
            start_time = now
            end_time = (
                now
                + timedelta(days=30)
            )

        events = fetch_events_between(
            start_time,
            end_time
        )

        return {
            "success": True,
            "period": period,
            "timezone": MAIRON_TIMEZONE,
            "range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
            "event_count": len(events),
            "events": events
        }

    except FileNotFoundError as error:
        return {
            "success": False,
            "message": str(error)
        }

    except HttpError as error:
        return {
            "success": False,
            "message": (
                f"Google Calendar API error: {error}"
            )
        }

    except Exception as error:
        return {
            "success": False,
            "message": (
                f"Calendar request failed: {error}"
            )
        }


def get_next_calendar_event():
    """
    Return Oliver's next upcoming calendar event.
    """

    try:
        now = datetime.now(
            LOCAL_TIMEZONE
        )

        service = create_calendar_service()

        response = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now.isoformat(),
                maxResults=1,
                singleEvents=True,
                orderBy="startTime",
                showDeleted=False,
            )
            .execute()
        )

        events = response.get(
            "items",
            []
        )

        if not events:
            return {
                "success": True,
                "event": None,
                "message": (
                    "No upcoming calendar events were found."
                )
            }

        return {
            "success": True,
            "timezone": MAIRON_TIMEZONE,
            "event": normalise_event(
                events[0]
            )
        }

    except FileNotFoundError as error:
        return {
            "success": False,
            "message": str(error)
        }

    except HttpError as error:
        return {
            "success": False,
            "message": (
                f"Google Calendar API error: {error}"
            )
        }

    except Exception as error:
        return {
            "success": False,
            "message": (
                f"Calendar request failed: {error}"
            )
        }


def calendar_creation_unknown():
    """A dispatched request may have committed; its consumed approval stays spent."""
    return {
        "success": False,
        "status": "outcome_unknown",
        "dispatch_attempted": True,
        "retryable": False,
        "message": (
            "Calendar creation could not be confirmed. Check your calendar before "
            "approving another attempt; this approval cannot be retried."
        ),
    }


def _calendar_not_attempted(message, *, approval_rejected=False):
    return {
        "success": False,
        "status": "not_attempted",
        "dispatch_attempted": False,
        "retryable": False,
        "approval_rejected": approval_rejected,
        "message": message,
    }


def _confirmed_insert_response(response, approved_body):
    """Require an event acknowledgement, not an empty/error/malformed response."""
    if (not isinstance(response, dict) or "error" in response
            or response.get("status") not in (None, "confirmed", "tentative")):
        return False
    event_id = response.get("id")
    if isinstance(event_id, str) and event_id.strip():
        return True
    # A response omitting its ID must at least acknowledge all approved identity
    # fields. Never invent an ID/link from approved details alone.
    return (response.get("summary") == approved_body["summary"]
            and isinstance(response.get("start"), dict)
            and isinstance(response.get("end"), dict)
            and response["start"].get("dateTime") == approved_body["start"]["dateTime"]
            and response["end"].get("dateTime") == approved_body["end"]["dateTime"])


def create_calendar_event(
    summary,
    start_time,
    end_time,
    location=None,
    description=None
):
    """
    Create an event on Oliver's primary Google Calendar.

    SECURITY NOTE:
    This function performs the actual write.

    It must NOT be exposed directly to the AI model.
    Mairon Core must obtain explicit user approval before
    this function is ever called.
    """

    if not consume_calendar_effect(summary, start_time, end_time, location, description):
        return _calendar_not_attempted(
            "Calendar event execution requires current, single-use approval.",
            approval_rejected=True,
        )

    if not summary:
        return _calendar_not_attempted("Event summary is required.")

    if not start_time or not end_time:
        return _calendar_not_attempted("Event start and end times are required.")

    try:
        start_datetime = datetime.fromisoformat(
            start_time
        )

        end_datetime = datetime.fromisoformat(
            end_time
        )

        if start_datetime.tzinfo is None:
            start_datetime = start_datetime.replace(
                tzinfo=LOCAL_TIMEZONE
            )

        if end_datetime.tzinfo is None:
            end_datetime = end_datetime.replace(
                tzinfo=LOCAL_TIMEZONE
            )

        if end_datetime <= start_datetime:
            return _calendar_not_attempted("Event end time must be after its start time.")

        event_body = {
            "summary": summary,
            "start": {
                "dateTime": start_datetime.isoformat(),
                "timeZone": MAIRON_TIMEZONE,
            },
            "end": {
                "dateTime": end_datetime.isoformat(),
                "timeZone": MAIRON_TIMEZONE,
            },
        }

        if location:
            event_body["location"] = location

        if description:
            event_body["description"] = description

    except (ValueError, TypeError):
        return _calendar_not_attempted("Invalid event date/time format.")

    # Google discovery resource construction creates an HttpRequest; only
    # execute() dispatches the insertion. Credential/client/build failures here
    # are confirmed non-insertion, irrespective of account setup activity.
    try:
        service = create_calendar_service()
        request = service.events().insert(calendarId="primary", body=event_body)
        execute = request.execute
    except HttpError:
        error = "Calendar service was unavailable before insertion."
        return _calendar_not_attempted(f"Google Calendar API error: {error}")
    except Exception:
        error = "Calendar service was unavailable before insertion."
        return _calendar_not_attempted(f"Calendar event creation failed: {error}")

    # From this point onward an exception cannot prove that the server did not
    # commit. Never retry, including HTTP errors whose dispatch is uncertain.
    try:
        created_event = execute()
    except Exception:
        return calendar_creation_unknown()
    if not _confirmed_insert_response(created_event, event_body):
        return calendar_creation_unknown()

    # Acknowledged creation is irreversible by presentation/enrichment errors.
    details_unavailable = False
    try:
        event = normalise_event(created_event)
        if not isinstance(event, dict):
            raise ValueError("Unavailable event details.")
    except Exception:
        details_unavailable = True
        event = {
            "summary": summary,
            "start": event_body["start"]["dateTime"],
            "end": event_body["end"]["dateTime"],
            "all_day": False,
        }
    result = {
        "success": True,
        "status": "confirmed_created",
        "dispatch_attempted": True,
        "retryable": False,
        "message": "Calendar event created.",
        "event": event,
        "details_unavailable": details_unavailable,
    }
    if details_unavailable:
        result["note"] = "Additional event details are unavailable."
    return result


if __name__ == "__main__":
    print("TODAY:")
    print(
        json.dumps(
            get_calendar_events("today"),
            indent=2
        )
    )

    print()

    print("NEXT EVENT:")
    print(
        json.dumps(
            get_next_calendar_event(),
            indent=2
        )
    )
