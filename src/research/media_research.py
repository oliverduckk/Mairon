import json
import re
from urllib.parse import urlparse

from tools.tool_registry import execute_tool


# --------------------------------------------------
# Research policy
# --------------------------------------------------

FACT_CHECK_PATTERNS = [
    r"\bwhat do you mean\b",
    r"\bare you sure\b",
    r"\bis that true\b",
    r"\bis this true\b",
    r"\byou said\b",
    r"\bdidn't you say\b",
    r"\bdid you say\b",
    r"\bwtf\b",
    r"\bwhat the fuck\b",
    r"\breally\??$",
]

SPECIFIC_FACT_PATTERNS = [
    r"\bwho (?:is|was|did|killed|fought|beat|joined|left)\b",
    r"\bwhat (?:is|was|happened|happens|did)\b",
    r"\bwhy did\b",
    r"\bwhen did\b",
    r"\bwhere did\b",
    r"\bdoes .{1,100}\b(?:die|join|leave|return|become|win|lose)\b",
    r"\bis .{1,100}\b(?:dead|alive|canon|confirmed)\b",
    r"\bhow did\b",
    r"\bwhich (?:arc|chapter|episode|volume|season)\b",
]

CURRENT_PATTERNS = [
    r"\blatest\b",
    r"\bnewest\b",
    r"\bcurrent\b",
    r"\bthis week\b",
    r"\btoday\b",
    r"\bjust released\b",
]

OFFICIALISH_DOMAIN_HINTS = [
    "one-piece.com",
    "shonenjump.com",
    "viz.com",
    "mangaplus.shueisha.co.jp",
    "shueisha.co.jp",
    "crunchyroll.com",
    "re-zero.com",
    "kadokawa.co.jp",
    "kadokawa.com",
    "yenpress.com",
    "aniplex.co.jp",
    "netflix.com",
    "imdb.com",
    "wikipedia.org",
]


def _normalise(text):
    return re.sub(
        r"\s+",
        " ",
        str(text or "").strip().lower(),
    )


def _matches_any(
    text,
    patterns,
):
    return any(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        for pattern in patterns
    )


def should_research_media_turn(
    user_input,
    conversation_policy,
    spoiler_context,
):
    """
    Decide whether ordinary model memory is not enough.

    Research is deliberately biased toward:
    - current/release-sensitive discussion;
    - specific factual/canon questions;
    - fact-checks/corrections;
    - subjective ranking/opinion turns where invented canon would be a
      particularly bad way to justify the opinion.

    Spoiler-progress questions themselves are never researched until
    Core knows the spoiler ceiling.
    """

    if spoiler_context.get(
        "must_ask_progress"
    ):
        return False

    if spoiler_context.get(
        "must_complete_progress"
    ):
        return False

    if spoiler_context.get(
        "must_confirm_latest"
    ):
        return False

    if (
        spoiler_context.get(
            "progress_updated"
        )
        and not spoiler_context.get(
            "pending_question"
        )
    ):
        return False

    title = spoiler_context.get(
        "title"
    )

    if not title:
        return False

    text = _normalise(
        user_input
    )

    pending_question = spoiler_context.get(
        "pending_question"
    )

    if pending_question:
        text = (
            text
            + " "
            + _normalise(
                pending_question
            )
        )

    if _matches_any(
        text,
        FACT_CHECK_PATTERNS,
    ):
        return True

    if _matches_any(
        text,
        SPECIFIC_FACT_PATTERNS,
    ):
        return True

    if _matches_any(
        text,
        CURRENT_PATTERNS,
    ):
        return True

    if conversation_policy.get(
        "opinion_turn"
    ):
        return True

    if conversation_policy.get(
        "challenge_turn"
    ):
        return True

    return False


def _profile_summary(
    spoiler_context,
):
    profile = spoiler_context.get(
        "profile"
    ) or {}

    pieces = []

    medium = profile.get(
        "medium"
    )

    if medium:
        pieces.append(
            f"medium={medium}"
        )

    progress_type = profile.get(
        "progress_type"
    )

    progress_value = profile.get(
        "progress_value"
    )

    if (
        progress_type
        and progress_value is not None
    ):
        pieces.append(
            f"{progress_type}={progress_value}"
        )

    if profile.get(
        "caught_up"
    ):
        pieces.append(
            "caught_up=true"
        )

    return (
        ", ".join(
            pieces
        )
        if pieces
        else "unknown"
    )


def build_media_search_query(
    user_input,
    spoiler_context,
):
    title = spoiler_context.get(
        "title"
    ) or ""

    target_question = (
        spoiler_context.get(
            "pending_question"
        )
        or user_input
    )

    profile = spoiler_context.get(
        "profile"
    ) or {}

    medium = profile.get(
        "medium"
    )

    query = (
        f"{title} {target_question}"
    ).strip()

    # Adding the medium helps searches stay near Oliver's spoiler-safe
    # source boundary without including personal information.
    if medium:
        query += (
            " "
            + medium.replace(
                "_",
                " ",
            )
        )

    query += (
        " official canon source"
    )

    return re.sub(
        r"\s+",
        " ",
        query,
    ).strip()


def _domain_priority(
    url,
):
    try:
        host = (
            urlparse(
                url
            ).netloc
            or ""
        ).lower()
    except Exception:
        return 0

    for index, domain in enumerate(
        OFFICIALISH_DOMAIN_HINTS
    ):
        if (
            host == domain
            or host.endswith(
                "."
                + domain
            )
        ):
            return (
                len(
                    OFFICIALISH_DOMAIN_HINTS
                )
                - index
            )

    return 0


def _extract_search_results(
    search_result,
):
    if not isinstance(
        search_result,
        dict,
    ):
        return []

    if not search_result.get(
        "success"
    ):
        return []

    results = search_result.get(
        "results",
        []
    )

    if not isinstance(
        results,
        list,
    ):
        return []

    cleaned = []

    for result in results:
        if not isinstance(
            result,
            dict,
        ):
            continue

        url = result.get(
            "url"
        )

        if not (
            isinstance(
                url,
                str,
            )
            and (
                url.startswith(
                    "https://"
                )
                or url.startswith(
                    "http://"
                )
            )
        ):
            continue

        cleaned.append({
            "title": result.get(
                "title"
            ),
            "url": url,
            "snippet": (
                result.get(
                    "content"
                )
                or result.get(
                    "snippet"
                )
                or result.get(
                    "description"
                )
            ),
            "domain_priority": _domain_priority(
                url
            ),
        })

    cleaned.sort(
        key=lambda item: item[
            "domain_priority"
        ],
        reverse=True,
    )

    return cleaned


def gather_media_research(
    user_input,
    spoiler_context,
    max_reads=2,
):
    """
    Gather public evidence using Mairon's existing allowlisted web
    tools.

    The raw results are for INTERNAL synthesis only. They should never
    be spoken directly because search snippets/pages may contain
    material beyond Oliver's spoiler ceiling.
    """

    query = build_media_search_query(
        user_input=user_input,
        spoiler_context=spoiler_context,
    )

    search_result = execute_tool(
        "web_search",
        {
            "query": query,
            "topic": "general",
            "time_range": (
                "year"
                if spoiler_context.get(
                    "release_sensitive"
                )
                else "none"
            ),
        },
    )

    results = _extract_search_results(
        search_result
    )

    reads = []

    for result in results[
        :max_reads
    ]:
        read_result = execute_tool(
            "web_read",
            {
                "url": result[
                    "url"
                ],
                "focus": (
                    spoiler_context.get(
                        "pending_question"
                    )
                    or user_input
                ),
            },
        )

        reads.append({
            "title": result.get(
                "title"
            ),
            "url": result[
                "url"
            ],
            "search_snippet": result.get(
                "snippet"
            ),
            "read_result": read_result,
        })

    return {
        "query": query,
        "topic": spoiler_context.get(
            "title"
        ),
        "spoiler_profile": _profile_summary(
            spoiler_context
        ),
        "search_result_count": len(
            results
        ),
        "sources": reads,
        "success": bool(
            reads
        ),
    }


def build_internal_research_packet(
    research_result,
):
    """
    Human-readable internal packet for isolated evidence synthesis.
    """

    if not research_result.get(
        "success"
    ):
        return (
            "MEDIA RESEARCH RESULT:\n"
            "No readable public sources were retrieved."
        )

    lines = [
        "MEDIA RESEARCH RESULT:",
        (
            "Research query: "
            + str(
                research_result.get(
                    "query"
                )
            )
        ),
        (
            "Topic: "
            + str(
                research_result.get(
                    "topic"
                )
            )
        ),
        (
            "Spoiler profile: "
            + str(
                research_result.get(
                    "spoiler_profile"
                )
            )
        ),
        "",
    ]

    for index, source in enumerate(
        research_result.get(
            "sources",
            []
        ),
        start=1,
    ):
        lines.extend([
            f"SOURCE {index}",
            (
                "Title: "
                + str(
                    source.get(
                        "title"
                    )
                )
            ),
            (
                "URL: "
                + str(
                    source.get(
                        "url"
                    )
                )
            ),
            (
                "Search snippet: "
                + str(
                    source.get(
                        "search_snippet"
                    )
                )
            ),
            "Read result:",
            json.dumps(
                source.get(
                    "read_result"
                ),
                ensure_ascii=False,
            ),
            "",
        ])

    return "\n".join(
        lines
    )
