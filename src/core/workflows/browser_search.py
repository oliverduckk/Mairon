from typing import Optional

from core.desktop_agent_client import (
    open_trusted_browser_site_via_agent,
)
from core.evidence import (
    Evidence,
    EvidenceBundle,
)
from core.web_catalog import (
    build_trusted_site_url,
    get_trusted_site,
    trusted_site_display_name,
)
from core.workflow_result import (
    WorkflowResult,
)


def _browser_agent_unavailable_error(
    site_id: str,
    query: Optional[str],
) -> str:
    display_name = trusted_site_display_name(
        site_id
    )

    if query is None:
        return (
            "The Windows Desktop Agent isn't running, so I can't "
            f"open {display_name} right now."
        )

    return (
        "The Windows Desktop Agent isn't running, so I can't "
        f"search {display_name} right now."
    )


def open_browser_action(
    site_id: str,
    query: Optional[str] = None,
) -> WorkflowResult:
    """
    Deterministically open/search one trusted website in Chrome through the
    authenticated Windows Desktop Agent.

    Core owns site identity, query validation, and the exact expected trusted
    destination. The Desktop Agent owns Windows execution and independently
    reconstructs the same trusted destination from site_id + query.

    Arbitrary URLs never cross the Core -> Agent request boundary.
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

    expected_url = build_trusted_site_url(
        site_id=site_id,
        query=query_value,
    )

    if not expected_url:
        return WorkflowResult(
            success=False,
            status="unsupported_browser_action",
            error=(
                "That trusted browser destination could not be constructed."
            ),
            data={
                "site_id": site_id,
                "query": query_value,
            },
        )

    result = open_trusted_browser_site_via_agent(
        site_id=site_id,
        query=query_value,
    )

    if not isinstance(
        result,
        dict,
    ):
        return WorkflowResult(
            success=False,
            status="unexpected_agent_result",
            error=(
                "The Windows Desktop Agent returned an unexpected browser "
                "result."
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
        result_status = str(
            result.get(
                "status",
                "",
            )
            or ""
        ).strip()

        if result_status == "agent_unavailable":
            workflow_status = (
                "desktop_agent_unavailable"
            )

            error = _browser_agent_unavailable_error(
                site_id=site_id,
                query=query_value,
            )

        else:
            workflow_status = (
                result_status
                or "browser_action_failed"
            )

            error = (
                result.get(
                    "message"
                )
                or "I couldn't complete that Chrome action."
            )

        return WorkflowResult(
            success=False,
            status=workflow_status,
            error=error,
            data={
                "site_id": site_id,
                "query": query_value,
                "agent_result": result,
            },
        )

    actual_url = str(
        result.get(
            "url",
            "",
        )
        or ""
    ).strip()

    if actual_url != expected_url:
        return WorkflowResult(
            success=False,
            status="browser_destination_mismatch",
            error=(
                "The Windows Desktop Agent did not confirm the exact "
                "Core-approved browser destination, so I won't claim that "
                "the browser action succeeded."
            ),
            data={
                "site_id": site_id,
                "query": query_value,
                "expected_url": expected_url,
                "actual_url": actual_url,
                "agent_result": result,
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
                "The Windows Desktop Agent opened Chrome to the exact "
                "Core-approved "
                f"{display_name} destination."
            ),
            provenance="desktop_agent",
            confidence="verified",
            source_name="open_trusted_browser_site",
            data={
                "site_id": site_id,
                "query": query_value,
                "url": actual_url,
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
            "expected_url": expected_url,
            "agent_result": result,
        },
    )


def open_browser_search(
    query: str,
) -> WorkflowResult:
    """
    Backward-compatible Google-search wrapper for existing callers/tests.
    """

    return open_browser_action(
        site_id="google",
        query=query,
    )
