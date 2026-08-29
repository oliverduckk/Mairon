from dataclasses import dataclass
from typing import Any


@dataclass
class RouteResult:
    status: str

    answer: str | None = None
    reason: str | None = None
    pending_prompt: str | None = None

    local_state: Any = None
    cloud_state: Any = None


def parse_cloud_command(user_input):
    if user_input.lower() == "/cloud":
        return True, ""

    if user_input.lower().startswith("/cloud "):
        return True, user_input[7:].strip()

    return False, user_input

def assess_cloud_complexity(user_input):
    """
    Apply simple deterministic heuristics to identify requests that are
    likely to benefit from a more capable cloud model.

    This does not contact any AI provider.
    """

    text = user_input.lower()

    complexity_score = 0
    reasons = []

    # Large prompts are more likely to contain demanding workloads.
    if len(user_input) > 1500:
        complexity_score += 2
        reasons.append("the request contains a large amount of input")

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
        reasons.append("the request asks for several forms of advanced analysis")

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
        reasons.append("the request involves a technically demanding domain")

    if complexity_score >= 4:
        reason = (
            "; ".join(reasons)
            if reasons
            else "the request appears unusually complex"
        )

        return True, reason

    return False, None

def route_message(
    user_input,
    local_ai,
    cloud_ai,
    instructions,
    local_state,
    cloud_state
):
    """
    Route a normal user message.

    Local processing is always the default.

    The user may explicitly use /cloud, or the local model may request
    permission for cloud escalation.
    """

    use_cloud, clean_input = parse_cloud_command(user_input)

    # --------------------------------------------------
    # Explicit /cloud command
    # --------------------------------------------------

    if use_cloud:
        if not clean_input:
            return RouteResult(
                status="answered",
                answer="You invoked the cloud and then gave me nothing to do. Impressive.",
                local_state=local_state,
                cloud_state=cloud_state
            )

        if cloud_ai is None:
            return RouteResult(
                status="answered",
                answer="Cloud processing is currently unavailable.",
                local_state=local_state,
                cloud_state=cloud_state
            )

        print("[AI] Using cloud: GPT-5.6 Luna")

        answer, cloud_state, _ = cloud_ai["module"].get_response(
            cloud_ai["client"],
            clean_input,
            instructions,
            cloud_state,
            allow_cloud_escalation=False
        )

        return RouteResult(
            status="answered",
            answer=answer,
            local_state=local_state,
            cloud_state=cloud_state
        )
    
    # --------------------------------------------------
    # Deterministic complexity assessment
    # --------------------------------------------------

    recommend_cloud, recommendation_reason = assess_cloud_complexity(
        clean_input
    )

    if recommend_cloud and cloud_ai is not None:
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

    print("[AI] Using local: Qwen3 14B")

    answer, new_local_state, escalation_reason = local_ai["module"].get_response(
        local_ai["client"],
        clean_input,
        instructions,
        local_state,
        allow_cloud_escalation=True
    )

    # The local AI has requested additional authority.
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
    prompt,
    cloud_ai,
    instructions,
    local_state,
    cloud_state
):
    """
    Execute a previously requested cloud escalation after user approval.
    """

    if cloud_ai is None:
        return RouteResult(
            status="answered",
            answer="Cloud processing is currently unavailable.",
            local_state=local_state,
            cloud_state=cloud_state
        )

    print("[AI] Cloud escalation approved.")
    print("[AI] Using cloud: GPT-5.6 Luna")

    answer, cloud_state, _ = cloud_ai["module"].get_response(
        cloud_ai["client"],
        prompt,
        instructions,
        cloud_state,
        allow_cloud_escalation=False
    )

    return RouteResult(
        status="answered",
        answer=answer,
        local_state=local_state,
        cloud_state=cloud_state
    )


def decline_cloud_escalation(
    prompt,
    local_ai,
    instructions,
    local_state,
    cloud_state
):
    """
    Continue locally after the user refuses cloud processing.

    Cloud escalation is disabled for this retry so the local model cannot
    immediately request it again.
    """

    print("[AI] Cloud escalation declined.")
    print("[AI] Continuing locally: Qwen3 14B")

    answer, local_state, _ = local_ai["module"].get_response(
        local_ai["client"],
        prompt,
        instructions,
        local_state,
        allow_cloud_escalation=False
    )

    return RouteResult(
        status="answered",
        answer=answer,
        local_state=local_state,
        cloud_state=cloud_state
    )