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
from core.desktop_agent_client import (
    launch_application_via_agent,
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

    result = launch_application_via_agent(
        app_name=app_name,
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
        status = str(
            result.get(
                "status",
                "",
            )
            or ""
        ).strip()

        if status == "agent_unavailable":
            error = (
                "The Windows Desktop Agent isn't running, so I can't "
                f"open {desktop_display_name(app_name)} right now."
            )
            workflow_status = "desktop_agent_unavailable"

        else:
            error = (
                result.get(
                    "message"
                )
                or (
                    f"{desktop_display_name(app_name)} "
                    "could not be opened."
                )
            )
            workflow_status = "launch_failed"

        return WorkflowResult(
            success=False,
            status=workflow_status,
            error=error,
            data={
                "app_name": app_name,
                "agent_result": result,
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
                "The Windows Desktop Agent successfully requested opening "
                f"{desktop_display_name(app_name)}."
            ),
            provenance="desktop_agent",
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
            "agent_result": result,
        },
    )
