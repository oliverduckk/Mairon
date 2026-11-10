from dataclasses import dataclass
from typing import Any

from core.provider_state import (
    bounded_local_history, eligible_cloud_continuation, make_cloud_continuation,
    adapt_cloud_provider_reply, adapt_local_provider_reply,
    requires_prior_cloud_context,
)

from core.authority_handoff import PreparedAuthority, CoreAuthorityUnavailable
from tools.tool_admission import provider_turn
from core.action_approval import issue_calendar_ticket
from core.cloud_export import (
    CloudExportDenied, issue_cloud_export_grant, admit_cloud_initial,
)

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
    approval_ticket: Any = None
    local_state: Any = None
    cloud_state: Any = None
    core_authority: PreparedAuthority | None = None
    provider_kind: str | None = None


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


def cloud_authority_supported(core_authority: PreparedAuthority) -> bool:
    try:
        core_authority.require_cloud()
        return True
    except CoreAuthorityUnavailable:
        return False


def _cloud_model_id(cloud_ai) -> str:
    module = cloud_ai.get("module") if isinstance(cloud_ai, dict) else None
    return str(getattr(module, "MODEL", "gpt-5.6-luna"))


def _qualified_cloud_state(cloud_ai, state, owner_id):
    return eligible_cloud_continuation(
        state, owner_id=owner_id, model_id=_cloud_model_id(cloud_ai),
        backend_client=cloud_ai.get("client"),
    )


def _state_after_cloud(cloud_ai, response_id, owner_id, predecessor):
    return make_cloud_continuation(
        response_id, owner_id=owner_id,
        model_id=_cloud_model_id(cloud_ai), predecessor=predecessor,
        backend_client=cloud_ai.get("client"),
    )


def route_message(
    local_ai,
    cloud_ai,
    user_input,
    instructions,
    local_state=None,
    cloud_state=None,
    *,
    core_authority: PreparedAuthority,
    state_owner_id: str | None = None,
):
    if not isinstance(core_authority, PreparedAuthority):
        raise CoreAuthorityUnavailable("Trusted Core authority is unavailable.")
    core_authority.require_local()
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

        core_authority.require_cloud()

        print(
            "[AI] Using cloud: GPT-5.6 Luna"
        )

        # S3: explicit /cloud grants only this prompt.  Never send the full
        # application instruction bundle, reconstructed chat, or old cloud
        # state as an unclassified history/continuation handle.
        prior = _qualified_cloud_state(cloud_ai, cloud_state, state_owner_id)
        if prior is None and requires_prior_cloud_context(clean_input):
            return RouteResult(
                status="answered",
                answer=(
                    "I can't safely resume earlier context in cloud processing. "
                    "Please restate the relevant details after /cloud."
                ),
                local_state=local_state, cloud_state=None,
                core_authority=core_authority,
            )
        grant = issue_cloud_export_grant(
            core_authority, clean_input, purpose="explicit_cloud_request",
            previous_state=prior, owner_id=state_owner_id,
            model_id=_cloud_model_id(cloud_ai),
            backend_client=cloud_ai.get("client"),
        )
        initial = admit_cloud_initial(grant, clean_input, previous_state=prior)
        try:
            with provider_turn(core_authority):
                raw_cloud_result = cloud_ai["module"].get_response(
                    cloud_ai["client"],
                    initial.payload["input"],
                    initial.payload["instructions"],
                    prior,
                    core_answer_contract=core_authority.runtime,
                    cloud_export=grant,
                )
            answer, new_cloud_state = adapt_cloud_provider_reply(raw_cloud_result)
        except Exception:
            # SDK exception text can echo user input or upstream payloads.
            raise CloudExportDenied("Cloud processing failed without an eligible response.") from None

        return RouteResult(
            status="answered",
            answer=answer,
            local_state=local_state,
            cloud_state=_state_after_cloud(
                cloud_ai, new_cloud_state, state_owner_id, prior,
            ),
            core_authority=core_authority,
            provider_kind="cloud",
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
        and cloud_authority_supported(core_authority)
    ):
        return RouteResult(
            status="cloud_approval_required",
            reason=recommendation_reason,
            pending_prompt=clean_input,
            local_state=local_state,
            cloud_state=cloud_state,
            core_authority=core_authority,
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

    with provider_turn(core_authority):
        raw_local_result = local_ai["module"].get_response(
            local_ai["client"],
            clean_input,
            instructions,
            bounded_local_history(local_state),
            allow_cloud_escalation=True,
            core_answer_contract=core_authority.runtime,
        )
    answer, new_local_state, escalation_reason, pending_action = (
        adapt_local_provider_reply(raw_local_result)
    )

    if pending_action:
        ticket = issue_calendar_ticket(pending_action, core_authority)
        if ticket is None:
            return RouteResult(
                status="answered",
                answer="I couldn't safely prepare that calendar approval.",
                local_state=bounded_local_history(new_local_state),
                cloud_state=None,
                core_authority=core_authority,
            )
        return RouteResult(
            approval_ticket=ticket,
            status="action_approval_required",
            pending_prompt=clean_input,
            pending_action=pending_action,
            local_state=bounded_local_history(new_local_state),
            cloud_state=None,
            core_authority=core_authority,
        )

    if escalation_reason and not cloud_authority_supported(core_authority):
        return RouteResult(
            status="answered",
            answer=(answer or "The cloud provider cannot satisfy this turn's required Core obligations."),
            local_state=bounded_local_history(new_local_state),
            cloud_state=None,
            core_authority=core_authority,
        )

    if escalation_reason:
        return RouteResult(
            status="cloud_approval_required",
            reason=escalation_reason,
            pending_prompt=clean_input,
            local_state=bounded_local_history(new_local_state),
            cloud_state=None,
            core_authority=core_authority,
        )

    return RouteResult(
        status="answered",
        answer=answer,
        local_state=bounded_local_history(new_local_state),
        cloud_state=None,
        core_authority=core_authority,
    )


def approve_cloud_escalation(
    cloud_ai,
    prompt,
    instructions,
    local_state=None,
    cloud_state=None,
    *,
    core_authority: PreparedAuthority,
    state_owner_id: str | None = None,
):
    if not isinstance(core_authority, PreparedAuthority):
        raise CoreAuthorityUnavailable("Trusted Core authority is unavailable.")
    core_authority.require_cloud()
    if cloud_ai is None:
        return RouteResult(
            status="answered",
            answer=(
                "Cloud processing is not configured."
            ),
            local_state=local_state,
            cloud_state=cloud_state,
            core_authority=core_authority,
        )

    print(
        "[Router] Cloud processing approved."
    )

    print(
        "[AI] Using cloud: GPT-5.6 Luna"
    )

    # Approval grants export of the pending prompt only, not its surrounding
    # private instructions, historical context, local state or saved handle.
    prior = _qualified_cloud_state(cloud_ai, cloud_state, state_owner_id)
    if prior is None and requires_prior_cloud_context(prompt):
        return RouteResult(
            status="answered",
            answer=(
                "I can't safely resume earlier context in cloud processing. "
                "Please restate the relevant details after /cloud."
            ),
            local_state=local_state, cloud_state=None,
            core_authority=core_authority,
        )
    grant = issue_cloud_export_grant(
        core_authority, prompt, purpose="approved_cloud_escalation",
        previous_state=prior, owner_id=state_owner_id,
        model_id=_cloud_model_id(cloud_ai),
        backend_client=cloud_ai.get("client"),
    )
    initial = admit_cloud_initial(grant, prompt, previous_state=prior)
    try:
        with provider_turn(core_authority):
            raw_cloud_result = cloud_ai["module"].get_response(
                cloud_ai["client"],
                initial.payload["input"],
                initial.payload["instructions"],
                prior,
                core_answer_contract=core_authority.runtime,
                cloud_export=grant,
            )
        answer, new_cloud_state = adapt_cloud_provider_reply(raw_cloud_result)
    except Exception:
        # The cloud SDK/adapter may otherwise return sensitive request text in
        # a raw exception, subsequently shown in the application diagnostics.
        raise CloudExportDenied("Cloud processing failed without an eligible response.") from None

    return RouteResult(
        status="answered",
        answer=answer,
        local_state=local_state,
        cloud_state=_state_after_cloud(
            cloud_ai, new_cloud_state, state_owner_id, prior,
        ),
        core_authority=core_authority,
        provider_kind="cloud",
    )


def decline_cloud_escalation(
    local_ai,
    prompt,
    instructions,
    local_state=None,
    cloud_state=None,
    *,
    core_authority: PreparedAuthority,
    state_owner_id: str | None = None,
):
    if not isinstance(core_authority, PreparedAuthority):
        raise CoreAuthorityUnavailable("Trusted Core authority is unavailable.")
    core_authority.require_local()
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

    with provider_turn(core_authority):
        raw_local_result = local_ai["module"].get_response(
            local_ai["client"],
            prompt,
            instructions,
            bounded_local_history(local_state),
            allow_cloud_escalation=False,
            core_answer_contract=core_authority.runtime,
        )
    answer, new_local_state, _, pending_action = adapt_local_provider_reply(raw_local_result)

    if pending_action:
        ticket = issue_calendar_ticket(pending_action, core_authority)
        if ticket is None:
            return RouteResult(
                status="answered",
                answer="I couldn't safely prepare that calendar approval.",
                local_state=bounded_local_history(new_local_state),
                cloud_state=None,
                core_authority=core_authority,
            )
        return RouteResult(
            approval_ticket=ticket,
            status="action_approval_required",
            pending_prompt=prompt,
            pending_action=pending_action,
            local_state=bounded_local_history(new_local_state),
            cloud_state=None,
            core_authority=core_authority,
        )

    return RouteResult(
        status="answered",
        answer=answer,
        local_state=bounded_local_history(new_local_state),
        cloud_state=None,
        core_authority=core_authority,
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
            action, approval_ticket=result.approval_ticket,
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

    if result.approval_ticket is not None:
        result.approval_ticket.revoke()

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