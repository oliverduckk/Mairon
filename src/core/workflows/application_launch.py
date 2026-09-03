from core.desktop_catalog import (
    DESKTOP_TARGETS,
    desktop_display_name,
)
from core.evidence import (
    Evidence,
    EvidenceBundle,
)
from core.workflow_result import (
    WorkflowResult,
)
from tools.tool_registry import (
    execute_tool,
)


APP_DISPLAY_NAMES = {
    target_id: metadata["display_name"]
    for target_id, metadata in DESKTOP_TARGETS.items()
}


def _launch_answer(
    target_id: str,
) -> str:
    if target_id == "downloads":
        return "Downloads is open."

    if target_id == "mairon_project":
        return "Mairon's open in VS Code."

    return (
        f"{desktop_display_name(target_id)}'s open."
    )


def launch_approved_application(
    app_name: str,
) -> WorkflowResult:
    """
    Deterministically open one allowlisted desktop target.

    Core owns target identity. Qwen does not choose executable paths or
    construct commands.
    """

    app_name = str(
        app_name
        or ""
    ).strip().lower()

    if app_name not in APP_DISPLAY_NAMES:
        return WorkflowResult(
            success=False,
            status="unsupported_application",
            error=(
                "That desktop target is not currently in Mairon's "
                "approved allowlist."
            ),
            data={
                "app_name": app_name,
            },
        )

    result = execute_tool(
        "launch_application",
        {
            "app_name": app_name,
        },
    )

    if not isinstance(
        result,
        dict,
    ):
        return WorkflowResult(
            success=False,
            status="unexpected_tool_result",
            error=(
                "The desktop launch tool returned an unexpected result."
            ),
            data={
                "app_name": app_name,
                "raw_result": str(result),
            },
        )

    if result.get("success") is not True:
        return WorkflowResult(
            success=False,
            status="launch_failed",
            error=(
                result.get("message")
                or (
                    f"{desktop_display_name(app_name)} "
                    "could not be opened."
                )
            ),
            data={
                "app_name": app_name,
                "tool_result": result,
            },
        )

    answer_fact = _launch_answer(
        app_name
    )

    evidence = EvidenceBundle(
        authority="desktop",
        success=True,
    )

    evidence.add(
        Evidence(
            claim=(
                "The local desktop tool successfully requested opening "
                f"{desktop_display_name(app_name)}."
            ),
            provenance="desktop_tool",
            confidence="verified",
            source_name="launch_application",
            data={
                "app_name": app_name,
            },
        )
    )

    return WorkflowResult(
        success=True,
        status="launched",
        answer_fact=answer_fact,
        evidence=evidence,
        data={
            "app_name": app_name,
            "tool_result": result,
        },
    )
