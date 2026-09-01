import json
import re


def _extract_json_object(
    text,
):
    """
    Parse a JSON object from a model response conservatively.
    """

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

        if isinstance(
            parsed,
            dict,
        ):
            return parsed

    except Exception:
        return None

    return None


def verify_media_draft(
    client,
    model,
    user_input,
    draft,
    research_evidence,
    self_correction_context=None,
    opinion_context=None,
):
    """
    Isolated semantic fact-check against the actual evidence packet.

    The verifier's job is intentionally narrow:
    - subjective taste does not require citation;
    - claims about canon/current events/roles/history DO;
    - a claim unsupported by the supplied evidence fails even if the
      verifier happens to know it from model memory.
    """

    if not research_evidence:
        return []

    system_text = (
        "You are Mairon Core's INTERNAL factual-support verifier. "
        "You are not speaking to Oliver.\n\n"
        "Compare the proposed conversational draft against the supplied "
        "source-grounded evidence. Treat the evidence packet, Oliver's "
        "current message, explicit Opinion Ledger state, and explicit "
        "immediate self-correction context as the ONLY allowed grounding "
        "for specific media/canon/current factual claims.\n\n"
        "IMPORTANT RULES:\n"
        "- Do NOT use your own training-memory knowledge to rescue a claim.\n"
        "- Subjective preference, humour, and aesthetic judgment do not need "
        "source support unless they smuggle in a factual premise.\n"
        "- Specific claims about ranks, factions, titles, abilities, deaths, "
        "relationships, backstory, plot events, chronology, chapter/episode "
        "content, release events, character actions, character history, or "
        "adaptation status MUST be explicitly supported by the evidence.\n"
        "- Speculation and rumours are unsupported unless the evidence itself "
        "explicitly establishes that the claim is speculation/rumour AND the "
        "user asked for that kind of material.\n"
        "- If the draft contradicts the evidence, mark it unsupported.\n"
        "- If a claim is plausible but absent from the evidence, mark it "
        "unsupported. Plausibility is not evidence.\n\n"
        "Return JSON ONLY in this exact shape:\n"
        "{\n"
        '  "supported": true,\n'
        '  "unsupported_claims": []\n'
        "}\n\n"
        "If anything specific is unsupported, set supported=false and quote "
        "short descriptions of each unsupported claim."
    )

    messages = [
        {
            "role": "system",
            "content": system_text,
        },
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
            "role": "system",
            "content": research_evidence,
        },
    ]

    if self_correction_context:
        messages.append({
            "role": "system",
            "content": self_correction_context,
        })

    if opinion_context:
        messages.append({
            "role": "system",
            "content": opinion_context,
        })

    messages.append({
        "role": "user",
        "content": (
            "PROPOSED MAIRON DRAFT TO VERIFY:\n"
            + str(
                draft
            )
        ),
    })

    result = client.chat(
        model=model,
        messages=messages,
    )

    parsed = _extract_json_object(
        result.message.content
    )

    if not parsed:
        # Verification failure should fail closed rather than silently
        # approving a media answer.
        return [
            "media factual-support verifier could not validate the draft"
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
        :6
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
                "unsupported media claim: "
                + claim
            )
            for claim in cleaned
        ]

    return [
        "media response contained unsupported factual claims"
    ]


def build_grounding_retry_instruction(
    violations,
):
    unsupported = [
        violation
        for violation in violations
        if (
            "unsupported media claim"
            in violation
            or "factual-support verifier"
            in violation
            or "unsupported factual claims"
            in violation
        )
    ]

    if not unsupported:
        return None

    details = "\n".join(
        "- "
        + item
        for item in unsupported
    )

    return (
        "MEDIA FACTUAL-GROUNDING REPAIR:\n"
        "Core found factual/canon statements that are not supported by "
        "the actual research evidence.\n"
        f"{details}\n\n"
        "Rewrite the response with those claims REMOVED. Do not replace "
        "them with different unverified lore. Keep subjective opinions if "
        "you want, but factual reasons must come from the supplied evidence. "
        "A shorter answer is correct if the evidence is thin."
    )


def _extract_ranked_names(
    stance_text,
    expected_count=None,
):
    """
    Recover the subjective selections from a previously stored ranking
    without reusing its factual explanations.

    This is intentionally conservative and only handles clear numbered
    ranking formats.
    """

    text = str(
        stance_text or ""
    )

    patterns = [
        r"(?m)^\s*\d+\.\s+\*\*([^*\n]+)\*\*",
        r"(?m)^\s*\d+\.\s+([A-Z][^\n–—:-]{1,60})(?:\s*[–—:-])",
    ]

    for pattern in patterns:
        names = [
            re.sub(
                r"\s+",
                " ",
                match.strip(),
            )
            for match in re.findall(
                pattern,
                text,
            )
        ]

        names = [
            name
            for name in names
            if name
        ]

        if names:
            if expected_count:
                names = names[
                    :int(
                        expected_count
                    )
                ]

            return names

    return []


def _natural_join(
    items,
):
    values = [
        str(
            item
        ).strip()
        for item in items
        if str(
            item
        ).strip()
    ]

    if not values:
        return ""

    if len(values) == 1:
        return values[
            0
        ]

    if len(values) == 2:
        return (
            values[
                0
            ]
            + " and "
            + values[
                1
            ]
        )

    return (
        ", ".join(
            values[
                :-1
            ]
        )
        + ", and "
        + values[
            -1
        ]
    )


def build_failed_grounding_fallback(
    opinion_entry=None,
):
    """
    Fail closed after repeated unsupported drafts.

    For an established ranking, preserve only the subjective selections
    and discard old factual explanations.
    """

    if opinion_entry:
        names = _extract_ranked_names(
            opinion_entry.get(
                "stance_text",
                "",
            ),
            expected_count=opinion_entry.get(
                "count"
            ),
        )

        if names:
            return (
                "I'm keeping the same picks: "
                + _natural_join(
                    names
                )
                + ". My verification pass isn't clean enough for me to "
                "start decorating that with canon claims, so I'm leaving "
                "the supporting lore out rather than bullshitting you."
            )

        return (
            "I'm keeping my established stance, but I'm not going to "
            "pile more canon claims onto it when my verification pass "
            "isn't clean enough. I need better evidence before I start "
            "pretending the details are settled."
        )

    return (
        "I couldn't verify that cleanly enough to give you a detailed "
        "answer without risking making shit up, so I'm not going to bluff it."
    )
