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
from tools.desktop_tools import (
    close_application,
    focus_application,
)


def control_approved_application(
    app_name: str,
    action: str,
) -> WorkflowResult:
    """
    Perform one bounded Core-owned desktop window action.

    Close semantics come from Core's allowlisted desktop catalogue.

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
        result = close_application(
            app_name
        )
    elif action == "focus":
        result = focus_application(
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
            status="unexpected_tool_result",
            error=(
                "The desktop control layer returned an unexpected result."
            ),
            data={
                "app_name": app_name,
                "action": action,
                "raw_result": str(result),
            },
        )

    if result.get("success") is not True:
        return WorkflowResult(
            success=False,
            status=(
                result.get("status")
                or f"{action}_failed"
            ),
            error=(
                result.get("message")
                or (
                    f"I couldn't {action} "
                    f"{desktop_display_name(app_name)}."
                )
            ),
            data={
                "app_name": app_name,
                "action": action,
                "tool_result": result,
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
                "The local desktop control layer successfully performed "
                f"{action} for {display_name}."
            ),
            provenance="desktop_tool",
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
            "tool_result": result,
        },
    )
