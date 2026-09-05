from core.desktop_agent_client import (
    close_application_via_agent,
    focus_application_via_agent,
)
from core.desktop_catalog import (
    desktop_display_name,
    get_desktop_target,
)
from core.evidence import (
    Evidence,
    EvidenceBundle,
)
from core.workflow_result import (
    WorkflowResult,
)


def _agent_unavailable_error(
    app_name: str,
    action: str,
) -> str:
    display_name = desktop_display_name(
        app_name
    )

    if action == "close":
        return (
            "The Windows Desktop Agent isn't running, so I can't "
            f"close {display_name} right now."
        )

    return (
        "The Windows Desktop Agent isn't running, so I can't "
        f"bring {display_name} to the front right now."
    )


def control_approved_application(
    app_name: str,
    action: str,
) -> WorkflowResult:
    """
    Perform one bounded Core-owned desktop window action through the
    authenticated Windows Desktop Agent.

    Core owns target identity, referent resolution, and action authority.
    The Desktop Agent owns the actual Windows execution.

    Close semantics still come from Core's allowlisted desktop catalogue.
    Most targets use graceful WM_CLOSE. Known tray-backed exceptions may use
    an approved full-process quit that terminates only their fixed allowlisted
    process image names.
    """

    app_name = str(
        app_name
        or ""
    ).strip().lower()

    action = str(
        action
        or ""
    ).strip().lower()

    target = get_desktop_target(
        app_name
    )

    if target is None:
        return WorkflowResult(
            success=False,
            status="unsupported_application",
            error="That desktop target is not approved.",
            data={
                "app_name": app_name,
                "action": action,
            },
        )

    if action == "close":
        result = close_application_via_agent(
            app_name
        )

    elif action == "focus":
        result = focus_application_via_agent(
            app_name
        )

    else:
        return WorkflowResult(
            success=False,
            status="unsupported_desktop_action",
            error="That desktop action is not supported.",
            data={
                "app_name": app_name,
                "action": action,
            },
        )

    if not isinstance(
        result,
        dict,
    ):
        return WorkflowResult(
            success=False,
            status="unexpected_agent_result",
            error=(
                "The Windows Desktop Agent returned an unexpected result."
            ),
            data={
                "app_name": app_name,
                "action": action,
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

            error = _agent_unavailable_error(
                app_name=app_name,
                action=action,
            )

        else:
            workflow_status = (
                result_status
                or f"{action}_failed"
            )

            error = (
                result.get(
                    "message"
                )
                or (
                    f"I couldn't {action} "
                    f"{desktop_display_name(app_name)}."
                )
            )

        return WorkflowResult(
            success=False,
            status=workflow_status,
            error=error,
            data={
                "app_name": app_name,
                "action": action,
                "agent_result": result,
            },
        )

    display_name = desktop_display_name(
        app_name
    )

    if action == "close":
        close_behavior = str(
            result.get(
                "close_behavior",
                "graceful_window",
            )
            or "graceful_window"
        ).strip().lower()

        if close_behavior == "quit_process":
            answer_fact = (
                f"{display_name}'s closed."
            )

        else:
            answer_fact = (
                f"{display_name} window's closed."
            )

    else:
        answer_fact = (
            f"{display_name}'s in front."
        )

    evidence = EvidenceBundle(
        authority="desktop",
        success=True,
    )

    evidence.add(
        Evidence(
            claim=(
                "The Windows Desktop Agent successfully performed "
                f"{action} for {display_name}."
            ),
            provenance="desktop_agent",
            confidence="verified",
            source_name=f"{action}_application",
            data={
                "app_name": app_name,
                "action": action,
            },
        )
    )

    return WorkflowResult(
        success=True,
        status=(
            "closed"
            if action == "close"
            else "focused"
        ),
        answer_fact=answer_fact,
        evidence=evidence,
        data={
            "app_name": app_name,
            "action": action,
            "agent_result": result,
        },
    )
