import base64
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


PROJECT_ROOT = Path(__file__).resolve().parents[2]

GOOGLE_DATA_DIR = PROJECT_ROOT / "data" / "google"

CREDENTIALS_PATH = GOOGLE_DATA_DIR / "credentials.json"
TOKEN_PATH = GOOGLE_DATA_DIR / "gmail_token.json"


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly"
]


# --------------------------------------------------
# Email text cleanup
# --------------------------------------------------

INVISIBLE_EMAIL_CHARACTERS = {
    ord("\u034f"): None,  # Combining Grapheme Joiner
    ord("\u200b"): None,  # Zero Width Space
    ord("\u200c"): None,  # Zero Width Non-Joiner
    ord("\u200d"): None,  # Zero Width Joiner
    ord("\u200e"): None,  # Left-to-Right Mark
    ord("\u200f"): None,  # Right-to-Left Mark
    ord("\u202a"): None,
    ord("\u202b"): None,
    ord("\u202c"): None,
    ord("\u202d"): None,
    ord("\u202e"): None,
    ord("\u2060"): None,  # Word Joiner
    ord("\u2061"): None,
    ord("\u2062"): None,
    ord("\u2063"): None,
    ord("\u2064"): None,
    ord("\u2066"): None,
    ord("\u2067"): None,
    ord("\u2068"): None,
    ord("\u2069"): None,
    ord("\ufeff"): None,  # Zero Width No-Break Space / BOM
}


def clean_email_text(text):
    """
    Remove invisible formatting characters that can appear
    in promotional or heavily formatted email content.

    These characters add no useful semantic information for
    Mairon and can distract the local model.
    """

    if not text:
        return ""

    return str(text).translate(
        INVISIBLE_EMAIL_CHARACTERS
    )


# --------------------------------------------------
# Authentication
# --------------------------------------------------

def get_credentials():
    """
    Load Gmail-specific OAuth credentials.

    Gmail uses its own token so Gmail authorization
    remains separate from Calendar authorization.
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


def create_gmail_service():
    """
    Create an authenticated read-only Gmail client.
    """

    credentials = get_credentials()

    return build(
        "gmail",
        "v1",
        credentials=credentials
    )


# --------------------------------------------------
# Message parsing
# --------------------------------------------------

def get_header(
    headers,
    name
):
    """
    Retrieve one email header by name.
    """

    for header in headers:
        if (
            header.get(
                "name",
                ""
            ).lower()
            == name.lower()
        ):
            return header.get(
                "value"
            )

    return None


def decode_body(
    data
):
    """
    Decode Gmail's URL-safe base64 body content.
    """

    if not data:
        return ""

    try:
        decoded = base64.urlsafe_b64decode(
            data.encode("utf-8")
        )

        return decoded.decode(
            "utf-8",
            errors="replace"
        )

    except Exception:
        return ""


def extract_plain_text(
    payload
):
    """
    Recursively locate plain-text email content.

    HTML content is deliberately ignored for now.
    """

    mime_type = payload.get(
        "mimeType",
        ""
    )

    body = payload.get(
        "body",
        {}
    )

    if mime_type == "text/plain":
        return decode_body(
            body.get("data")
        )

    parts = payload.get(
        "parts",
        []
    )

    for part in parts:
        text = extract_plain_text(
            part
        )

        if text:
            return text

    return ""


def normalise_message_summary(
    message
):
    """
    Return only lightweight email metadata.

    Search results deliberately do NOT include the full
    email body.
    """

    payload = message.get(
        "payload",
        {}
    )

    headers = payload.get(
        "headers",
        []
    )

    return {
        "message_id": message.get(
            "id"
        ),
        "from": clean_email_text(
            get_header(
                headers,
                "From"
            )
        ),
        "subject": clean_email_text(
            get_header(
                headers,
                "Subject"
            ) or "(No subject)"
        ),
        "date": get_header(
            headers,
            "Date"
        ),
        "snippet": clean_email_text(
            message.get(
                "snippet",
                ""
            )
        ),
        "unread": (
            "UNREAD"
            in message.get(
                "labelIds",
                []
            )
        )
    }


def normalise_full_message(
    message
):
    """
    Return the contents of one explicitly selected email.

    The body remains size-limited to avoid overwhelming
    local model context.
    """

    result = normalise_message_summary(
        message
    )

    payload = message.get(
        "payload",
        {}
    )

    headers = payload.get(
        "headers",
        []
    )

    body = clean_email_text(
        extract_plain_text(
            payload
        )
    ).strip()

    MAX_BODY_CHARACTERS = 5000

    if len(body) > MAX_BODY_CHARACTERS:
        body = (
            body[:MAX_BODY_CHARACTERS]
            + "..."
        )

    result["to"] = clean_email_text(
        get_header(
            headers,
            "To"
        )
    )

    result["body"] = body

    return result


# --------------------------------------------------
# Gmail API helpers
# --------------------------------------------------

def get_message_summaries(
    service,
    message_ids
):
    """
    Fetch lightweight metadata for Gmail messages.
    """

    messages = []

    for item in message_ids:
        message_id = item.get(
            "id"
        )

        if not message_id:
            continue

        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=[
                    "From",
                    "Subject",
                    "Date"
                ]
            )
            .execute()
        )

        messages.append(
            normalise_message_summary(
                message
            )
        )

    return messages


def search_emails(
    query,
    max_results=10
):
    """
    Low-level Gmail search.
    """

    query = (
        query
        or ""
    ).strip()

    if not query:
        return {
            "success": False,
            "message": (
                "Email search query cannot be empty."
            )
        }

    max_results = max(
        1,
        min(
            int(max_results),
            20
        )
    )

    try:
        print(
            f"[Gmail] Query: {query}"
        )

        service = create_gmail_service()

        response = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=max_results
            )
            .execute()
        )

        message_ids = response.get(
            "messages",
            []
        )

        messages = get_message_summaries(
            service,
            message_ids
        )

        return {
            "success": True,
            "gmail_query": query,
            "email_count": len(messages),
            "emails": messages
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
                f"Gmail API error: {error}"
            )
        }

    except Exception as error:
        return {
            "success": False,
            "message": (
                f"Gmail request failed: {error}"
            )
        }


# --------------------------------------------------
# Search query helpers
# --------------------------------------------------

def sanitise_search_text(
    search_text
):
    """
    Remove characters that could interfere with the
    Gmail query syntax Mairon constructs internally.
    """

    search_text = (
        search_text
        or ""
    ).strip()

    return (
        search_text
        .replace('"', "")
        .replace("{", "")
        .replace("}", "")
    )


def build_exact_query(
    search_text,
    days,
    unread_only
):
    """
    Build a narrow exact-phrase Gmail search.
    """

    query_parts = [
        f"newer_than:{days}d"
    ]

    if unread_only:
        query_parts.append(
            "is:unread"
        )

    if search_text:
        query_parts.append(
            f'"{search_text}"'
        )

    return " ".join(
        query_parts
    )


def build_loose_query(
    search_text,
    days,
    unread_only
):
    """
    Build a broader keyword search.
    """

    query_parts = [
        f"newer_than:{days}d"
    ]

    if unread_only:
        query_parts.append(
            "is:unread"
        )

    if search_text:
        query_parts.append(
            search_text
        )

    return " ".join(
        query_parts
    )


# --------------------------------------------------
# AI-facing Gmail operations
# --------------------------------------------------

def find_emails(
    search_text="",
    days=30,
    unread_only=False,
    max_results=10
):
    """
    Find emails using structured parameters.

    Search strategy:

    1. Try the requested time range using an exact phrase.
    2. If that fails, retry using loose keywords.
    3. If the period was narrower than 30 days and still
       nothing was found, expand to 30 days.
    4. Try exact and loose matching again.
    """

    search_text = sanitise_search_text(
        search_text
    )

    days = max(
        1,
        min(
            int(days),
            365
        )
    )

    max_results = max(
        1,
        min(
            int(max_results),
            20
        )
    )

    # --------------------------------------------------
    # Search 1:
    # requested period + exact phrase
    # --------------------------------------------------

    exact_query = build_exact_query(
        search_text,
        days,
        unread_only
    )

    exact_result = search_emails(
        query=exact_query,
        max_results=max_results
    )

    if not exact_result.get(
        "success"
    ):
        return exact_result

    if exact_result.get(
        "email_count",
        0
    ) > 0:
        exact_result[
            "search_strategy"
        ] = "exact"

        exact_result[
            "search_expanded"
        ] = False

        return exact_result

    # --------------------------------------------------
    # Search 2:
    # requested period + loose keywords
    # --------------------------------------------------

    if search_text:
        print(
            "[Gmail] Exact phrase returned no matches. "
            "Retrying with loose keywords."
        )

        loose_query = build_loose_query(
            search_text,
            days,
            unread_only
        )

        loose_result = search_emails(
            query=loose_query,
            max_results=max_results
        )

        if not loose_result.get(
            "success"
        ):
            return loose_result

        if loose_result.get(
            "email_count",
            0
        ) > 0:
            loose_result[
                "search_strategy"
            ] = "loose_keywords"

            loose_result[
                "search_expanded"
            ] = False

            return loose_result

    # --------------------------------------------------
    # Search 3:
    # expand narrow searches to 30 days
    # --------------------------------------------------

    if (
        search_text
        and days < 30
    ):
        expanded_days = 30

        print(
            "[Gmail] No matches in narrow window. "
            f"Expanding search to {expanded_days} days."
        )

        expanded_exact_query = (
            build_exact_query(
                search_text,
                expanded_days,
                unread_only
            )
        )

        expanded_exact_result = (
            search_emails(
                query=expanded_exact_query,
                max_results=max_results
            )
        )

        if not expanded_exact_result.get(
            "success"
        ):
            return expanded_exact_result

        if expanded_exact_result.get(
            "email_count",
            0
        ) > 0:
            expanded_exact_result[
                "search_strategy"
            ] = "expanded_exact"

            expanded_exact_result[
                "search_expanded"
            ] = True

            expanded_exact_result[
                "original_search_days"
            ] = days

            expanded_exact_result[
                "expanded_search_days"
            ] = expanded_days

            return expanded_exact_result

        print(
            "[Gmail] Expanded exact search returned no matches. "
            "Retrying expanded search with loose keywords."
        )

        expanded_loose_query = (
            build_loose_query(
                search_text,
                expanded_days,
                unread_only
            )
        )

        expanded_loose_result = (
            search_emails(
                query=expanded_loose_query,
                max_results=max_results
            )
        )

        if not expanded_loose_result.get(
            "success"
        ):
            return expanded_loose_result

        expanded_loose_result[
            "search_strategy"
        ] = "expanded_loose_keywords"

        expanded_loose_result[
            "search_expanded"
        ] = True

        expanded_loose_result[
            "original_search_days"
        ] = days

        expanded_loose_result[
            "expanded_search_days"
        ] = expanded_days

        return expanded_loose_result

    return {
        "success": True,
        "gmail_query": (
            build_loose_query(
                search_text,
                days,
                unread_only
            )
        ),
        "email_count": 0,
        "emails": [],
        "search_strategy": "all_attempts_exhausted",
        "search_expanded": False
    }


def get_recent_emails(
    days=7,
    max_results=10,
    unread_only=False
):
    """
    Retrieve recent email summaries without a keyword.

    General recent-mail requests remain strictly limited
    to the requested period.
    """

    days = max(
        1,
        min(
            int(days),
            90
        )
    )

    max_results = max(
        1,
        min(
            int(max_results),
            20
        )
    )

    query_parts = [
        f"newer_than:{days}d"
    ]

    if unread_only:
        query_parts.append(
            "is:unread"
        )

    query = " ".join(
        query_parts
    )

    return search_emails(
        query=query,
        max_results=max_results
    )


def read_email(
    message_id
):
    """
    Read the contents of one explicitly selected email.

    This is strictly read-only.
    """

    message_id = (
        message_id
        or ""
    ).strip()

    if not message_id:
        return {
            "success": False,
            "message": (
                "A Gmail message ID is required."
            )
        }

    try:
        service = create_gmail_service()

        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="full"
            )
            .execute()
        )

        return {
            "success": True,
            "email": normalise_full_message(
                message
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
                f"Gmail API error: {error}"
            )
        }

    except Exception as error:
        return {
            "success": False,
            "message": (
                f"Gmail request failed: {error}"
            )
        }