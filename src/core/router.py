from dataclasses import dataclass
from typing import Any

from core.action_manager import (
    execute_approved_action,
    format_action_result,
)


@dataclass
class RouteResult:
    status: str
    answer: str | None = None
    reason: str | None = None
    pending_prompt: str | None = None
    pending_action: dict | None = None
    local_state: Any = None
    cloud_state: Any = None


def parse_cloud_command(
    user_input
):
    if user_input.lower() == "/cloud":
        return True, ""

    if user_input.lower().startswith(
        "/cloud "
    ):
        return (
            True,
            user_input[7:].strip()
        )

    return (
        False,
        user_input
    )


def assess_cloud_complexity(
    user_input
):
    """
    Apply deterministic heuristics to identify requests
    likely to benefit from cloud processing.

    This function never contacts an AI provider.
    """

    text = user_input.lower()

    complexity_score = 0
    reasons = []

    if len(user_input) > 1500:
        complexity_score += 2

        reasons.append(
            "the request contains a large amount of input"
        )

    elif len(user_input) > 700:
        complexity_score += 1

    advanced_phrases = [
        "rigorous",
        "derive",
        "prove",
        "proof",
        "multi-stage",
        "deeply technical",
        "in significant detail",
        "exhaustive",
        "comprehensive analysis",
        "formal verification",
        "analyse this document",
        "analyze this document",
        "research paper",
        "compare and justify",
    ]

    phrase_matches = [
        phrase
        for phrase in advanced_phrases
        if phrase in text
    ]

    if len(phrase_matches) >= 3:
        complexity_score += 3

        reasons.append(
            "the request asks for several forms "
            "of advanced analysis"
        )

    elif len(phrase_matches) >= 1:
        complexity_score += 1

    demanding_domains = [
        "byzantine",
        "distributed system",
        "consensus protocol",
        "cryptography",
        "formal proof",
        "quantum algorithm",
        "compiler design",
        "type system",
        "theorem",
    ]

    domain_matches = [
        term
        for term in demanding_domains
        if term in text
    ]

    if len(domain_matches) >= 2:
        complexity_score += 2

        reasons.append(
            "the request involves a technically "
            "demanding domain"
        )

    if complexity_score >= 4:
        reason = (
            "; ".join(reasons)
            if reasons
            else "the request appears unusually complex"
        )

        return (
            True,
            reason
        )

    return (
        False,
        None
    )




def _local_model_label(
    local_ai,
):
    """Return the active local model name without hard-coding provider branding."""

    module = (
        (local_ai or {}).get(
            "module"
        )
        if isinstance(
            local_ai,
            dict,
        )
        else None
    )

    getter = getattr(
        module,
        "get_local_model_name",
        None,
    )

    if callable(
        getter
    ):
        try:
            value = str(
                getter()
                or ""
            ).strip()

            if value:
                return value

        except Exception:
            pass

    value = getattr(
        module,
        "MODEL",
        None,
    )

    return str(
        value
        or "local model"
    ).strip()


def route_message(
    local_ai,
    cloud_ai,
    user_input,
    instructions,
    local_state=None,
    cloud_state=None
):
    use_cloud, clean_input = (
        parse_cloud_command(
            user_input
        )
    )

    # --------------------------------------------------
    # Explicit cloud request
    # --------------------------------------------------

    if use_cloud:

        if not clean_input:
            return RouteResult(
                status="answered",
                answer=(
                    "Put a prompt after /cloud."
                ),
                local_state=local_state,
                cloud_state=cloud_state
            )

        if cloud_ai is None:
            return RouteResult(
                status="answered",
                answer=(
                    "Cloud processing is not configured."
                ),
                local_state=local_state,
                cloud_state=cloud_state
            )

        print(
            "[AI] Using cloud: GPT-5.6 Luna"
        )

        answer, new_cloud_state, _ = (
            cloud_ai["module"].get_response(
                cloud_ai["client"],
                clean_input,
                instructions,
                cloud_state
            )
        )

        return RouteResult(
            status="answered",
            answer=answer,
            local_state=local_state,
            cloud_state=new_cloud_state
        )

    # --------------------------------------------------
    # Deterministic complexity recommendation
    # --------------------------------------------------

    recommend_cloud, recommendation_reason = (
        assess_cloud_complexity(
            clean_input
        )
    )

    if (
        recommend_cloud
        and cloud_ai is not None
    ):
        return RouteResult(
            status="cloud_approval_required",
            reason=recommendation_reason,
            pending_prompt=clean_input,
            local_state=local_state,
            cloud_state=cloud_state
        )

    # --------------------------------------------------
    # Normal local processing
    # --------------------------------------------------

    print(
        "[AI] Using local: "
        + _local_model_label(
            local_ai
        )
    )

    (
        answer,
        new_local_state,
        escalation_reason,
        pending_action,
    ) = local_ai["module"].get_response(
        local_ai["client"],
        clean_input,
        instructions,
        local_state,
        allow_cloud_escalation=True
    )

    if pending_action:
        return RouteResult(
            status="action_approval_required",
            pending_prompt=clean_input,
            pending_action=pending_action,
            local_state=new_local_state,
            cloud_state=cloud_state
        )

    if escalation_reason:
        return RouteResult(
            status="cloud_approval_required",
            reason=escalation_reason,
            pending_prompt=clean_input,
            local_state=new_local_state,
            cloud_state=cloud_state
        )

    return RouteResult(
        status="answered",
        answer=answer,
        local_state=new_local_state,
        cloud_state=cloud_state
    )


def approve_cloud_escalation(
    cloud_ai,
    prompt,
    instructions,
    local_state=None,
    cloud_state=None
):
    if cloud_ai is None:
        return RouteResult(
            status="answered",
            answer=(
                "Cloud processing is not configured."
            ),
            local_state=local_state,
            cloud_state=cloud_state
        )

    print(
        "[Router] Cloud processing approved."
    )

    print(
        "[AI] Using cloud: GPT-5.6 Luna"
    )

    answer, new_cloud_state, _ = (
        cloud_ai["module"].get_response(
            cloud_ai["client"],
            prompt,
            instructions,
            cloud_state
        )
    )

    return RouteResult(
        status="answered",
        answer=answer,
        local_state=local_state,
        cloud_state=new_cloud_state
    )


def decline_cloud_escalation(
    local_ai,
    prompt,
    instructions,
    local_state=None,
    cloud_state=None
):
    print(
        "[Router] Cloud processing declined. "
        "Continuing locally."
    )

    print(
        "[AI] Using local: "
        + _local_model_label(
            local_ai
        )
    )

    (
        answer,
        new_local_state,
        _,
        pending_action,
    ) = local_ai["module"].get_response(
        local_ai["client"],
        prompt,
        instructions,
        local_state,
        allow_cloud_escalation=False
    )

    if pending_action:
        return RouteResult(
            status="action_approval_required",
            pending_prompt=prompt,
            pending_action=pending_action,
            local_state=new_local_state,
            cloud_state=cloud_state
        )

    return RouteResult(
        status="answered",
        answer=answer,
        local_state=new_local_state,
        cloud_state=cloud_state
    )


def approve_pending_action(
    result
):
    """
    Execute an action only after explicit user approval.
    """

    action = result.pending_action

    action_result = (
        execute_approved_action(
            action
        )
    )

    answer = format_action_result(
        action,
        action_result
    )

    return RouteResult(
        status="answered",
        answer=answer,
        local_state=result.local_state,
        cloud_state=result.cloud_state
    )


def decline_pending_action(
    result
):
    """
    Reject the pending action without changing anything.
    """

    action = (
        result.pending_action
        or {}
    )

    action_type = action.get(
        "type"
    )

    if action_type == "create_calendar_event":
        answer = (
            "Calendar event creation cancelled. "
            "Nothing was changed."
        )

    else:
        answer = (
            "Action cancelled. Nothing was changed."
        )

    return RouteResult(
        status="answered",
        answer=answer,
        local_state=result.local_state,
        cloud_state=result.cloud_state
    )