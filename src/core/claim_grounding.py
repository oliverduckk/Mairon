import json
import re
from typing import Any, Dict, List, Optional


def _extract_json_object(
    text: Any,
) -> Optional[Dict[str, Any]]:
    value = str(
        text or ""
    ).strip()

    if not value:
        return None

    try:
        parsed = json.loads(
            value
        )

        if isinstance(
            parsed,
            dict,
        ):
            return parsed

    except Exception:
        pass

    start = value.find(
        "{"
    )

    end = value.rfind(
        "}"
    )

    if (
        start == -1
        or end == -1
        or end <= start
    ):
        return None

    try:
        parsed = json.loads(
            value[
                start:end + 1
            ]
        )

    except Exception:
        return None

    if not isinstance(
        parsed,
        dict,
    ):
        return None

    return parsed


def _contract_value(
    core_answer_contract: Optional[str],
    field_name: str,
) -> Optional[str]:
    if not core_answer_contract:
        return None

    prefix = (
        str(
            field_name
        ).strip()
        + ":"
    ).lower()

    for raw_line in str(
        core_answer_contract
    ).splitlines():
        line = raw_line.strip()

        comparable = line.lstrip(
            "- "
        ).strip()

        if comparable.lower().startswith(
            prefix
        ):
            return comparable.split(
                ":",
                1,
            )[
                1
            ].strip()

    return None


def contract_forbids_new_factual_claims(
    core_answer_contract: Optional[str],
) -> bool:
    value = _contract_value(
        core_answer_contract,
        "New unsupported factual claims allowed",
    )

    return (
        str(
            value or ""
        ).strip().lower()
        == "false"
    )


def contract_intent(
    core_answer_contract: Optional[str],
) -> Optional[str]:
    value = _contract_value(
        core_answer_contract,
        "Intent",
    )

    if not value:
        return None

    return value.strip().lower()


def _message_role_and_content(
    message: Any,
):
    if isinstance(
        message,
        dict,
    ):
        return (
            message.get(
                "role"
            ),
            str(
                message.get(
                    "content"
                )
                or ""
            ),
        )

    return (
        getattr(
            message,
            "role",
            None,
        ),
        str(
            getattr(
                message,
                "content",
                "",
            )
            or ""
        ),
    )


def build_recent_user_grounding_context(
    conversation,
    max_user_messages: int = 4,
) -> Optional[str]:
    """
    Build a compact grounding packet from recent USER messages only.

    Prior assistant messages are deliberately excluded. A previous Mairon
    response proves what Mairon said, not that the factual content was true.
    This prevents an earlier hallucination from becoming evidence for a new
    hallucination.
    """

    collected = []

    for message in reversed(
        list(
            conversation or []
        )
    ):
        role, content = (
            _message_role_and_content(
                message
            )
        )

        if role != "user":
            continue

        content = re.sub(
            r"\s+",
            " ",
            content,
        ).strip()

        if not content:
            continue

        collected.append(
            content
        )

        if len(
            collected
        ) >= max(
            1,
            int(
                max_user_messages
            ),
        ):
            break

    if not collected:
        return None

    collected.reverse()

    lines = [
        "RECENT USER-PROVIDED CONTEXT:",
    ]

    for item in collected:
        lines.append(
            "- "
            + item
        )

    return "\n".join(
        lines
    )


def _combined_allowed_grounding_text(
    user_input: str,
    conversation,
    core_answer_contract: Optional[str],
) -> str:
    pieces = [
        str(
            user_input or ""
        ),
        str(
            core_answer_contract or ""
        ),
    ]

    recent_user_context = (
        build_recent_user_grounding_context(
            conversation
        )
    )

    if recent_user_context:
        pieces.append(
            recent_user_context
        )

    return "\n".join(
        pieces
    )


def _normalise_for_grounding(
    text: str,
) -> str:
    value = str(
        text or ""
    ).lower()

    value = re.sub(
        r"[’‘]",
        "'",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value


def _novel_multiword_named_entities(
    draft: str,
    grounding_text: str,
) -> List[str]:
    """
    Catch obvious introduced proper-noun phrases such as "Great Wall"
    when they never appeared anywhere in the allowed grounding packet.

    This is intentionally conservative: only 2-4 word capitalised spans
    are checked, so ordinary sentence-initial words are ignored.
    """

    candidates = re.findall(
        r"\b([A-Z][A-Za-z0-9'-]+"
        r"(?:\s+[A-Z][A-Za-z0-9'-]+){1,3})\b",
        str(
            draft or ""
        ),
    )

    grounding_lower = str(
        grounding_text or ""
    ).lower()

    ignored = {
        "Fair Enough",
        "Good Lord",
        "Jesus Christ",
        "Core Answer Contract",
    }

    leading_determiners = {
        "the",
        "a",
        "an",
        "this",
        "that",
        "these",
        "those",
        "my",
        "your",
        "our",
        "their",
    }

    novel = []

    for candidate in candidates:
        candidate = candidate.strip()

        if (
            not candidate
            or candidate in ignored
        ):
            continue

        candidate_lower = candidate.lower()

        if candidate_lower in grounding_lower:
            continue

        # Sentence-initial determiners can make ordinary grounded entities
        # look like multi-word proper nouns:
        #
        #   "The XT6s arrived."
        #
        # The regex sees "The XT6s". If the informative remainder ("XT6s")
        # is already present in the grounding packet, this is NOT a novel
        # named entity.
        words = candidate.split()

        if (
            len(words) >= 2
            and words[0].lower()
            in leading_determiners
        ):
            remainder = " ".join(
                words[1:]
            ).strip()

            if (
                remainder
                and remainder.lower()
                in grounding_lower
            ):
                continue

        if candidate not in novel:
            novel.append(
                candidate
            )

    return novel


def _unsupported_current_location_claims(
    draft: str,
    grounding_text: str,
) -> List[str]:
    """
    Catch one especially dangerous relation error:
    treating a destination/purpose as a current location.

    Example:
        Oliver: "I bought XT6s for China."
        Draft:  "They're in China."

    Topic overlap is not entailment.
    """

    draft_text = str(
        draft or ""
    )

    grounding_norm = _normalise_for_grounding(
        grounding_text
    )

    patterns = [
        r"\b(?:is|are|am|be|being|currently|now|they're|you're|we're|it's)"
        r"(?:\s+\w+){0,5}\s+in\s+([A-Z][A-Za-z]+"
        r"(?:\s+[A-Z][A-Za-z]+){0,2})\b",
        r"\b(?:sitting|located|based|staying)\s+in\s+"
        r"([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})\b",
    ]

    unsupported = []

    for pattern in patterns:
        for match in re.finditer(
            pattern,
            draft_text,
        ):
            location = (
                match.group(
                    1
                )
                or ""
            ).strip()

            if not location:
                continue

            location_norm = (
                location.lower()
            )

            directly_grounded = any(
                phrase
                in grounding_norm
                for phrase in (
                    f"in {location_norm}",
                    f"at {location_norm}",
                    f"currently in {location_norm}",
                    f"currently at {location_norm}",
                )
            )

            if directly_grounded:
                continue

            description = (
                f"current-location claim involving '{location}' "
                "is not directly supported"
            )

            if description not in unsupported:
                unsupported.append(
                    description
                )

    return unsupported


def find_deterministic_grounding_violations(
    user_input: str,
    draft: str,
    core_answer_contract: Optional[str],
    conversation=None,
) -> List[str]:
    """
    Cheap high-confidence checks before the semantic verifier.

    These do not attempt to understand every factual claim. They target
    failure classes where deterministic evidence is stronger than asking
    the same LLM to judge itself.
    """

    grounding_text = (
        _combined_allowed_grounding_text(
            user_input=user_input,
            conversation=conversation,
            core_answer_contract=(
                core_answer_contract
            ),
        )
    )

    violations = []

    for entity in (
        _novel_multiword_named_entities(
            draft=draft,
            grounding_text=grounding_text,
        )
    ):
        violations.append(
            (
                "unsupported Core-grounded claim: "
                f"introduced named entity '{entity}' "
                "that is absent from the allowed grounding packet"
            )
        )

    for description in (
        _unsupported_current_location_claims(
            draft=draft,
            grounding_text=grounding_text,
        )
    ):
        violations.append(
            (
                "unsupported Core-grounded claim: "
                + description
            )
        )

    return violations


def should_verify_core_grounding(
    core_answer_contract: Optional[str],
) -> bool:
    """
    Decide whether a generated direct-conversation draft needs semantic
    grounding verification.

    Simple acknowledgements are already constrained by deterministic
    structural rules and do not need an extra model call.

    Declarative shares are the first high-value target because Qwen tends
    to embellish them with product/location/media facts that Oliver did not
    actually supply.
    """

    if not contract_forbids_new_factual_claims(
        core_answer_contract
    ):
        return False

    intent = contract_intent(
        core_answer_contract
    )

    if intent in {
        "acknowledge",
    }:
        return False

    return True


def verify_core_grounded_draft(
    client,
    model: str,
    user_input: str,
    draft: str,
    core_answer_contract: Optional[str],
    conversation=None,
) -> List[str]:
    """
    Isolated semantic verifier for Core-restricted conversational turns.

    Allowed factual grounding:
    - Oliver's CURRENT message;
    - recent prior USER messages;
    - the current Core Answer Contract, including resolved referents,
      required claims, and verified evidence.

    Explicitly NOT authoritative:
    - model training memory;
    - prior assistant/Mairon claims;
    - plausibility;
    - stereotypical assumptions.

    Subjective banter is allowed when it is clearly non-literal and does not
    smuggle in a factual premise.
    """

    if not should_verify_core_grounding(
        core_answer_contract
    ):
        return []

    deterministic_violations = (
        find_deterministic_grounding_violations(
            user_input=user_input,
            draft=draft,
            core_answer_contract=(
                core_answer_contract
            ),
            conversation=conversation,
        )
    )

    if deterministic_violations:
        return deterministic_violations

    recent_user_context = (
        build_recent_user_grounding_context(
            conversation
        )
    )

    system_text = (
        "You are Mairon Core's INTERNAL claim-grounding verifier. "
        "You are not speaking to Oliver.\n\n"
        "Your only job is to decide whether factual assertions in a proposed "
        "Mairon draft are supported by the allowed grounding packet.\n\n"
        "ALLOWED FACTUAL GROUNDING:\n"
        "1. Oliver's current message.\n"
        "2. Recent PRIOR USER messages supplied below.\n"
        "3. The current CORE ANSWER CONTRACT, including resolved references, "
        "required claims, and verified evidence.\n\n"
        "NOT ALLOWED AS FACTUAL GROUNDING:\n"
        "- your own training memory;\n"
        "- common knowledge that is absent from the packet;\n"
        "- prior Mairon/assistant statements;\n"
        "- likely assumptions;\n"
        "- stereotypes;\n"
        "- facts that merely sound plausible.\n\n"
        "IMPORTANT — FACTS VS BANTER:\n"
        "- Grounding applies to statements a reasonable reader could interpret as "
        "literal claims about reality.\n"
        "- Clearly absurd, impossible, anthropomorphic, sarcastic, teasing, or "
        "hyperbolic jokes are NOT factual claims and do NOT require evidence.\n"
        "- Do NOT reject a joke merely because its literal wording is false. The "
        "whole point of obvious non-literal humour is that it is not asserting the "
        "literal proposition.\n"
        "- Examples that are NON-LITERAL and should be ALLOWED: "
        "'The shoes will need their own passport', "
        "'Hope they're not plotting a mutiny', "
        "'You'll end up living in those things', "
        "'They've claimed permanent residency on your feet', "
        "'Your socks should start drafting their obituary'.\n"
        "- A joke is NOT automatically exempt merely because it is phrased casually. "
        "If it smuggles in a plausible real-world premise, that premise still needs "
        "grounding.\n"
        "- Examples that remain FACTUAL and must be grounded: "
        "'XT6s are waterproof', "
        "'XT6s last 500 km', "
        "'they are currently in China', "
        "'you will visit the Great Wall', "
        "'they were made in China'.\n"
        "- When uncertain, ask: would a normal reader reasonably believe Mairon is "
        "telling Oliver something true about the product, location, itinerary, "
        "history, media canon, technical behaviour, or an external event? If yes, "
        "treat it as factual. If it is obviously impossible or ridiculous on its "
        "face, treat it as non-literal banter.\n"
        "- A product property, location assumption, itinerary assumption, "
        "technical specification, historical claim, media/canon claim, or "
        "claim about what happened outside the supplied packet IS factual.\n"
        "- Paraphrasing or logically trivial restatement of Oliver's supplied "
        "facts is allowed.\n"
        "- ENTAILMENT matters. Mere topic/word overlap is NOT support.\n"
        "- 'for China' does NOT support 'currently in China'.\n"
        "- 'arrived today' does NOT identify the place it arrived unless Oliver says where.\n"
        "- 'for a China trip' does NOT support a specific attraction or itinerary such as "
        "the Great Wall.\n"
        "- A product name does NOT support durability, cushioning, waterproofing, materials, "
        "performance, or other product properties unless those properties appear in the packet.\n"
        "- If a claim is true in the real world but absent from the allowed "
        "packet, it is STILL unsupported for this turn.\n"
        "- Never rescue a claim using your own knowledge.\n\n"
        "First classify each meaningful proposition as either LITERAL_FACT or "
        "CLEARLY_NON_LITERAL_BANTER. Do not perform factual grounding on "
        "CLEARLY_NON_LITERAL_BANTER. For EACH LITERAL_FACT, require a directly "
        "supporting quote or a trivial logical restatement of a supplied quote. "
        "Relation changes such as for->in, planned->completed, may->did, or "
        "future->current are unsupported.\n\n"
        "Return JSON ONLY:\n"
        "{\n"
        '  "supported": true,\n'
        '  "unsupported_claims": [],\n'
        '  "claim_checks": [\n'
        '    {"claim": "...", "supported": true, "evidence_quote": "...", "reason": "..."}\n'
        "  ]\n"
        "}\n\n"
        "If any factual assertion is unsupported, set supported=false and "
        "list short descriptions of those claims."
    )

    messages = [
        {
            "role": "system",
            "content": system_text,
        },
        {
            "role": "system",
            "content": (
                "CORE ANSWER CONTRACT:\n"
                + str(
                    core_answer_contract
                    or ""
                )
            ),
        },
    ]

    if recent_user_context:
        messages.append({
            "role": "system",
            "content": recent_user_context,
        })

    messages.extend([
        {
            "role": "user",
            "content": (
                "OLIVER'S CURRENT MESSAGE:\n"
                + str(
                    user_input
                )
            ),
        },
        {
            "role": "user",
            "content": (
                "PROPOSED MAIRON DRAFT:\n"
                + str(
                    draft
                )
            ),
        },
    ])

    result = client.chat(
        model=model,
        messages=messages,
        options={
            "temperature": 0,
        },
    )

    parsed = _extract_json_object(
        result.message.content
    )

    if not parsed:
        return [
            "Core claim-grounding verifier could not validate the draft"
        ]

    if parsed.get(
        "supported"
    ) is True:
        return []

    claims = parsed.get(
        "unsupported_claims"
    )

    if not isinstance(
        claims,
        list,
    ):
        claims = []

    cleaned = []

    for claim in claims[
        :8
    ]:
        value = re.sub(
            r"\s+",
            " ",
            str(
                claim
            ).strip(),
        )

        if value:
            cleaned.append(
                value
            )

    if cleaned:
        return [
            (
                "unsupported Core-grounded claim: "
                + claim
            )
            for claim in cleaned
        ]

    return [
        "Core-restricted response contained unsupported factual claims"
    ]


def build_core_grounding_retry_instruction(
    violations: List[str],
) -> Optional[str]:
    relevant = [
        violation
        for violation in violations
        if (
            "unsupported Core-grounded claim"
            in violation
            or "claim-grounding verifier"
            in violation
            or "Core-restricted response contained unsupported"
            in violation
        )
    ]

    if not relevant:
        return None

    details = "\n".join(
        "- "
        + item
        for item in relevant
    )

    return (
        "CORE CLAIM-GROUNDING REPAIR:\n"
        "The previous draft introduced factual statements that were not "
        "grounded in Oliver's current message, recent USER-provided context, "
        "or Core's verified evidence.\n"
        f"{details}\n\n"
        "Rewrite the response with those factual claims REMOVED. Do not "
        "replace them with different external facts. Keep the response "
        "natural; subjective reaction and clearly non-literal banter are fine "
        "when they do not rely on an unsupported factual premise. A short "
        "response is better than invented detail."
    )


def build_core_grounding_fallback(
    core_answer_contract: Optional[str],
) -> str:
    """
    Fail closed after repeated semantic-grounding failures.

    These deliberately contain almost no factual content.
    """

    intent = contract_intent(
        core_answer_contract
    )

    if intent == "share_context":
        return (
            "Fair enough. That makes sense."
        )

    if intent == "acknowledge":
        return (
            "Anytime."
        )

    return (
        "Got it."
    )
