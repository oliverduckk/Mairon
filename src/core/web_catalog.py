import re
from typing import Dict, Optional
from urllib.parse import urlencode


TRUSTED_SITES: Dict[str, dict] = {
    "google": {
        "display_name": "Google",
        "aliases": (
            "google",
            "google search",
        ),
        "home_url": "https://www.google.com/",
        "search_url": "https://www.google.com/search",
        "search_param": "q",
    },
    "youtube": {
        "display_name": "YouTube",
        "aliases": (
            "youtube",
            "you tube",
            "yt",
        ),
        "home_url": "https://www.youtube.com/",
        "search_url": "https://www.youtube.com/results",
        "search_param": "search_query",
    },
    "reddit": {
        "display_name": "Reddit",
        "aliases": (
            "reddit",
        ),
        "home_url": "https://www.reddit.com/",
        "search_url": "https://www.reddit.com/search/",
        "search_param": "q",
    },
    "github": {
        "display_name": "GitHub",
        "aliases": (
            "github",
            "git hub",
        ),
        "home_url": "https://github.com/",
        "search_url": "https://github.com/search",
        "search_param": "q",
    },
    "gmail": {
        "display_name": "Gmail",
        "aliases": (
            "gmail",
            "google mail",
        ),
        "home_url": "https://mail.google.com/",
        "search_url": None,
        "search_param": None,
    },
}


def get_trusted_site(
    site_id: str,
) -> Optional[dict]:
    value = str(
        site_id
        or ""
    ).strip().lower()

    metadata = TRUSTED_SITES.get(
        value
    )

    if metadata is None:
        return None

    result = dict(
        metadata
    )

    result[
        "site_id"
    ] = value

    return result


def trusted_site_display_name(
    site_id: str,
) -> str:
    site = get_trusted_site(
        site_id
    )

    if site is None:
        return str(
            site_id
            or "that site"
        ).strip()

    return str(
        site.get(
            "display_name"
        )
        or site_id
    )


def site_supports_search(
    site_id: str,
) -> bool:
    site = get_trusted_site(
        site_id
    )

    if site is None:
        return False

    return bool(
        site.get(
            "search_url"
        )
        and site.get(
            "search_param"
        )
    )


def build_trusted_site_url(
    site_id: str,
    query: Optional[str] = None,
) -> Optional[str]:
    """
    Construct a URL only from Core-owned trusted site metadata.

    Query text is inert data passed through urllib.urlencode. It can never
    replace the scheme, host, path, or parameter name selected by Core.
    """

    site = get_trusted_site(
        site_id
    )

    if site is None:
        return None

    if query is None:
        return str(
            site[
                "home_url"
            ]
        )

    value = str(
        query
        or ""
    ).strip()

    if (
        not value
        or len(
            value
        ) > 500
    ):
        return None

    search_url = site.get(
        "search_url"
    )

    search_param = site.get(
        "search_param"
    )

    if (
        not search_url
        or not search_param
    ):
        return None

    return (
        str(
            search_url
        )
        + "?"
        + urlencode({
            str(
                search_param
            ): value,
        })
    )


def _normalise(
    text: str,
) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(
            text
            or ""
        ).strip().lower(),
    )


def _site_alias_candidates():
    candidates = []

    for site_id, metadata in (
        TRUSTED_SITES.items()
    ):
        for alias in metadata.get(
            "aliases",
            (),
        ):
            value = _normalise(
                alias
            )

            candidates.append(
                (
                    len(
                        value
                    ),
                    value,
                    site_id,
                )
            )

    return sorted(
        candidates,
        reverse=True,
    )


def resolve_site_alias(
    text: str,
) -> Optional[str]:
    value = _normalise(
        text
    )

    if not value:
        return None

    for _, alias, site_id in (
        _site_alias_candidates()
    ):
        if value == alias:
            return site_id

    return None


def _active_browser_site(
    conversation_state,
) -> Optional[str]:
    if conversation_state is None:
        return None

    value = str(
        getattr(
            conversation_state,
            "active_browser_site",
            "",
        )
        or ""
    ).strip().lower()

    if value not in TRUSTED_SITES:
        return None

    return value


COMPOUND_CHROME_SEARCH = re.compile(
    r"^\s*(?:open|launch|start)\s+(?:google\s+)?chrome\s+and\s+"
    r"(?:search|google|look\s+up)(?:\s+for)?\s+"
    r"(?P<query>.+?)\s*[.!?]*$",
    flags=re.IGNORECASE,
)

COMPOUND_SITE_SEARCH = re.compile(
    r"^\s*(?:open|go\s+to|visit|launch)\s+"
    r"(?P<site>.+?)\s+and\s+"
    r"(?:search|look\s+up)(?:\s+for)?\s+"
    r"(?P<query>.+?)\s*[.!?]*$",
    flags=re.IGNORECASE,
)

SEARCH_SITE_FOR = re.compile(
    r"^\s*(?:search|look\s+up)\s+"
    r"(?P<site>.+?)(?:\s+for)\s+"
    r"(?P<query>.+?)\s*[.!?]*$",
    flags=re.IGNORECASE,
)

SEARCH_QUERY_ON_SITE = re.compile(
    r"^\s*(?:search|look\s+up)(?:\s+for)?\s+"
    r"(?P<query>.+?)\s+(?:on|in)\s+"
    r"(?P<site>.+?)\s*[.!?]*$",
    flags=re.IGNORECASE,
)

OPEN_SITE = re.compile(
    r"^\s*(?:open|go\s+to|visit|launch)\s+"
    r"(?:the\s+)?(?P<site>.+?)\s*[.!?]*$",
    flags=re.IGNORECASE,
)

GOOGLE_SHORTCUT = re.compile(
    r"^\s*google\s+(?P<query>.+?)\s*[.!?]*$",
    flags=re.IGNORECASE,
)

SEARCH_GOOGLE = re.compile(
    r"^\s*search\s+google(?:\s+for)?\s+"
    r"(?P<query>.+?)\s*[.!?]*$",
    flags=re.IGNORECASE,
)

ACTIVE_SITE_SEARCH = re.compile(
    r"^\s*(?:search|look\s+up)(?:\s+for)?\s+"
    r"(?P<query>.+?)\s*[.!?]*$",
    flags=re.IGNORECASE,
)


def _clean_query(
    value: str,
) -> Optional[str]:
    query = str(
        value
        or ""
    ).strip()

    if (
        not query
        or len(
            query
        ) > 500
    ):
        return None

    return query


def _build_search_request(
    site_id: str,
    query: str,
    inherited: bool = False,
) -> Optional[dict]:
    if not site_supports_search(
        site_id
    ):
        return None

    value = _clean_query(
        query
    )

    if value is None:
        return None

    return {
        "action": "search",
        "site_id": site_id,
        "display_name": trusted_site_display_name(
            site_id
        ),
        "query": value,
        "inherited": inherited,
    }


def extract_browser_action_request(
    text: str,
    conversation_state=None,
) -> Optional[dict]:
    """
    Resolve a bounded Chrome navigation/search action.

    Core owns the trusted destination. User query text remains data only.

    A bare "search for X" is accepted only when Core already has one active
    trusted browser site that supports search. This avoids globally hijacking
    generic Mairon search/research requests.
    """

    raw = str(
        text
        or ""
    ).strip()

    if not raw:
        return None

    match = COMPOUND_CHROME_SEARCH.match(
        raw
    )

    if match:
        return _build_search_request(
            "google",
            match.group(
                "query"
            ),
        )

    match = SEARCH_GOOGLE.match(
        raw
    )

    if match:
        return _build_search_request(
            "google",
            match.group(
                "query"
            ),
        )

    match = GOOGLE_SHORTCUT.match(
        raw
    )

    if match:
        return _build_search_request(
            "google",
            match.group(
                "query"
            ),
        )

    match = COMPOUND_SITE_SEARCH.match(
        raw
    )

    if match:
        site_id = resolve_site_alias(
            match.group(
                "site"
            )
        )

        if site_id:
            return _build_search_request(
                site_id,
                match.group(
                    "query"
                ),
            )

    match = SEARCH_SITE_FOR.match(
        raw
    )

    if match:
        site_id = resolve_site_alias(
            match.group(
                "site"
            )
        )

        if site_id:
            return _build_search_request(
                site_id,
                match.group(
                    "query"
                ),
            )

    match = SEARCH_QUERY_ON_SITE.match(
        raw
    )

    if match:
        site_id = resolve_site_alias(
            match.group(
                "site"
            )
        )

        if site_id:
            return _build_search_request(
                site_id,
                match.group(
                    "query"
                ),
            )

    match = OPEN_SITE.match(
        raw
    )

    if match:
        site_id = resolve_site_alias(
            match.group(
                "site"
            )
        )

        if site_id:
            return {
                "action": "open",
                "site_id": site_id,
                "display_name": trusted_site_display_name(
                    site_id
                ),
                "query": None,
                "inherited": False,
            }

    match = ACTIVE_SITE_SEARCH.match(
        raw
    )

    if match:
        site_id = _active_browser_site(
            conversation_state
        )

        if (
            site_id
            and site_supports_search(
                site_id
            )
        ):
            return _build_search_request(
                site_id,
                match.group(
                    "query"
                ),
                inherited=True,
            )

    return None
