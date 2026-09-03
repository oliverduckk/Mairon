from core.evidence import (
    Evidence,
    EvidenceBundle,
)
from core.workflow_result import (
    WorkflowResult,
)
from tools.desktop_tools import (
    open_chrome_search,
)


def open_browser_search(
    query: str,
) -> WorkflowResult:
    """
    Deterministically open one explicit search query in Chrome.
    """

    value = str(
        query
        or ""
    ).strip()

    print(
        "[Tool] Mairon Core required: open_chrome_search"
    )

    result = open_chrome_search(
        value
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
                "query": value,
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
                or "browser_search_failed"
            ),
            error=(
                result.get(
                    "message"
                )
                or "I couldn't open that Chrome search."
            ),
            data={
                "query": value,
                "tool_result": result,
            },
        )

    evidence = EvidenceBundle(
        authority="desktop",
        success=True,
    )

    evidence.add(
        Evidence(
            claim=(
                "The local desktop layer opened Chrome with the exact "
                "URL-encoded search query supplied by Core."
            ),
            provenance="desktop_tool",
            confidence="verified",
            source_name="open_chrome_search",
            data={
                "query": value,
            },
        )
    )

    return WorkflowResult(
        success=True,
        status="browser_search_opened",
        answer_fact=(
            f'Searching Chrome for "{value}".'
        ),
        evidence=evidence,
        data={
            "query": value,
            "tool_result": result,
        },
    )
