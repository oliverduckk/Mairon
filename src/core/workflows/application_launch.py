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
    "calculator": "Calculator",
    "notepad": "Notepad",
}


def launch_approved_application(
    app_name: str,
) -> WorkflowResult:
    """
    Deterministically launch one allowlisted desktop application.

    Core owns this workflow. Qwen does not decide whether Mairon has the
    capability, which tool to call, or whether the action succeeded.
    """

    app_name = str(
        app_name or ""
    ).strip().lower()

    if app_name not in APP_DISPLAY_NAMES:
        return WorkflowResult(
            success=False,
            status="unsupported_application",
            error=(
                "That application is not currently in Mairon's "
                "approved launch allowlist."
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
            status="launch_failed",
            error=(
                result.get(
                    "message"
                )
                or (
                    f"{APP_DISPLAY_NAMES[app_name]} "
                    "could not be opened."
                )
            ),
            data={
                "app_name": app_name,
                "tool_result": result,
            },
        )

    display_name = APP_DISPLAY_NAMES[
        app_name
    ]

    evidence = EvidenceBundle(
        authority="desktop",
        success=True,
    )

    evidence.add(
        Evidence(
            claim=(
                f"The local desktop tool successfully launched "
                f"{display_name}."
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
        answer_fact=(
            f"{display_name}'s open."
        ),
        evidence=evidence,
        data={
            "app_name": app_name,
            "tool_result": result,
        },
    )
