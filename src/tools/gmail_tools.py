import base64
import html
import re
from html.parser import HTMLParser
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
        # Gmail commonly omits base64 padding. urlsafe_b64decode accepts
        # padded input reliably, so restore it without changing payload data.
        value = str(
            data
        ).strip()

        padding = (
            -len(value)
            % 4
        )

        if padding:
            value += (
                "="
                * padding
            )

        decoded = base64.urlsafe_b64decode(
            value.encode(
                "utf-8"
            )
        )

        return decoded.decode(
            "utf-8",
            errors="replace"
        )

    except Exception:
        return ""


def _extract_first_mime_body(
    payload,
    wanted_mime_type
):
    """
    Recursively return the first inline MIME part of the requested type.

    Gmail multipart/alternative commonly contains both text/plain and
    text/html. Callers deliberately request text/plain first.
    """

    if not isinstance(
        payload,
        dict,
    ):
        return ""

    mime_type = str(
        payload.get(
            "mimeType",
            "",
        )
        or ""
    ).lower()

    body = payload.get(
        "body",
        {},
    )

    if (
        mime_type
        == wanted_mime_type
        and isinstance(
            body,
            dict,
        )
    ):
        decoded = decode_body(
            body.get(
                "data"
            )
        )

        if decoded:
            return decoded

    for part in (
        payload.get(
            "parts",
            [],
        )
        or []
    ):
        text = _extract_first_mime_body(
            part,
            wanted_mime_type,
        )

        if text:
            return text

    return ""


class _VisibleHTMLTextExtractor(
    HTMLParser
):
    """
    Convert an email's visible HTML into plain text using only stdlib.

    Script/style/head content is discarded. Block boundaries are converted to
    newlines so paragraphs, lists and table rows remain readable rather than
    collapsing into one giant sentence.
    """

    BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "div",
        "dl",
        "dt",
        "dd",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "th",
        "tr",
        "ul",
    }

    IGNORED_TAGS = {
        "head",
        "script",
        "style",
        "svg",
        "noscript",
    }

    def __init__(
        self,
    ):
        super().__init__(
            convert_charrefs=True
        )

        self._pieces = []
        self._ignored_depth = 0

    def _newline(
        self,
    ):
        if (
            not self._pieces
            or self._pieces[
                -1
            ] != "\n"
        ):
            self._pieces.append(
                "\n"
            )

    def handle_starttag(
        self,
        tag,
        attrs,
    ):
        tag = str(
            tag
            or ""
        ).lower()

        if tag in self.IGNORED_TAGS:
            self._ignored_depth += 1
            return

        if self._ignored_depth:
            return

        if tag == "br":
            self._newline()

        elif tag in self.BLOCK_TAGS:
            self._newline()

    def handle_startendtag(
        self,
        tag,
        attrs,
    ):
        self.handle_starttag(
            tag,
            attrs,
        )

        self.handle_endtag(
            tag
        )

    def handle_endtag(
        self,
        tag,
    ):
        tag = str(
            tag
            or ""
        ).lower()

        if tag in self.IGNORED_TAGS:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return

        if self._ignored_depth:
            return

        if tag in self.BLOCK_TAGS:
            self._newline()

    def handle_data(
        self,
        data,
    ):
        if self._ignored_depth:
            return

        value = str(
            data
            or ""
        )

        if value:
            self._pieces.append(
                value
            )

    def text(
        self,
    ):
        raw = "".join(
            self._pieces
        )

        raw = html.unescape(
            raw
        )

        raw = clean_email_text(
            raw
        )

        lines = []

        for line in raw.splitlines():
            line = re.sub(
                r"[ \t\f\v]+",
                " ",
                line,
            ).strip()

            if line:
                lines.append(
                    line
                )

        return "\n".join(
            lines
        ).strip()


def html_to_visible_text(
    html_text
):
    """
    Safely reduce HTML email markup to visible local plain text.

    No network resources are fetched and no embedded code is executed.
    """

    if not html_text:
        return ""

    parser = (
        _VisibleHTMLTextExtractor()
    )

    try:
        parser.feed(
            str(
                html_text
            )
        )

        parser.close()

        return parser.text()

    except Exception:
        return ""


def extract_message_text(
    payload
):
    """
    Extract readable email body text.

    Authority order:
      1. genuine text/plain MIME content;
      2. visible text converted locally from text/html.

    HTML is a fallback only. This avoids needless markup while supporting
    senders that publish HTML-only messages.
    """

    plain = _extract_first_mime_body(
        payload,
        "text/plain",
    )

    plain = clean_email_text(
        plain
    ).strip()

    if plain:
        return (
            plain,
            "text/plain",
        )

    html_body = _extract_first_mime_body(
        payload,
        "text/html",
    )

    html_text = html_to_visible_text(
        html_body
    )

    if html_text:
        return (
            html_text,
            "text/html",
        )

    return (
        "",
        None,
    )


def extract_plain_text(
    payload
):
    """
    Backward-compatible body extractor.

    Historically this returned only text/plain. It now preserves that
    preference while safely falling back to visible HTML text.
    """

    text, _ = extract_message_text(
        payload
    )

    return text


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
        "internal_date_ms": (
            int(
                message.get(
                    "internalDate"
                )
            )
            if str(
                message.get(
                    "internalDate",
                    ""
                )
            ).isdigit()
            else None
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

    Plain-text MIME content is preferred. HTML-only messages are converted
    locally to visible text. The body remains size-limited to avoid
    overwhelming local model context.
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

    body, body_format = (
        extract_message_text(
            payload
        )
    )

    body = clean_email_text(
        body
    ).strip()

    MAX_BODY_CHARACTERS = 5000

    if len(body) > MAX_BODY_CHARACTERS:
        body = (
            body[
                :MAX_BODY_CHARACTERS
            ]
            + "..."
        )

    result["to"] = clean_email_text(
        get_header(
            headers,
            "To"
        )
    )

    result["body"] = body
    result["body_format"] = (
        body_format
    )

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
    unread_only,
    after_epoch=None,
    before_epoch=None
):
    """
    Build a narrow exact-phrase Gmail search.

    Rolling searches use newer_than:Nd.

    Exact local-day searches use epoch-second after:/before: bounds.
    Epoch bounds avoid Gmail's YYYY/MM/DD timezone ambiguity and let
    Mairon Core represent "today" and "yesterday" precisely.
    """

    query_parts = []

    if after_epoch is not None:
        query_parts.append(
            f"after:{int(after_epoch)}"
        )

    if before_epoch is not None:
        query_parts.append(
            f"before:{int(before_epoch)}"
        )

    if (
        after_epoch is None
        and before_epoch is None
    ):
        query_parts.append(
            f"newer_than:{days}d"
        )

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
    unread_only,
    after_epoch=None,
    before_epoch=None
):
    """
    Build a broader keyword search.

    Exact local-day bounds use epoch-second after:/before: operators.
    """

    query_parts = []

    if after_epoch is not None:
        query_parts.append(
            f"after:{int(after_epoch)}"
        )

    if before_epoch is not None:
        query_parts.append(
            f"before:{int(before_epoch)}"
        )

    if (
        after_epoch is None
        and before_epoch is None
    ):
        query_parts.append(
            f"newer_than:{days}d"
        )

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
    max_results=10,
    after_epoch=None,
    before_epoch=None,
    expand_search=True
):
    """
    Find emails using structured parameters.

    Search strategy for normal rolling searches:

    1. Try the requested time range using an exact phrase.
    2. If that fails, retry using loose keywords.
    3. If the period was narrower than 30 days and still nothing was
       found, optionally expand to 30 days.
    4. Try exact and loose matching again.

    Exact-window mode:

    If after_epoch and/or before_epoch are supplied, Gmail is constrained
    to those exact epoch-second boundaries and Core NEVER broadens the
    time window. This is used for requests such as "today" or "yesterday".
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

    if after_epoch is not None:
        after_epoch = max(
            0,
            int(after_epoch)
        )

    if before_epoch is not None:
        before_epoch = max(
            0,
            int(before_epoch)
        )

    if (
        after_epoch is not None
        and before_epoch is not None
        and before_epoch <= after_epoch
    ):
        return {
            "success": False,
            "message": (
                "Gmail exact search has an invalid time window."
            )
        }

    exact_window = (
        after_epoch is not None
        or before_epoch is not None
    )

    if exact_window:
        expand_search = False

    exact_query = build_exact_query(
        search_text,
        days,
        unread_only,
        after_epoch=after_epoch,
        before_epoch=before_epoch
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
        ] = (
            "exact_window_exact"
            if exact_window
            else "exact"
        )

        exact_result[
            "search_expanded"
        ] = False

        exact_result[
            "after_epoch"
        ] = after_epoch

        exact_result[
            "before_epoch"
        ] = before_epoch

        return exact_result

    if search_text:
        print(
            "[Gmail] Exact phrase returned no matches. "
            "Retrying with loose keywords."
        )

        loose_query = build_loose_query(
            search_text,
            days,
            unread_only,
            after_epoch=after_epoch,
            before_epoch=before_epoch
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
            ] = (
                "exact_window_loose_keywords"
                if exact_window
                else "loose_keywords"
            )

            loose_result[
                "search_expanded"
            ] = False

            loose_result[
                "after_epoch"
            ] = after_epoch

            loose_result[
                "before_epoch"
            ] = before_epoch

            return loose_result

    if exact_window:
        return {
            "success": True,
            "gmail_query": build_loose_query(
                search_text,
                days,
                unread_only,
                after_epoch=after_epoch,
                before_epoch=before_epoch
            ),
            "email_count": 0,
            "emails": [],
            "search_strategy": "exact_window_exhausted",
            "search_expanded": False,
            "after_epoch": after_epoch,
            "before_epoch": before_epoch
        }

    if (
        expand_search
        and search_text
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
