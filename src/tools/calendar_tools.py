import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


PROJECT_ROOT = Path(__file__).resolve().parents[2]

GOOGLE_DATA_DIR = PROJECT_ROOT / "data" / "google"

CREDENTIALS_PATH = GOOGLE_DATA_DIR / "credentials.json"
TOKEN_PATH = GOOGLE_DATA_DIR / "token.json"


SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly"
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

    token.json is reused between runs. If the access token
    expires and a refresh token exists, Google automatically
    refreshes it.
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
    Create an authenticated read-only Google Calendar client.
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


if __name__ == "__main__":
    print("TODAY:")
    print(
        json.dumps(
            get_calendar_events("today"),
            indent=2
        )
    )

    print()

    print("TOMORROW:")
    print(
        json.dumps(
            get_calendar_events("tomorrow"),
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