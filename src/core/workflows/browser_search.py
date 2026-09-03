from typing import Optional

from core.evidence import (
    Evidence,
    EvidenceBundle,
)
from core.web_catalog import (
    get_trusted_site,
    trusted_site_display_name,
)
from core.workflow_result import (
    WorkflowResult,
)
from tools.desktop_tools import (
    open_chrome_trusted_site,
)


def open_browser_action(
    site_id: str,
    query: Optional[str] = None,
) -> WorkflowResult:
    """
    Deterministically open/search one trusted website in Chrome.
    """

    site_id = str(
        site_id
        or ""
    ).strip().lower()

    site = get_trusted_site(
        site_id
    )

    if site is None:
        return WorkflowResult(
            success=False,
            status="untrusted_site",
            error=(
                "That website is not in Mairon's trusted browser catalogue."
            ),
            data={
                "site_id": site_id,
                "query": query,
            },
        )

    query_value = None

    if query is not None:
        query_value = str(
            query
            or ""
        ).strip()

        if (
            not query_value
            or len(
                query_value
            ) > 500
        ):
            return WorkflowResult(
                success=False,
                status="invalid_search_query",
                error=(
                    "That browser search query is empty or too long."
                ),
                data={
                    "site_id": site_id,
                },
            )

    print(
        "[Tool] Mairon Core required: open_chrome_trusted_site"
    )

    result = open_chrome_trusted_site(
        site_id=site_id,
        query=query_value,
    )

    if not isinstance(
        result,
        dict,
    ):
        return WorkflowResult(
            success=False,
            status="unexpected_tool_result",
            error=(
                "The desktop browser layer returned an unexpected result."
            ),
            data={
                "site_id": site_id,
                "query": query_value,
                "raw_result": str(
                    result
                ),
            },
        )

    if result.get(
        "success"
    ) is not True:
        return WorkflowResult(
            success=False,
            status=(
                result.get(
                    "status"
                )
                or "browser_action_failed"
            ),
            error=(
                result.get(
                    "message"
                )
                or "I couldn't complete that Chrome action."
            ),
            data={
                "site_id": site_id,
                "query": query_value,
                "tool_result": result,
            },
        )

    display_name = trusted_site_display_name(
        site_id
    )

    if query_value is None:
        answer_fact = (
            f"{display_name}'s open."
        )
    else:
        answer_fact = (
            f'Searching {display_name} for "{query_value}".'
        )

    evidence = EvidenceBundle(
        authority="desktop",
        success=True,
    )

    evidence.add(
        Evidence(
            claim=(
                "The local desktop layer opened Chrome to a Core-approved "
                f"{display_name} destination."
            ),
            provenance="desktop_tool",
            confidence="verified",
            source_name="open_chrome_trusted_site",
            data={
                "site_id": site_id,
                "query": query_value,
                "url": result.get(
                    "url"
                ),
            },
        )
    )

    return WorkflowResult(
        success=True,
        status=(
            "browser_search_opened"
            if query_value is not None
            else "browser_site_opened"
        ),
        answer_fact=answer_fact,
        evidence=evidence,
        data={
            "site_id": site_id,
            "query": query_value,
            "tool_result": result,
        },
    )


def open_browser_search(
    query: str,
) -> WorkflowResult:
    """
    Backward-compatible Google-search wrapper for Phase 8.3 callers/tests.
    """

    return open_browser_action(
        site_id="google",
        query=query,
    )
