import re


OPINION_PATTERNS = [
    r"\bwhat do you think\b",
    r"\bwhat's your opinion\b",
    r"\bwhat is your opinion\b",
    r"\byour opinion\b",
    r"\bwhat are your top\b",
    r"\bwhat's your top\b",
    r"\bwhat is your top\b",
    r"\bfavou?rite\b",
    r"\bbest character\b",
    r"\bbest characters\b",
    r"\bworst character\b",
    r"\bworst characters\b",
    r"\boverrated\b",
    r"\bunderrated\b",
    r"\bbetter than\b",
    r"\btop \d+\b",
]

CHALLENGE_PATTERNS = [
    r"\byou(?:'re| are) wrong\b",
    r"\bwrong\b",
    r"\bprove (?:me|it)\b",
    r"\bprove that\b",
    r"\bdefend (?:that|it|your)\b",
    r"\bi disagree\b",
    r"\bdon't agree\b",
    r"\bdo not agree\b",
    r"\bnah\b",
    r"\bna\b",
    r"\bno way\b",
    r"\b(?:trying|picking|choosing).{0,25}\bbe different\b",
    r"\bjust.{0,20}\bbe different\b",
    r"\bgeneric\b",
    r"\bbad take\b",
    r"\bshit take\b",
    r"\bterrible take\b",
    r"\bmid take\b",
]

USER_STANCE_PATTERNS = [
    r"\bi think\b",
    r"\bi reckon\b",
    r"\bfor me\b",
    r"\bmy top\b",
    r"\bmy favourite\b",
    r"\bmy favorite\b",
    r"\bi prefer\b",
    r"\bi like\b",
    r"\bi love\b",
    r"\bi hate\b",
    r"\bi dislike\b",
    r"\bi rate\b",
    r"\bi don't rate\b",
    r"\bi do not rate\b",
]

MEDIA_DISCUSSION_PATTERNS = [
    r"\banime\b",
    r"\bmanga\b",
    r"\banimanga\b",
    r"\blight novel\b",
    r"\bnovel\b",
    r"\bbook\b",
    r"\bseries\b",
    r"\bshow\b",
    r"\bmovie\b",
    r"\bfilm\b",
    r"\bcharacter\b",
    r"\bcharacters\b",
    r"\bepisode\b",
    r"\bchapter\b",
    r"\barc\b",
    r"\bgame\b",
]

CANON_DETAIL_PATTERNS = [
    r"\barc\b",
    r"\bchapter\b",
    r"\bepisode\b",
    r"\bvolume\b",
    r"\bseason\b",
    r"\bfaction\b",
    r"\brank\b",
    r"\btitle\b",
    r"\bpower\b",
    r"\bability\b",
    r"\bbackstory\b",
    r"\blore\b",
    r"\bcanon\b",
    r"\bplot\b",
    r"\bstory\b",
    r"\bwho (?:is|was|did|killed|fought|beat)\b",
    r"\bwhat happened\b",
    r"\bwhen did\b",
    r"\bwhy did\b",
]

GENERIC_ENDING_PATTERNS = [
    r"\bhow can i assist\b",
    r"\bhow may i help\b",
    r"\bwould you like me to\b",
    r"\bdo you want me to\b",
    r"\bwant me to outline\b",
]


def _normalise(text):
    return re.sub(
        r"\s+",
        " ",
        str(text or "").lower().strip(),
    )


def _matches_any(
    text,
    patterns,
):
    return any(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        for pattern in patterns
    )


def classify_conversation_policy(
    user_input,
):
    """
    Classify ordinary conversational behaviour.

    Core decides whether Mairon should be cautious with factual detail
    and whether the turn offers a genuine opportunity for reciprocal
    conversation.
    """

    text = _normalise(
        user_input
    )

    opinion_turn = _matches_any(
        text,
        OPINION_PATTERNS,
    )

    challenge_turn = _matches_any(
        text,
        CHALLENGE_PATTERNS,
    )

    user_stance_present = _matches_any(
        text,
        USER_STANCE_PATTERNS,
    )

    media_discussion = _matches_any(
        text,
        MEDIA_DISCUSSION_PATTERNS,
    )

    canon_detail_request = _matches_any(
        text,
        CANON_DETAIL_PATTERNS,
    )

    knowledge_honesty = (
        media_discussion
        or opinion_turn
        or canon_detail_request
    )

    if challenge_turn:
        reciprocity = "high"

    elif user_stance_present:
        reciprocity = "medium"

    elif opinion_turn:
        reciprocity = "high"

    else:
        reciprocity = "normal"

    return {
        "opinion_turn": opinion_turn,
        "challenge_turn": challenge_turn,
        "user_stance_present": user_stance_present,
        "media_discussion": media_discussion,
        "canon_detail_request": canon_detail_request,
        "knowledge_honesty": knowledge_honesty,
        "reciprocity": reciprocity,
    }


def build_conversation_policy_text(
    policy,
):
    """
    Convert Core's behavioural classification into compact model
    instructions. These are principles, not canned dialogue.
    """

    lines = [
        "CORE CONVERSATION POLICY:",
    ]

    if policy.get(
        "knowledge_honesty"
    ):
        lines.extend([
            "",
            "Knowledge honesty: STRICT.",
            "- Do not bluff detailed knowledge merely to sound informed.",
            "- Separate subjective opinion from factual/canon claims.",
            "- Never invent an arc name, chapter/episode title, film/game/book title, faction, rank, ability, relationship, event, quote, character motivation, or piece of lore.",
            "- Before using a specific canon detail as evidence, include it only if you are genuinely confident it is correct.",
            "- If confidence in a detail is low, OMIT that detail and use a broader reason instead.",
            "- If the user's question genuinely requires a detail you do not know confidently, say so plainly rather than guessing.",
            "- Do not claim that you personally watched, read, played, heard, or physically experienced media. Describe your knowledge/confidence instead.",
            "- Strong opinions are allowed. Fabricated evidence supporting those opinions is not.",
            "- A ranking does not require fake lore. Broad reasons such as personality, presence, humour, design, dynamics, themes, or role are enough when those are what you actually know.",
            "- Never invent a more specific explanation just because the broader truthful explanation sounds less impressive.",
        ])

    reciprocity = policy.get(
        "reciprocity",
        "normal",
    )

    lines.extend([
        "",
        f"Conversational reciprocity: {reciprocity.upper()}.",
        "- Mairon is participating in a conversation, not completing a support ticket.",
        "- Do not mechanically end after answering if there is a genuinely interesting disagreement, information gap, or opinion worth pursuing.",
        "- Challenge Oliver when there is a real point of disagreement. Defend your reasoning rather than conceding for politeness.",
        "- If Oliver makes a genuinely good point, acknowledge it or revise your view.",
        "- Curiosity must be specific to the discussion. Never use generic customer-service follow-ups.",
        "- Ask at most ONE direct question in a response.",
        "- Do not ask a question merely because a conversation exists. Sometimes a statement, challenge, or reaction is the better continuation.",
        "- Never ask Oliver for information he already gave in the visible or retrieved conversation.",
    ])

    if reciprocity == "high":
        lines.extend([
            "- This turn has a strong conversational opportunity.",
            "- Normally keep the exchange alive by doing at least one of: challenge Oliver's reasoning; defend Mairon's stance; ask for Oliver's corresponding ranking/position if it is still unknown; ask one pointed question about WHY he holds the view; or directly invite him to make his case.",
            "- Prefer a pointed, personality-consistent continuation over generic wording such as 'What do you think?'",
            "- If Oliver criticises Mairon's choice, do not simply replace the choice to please him. Defend it, reconsider it for an actual reason, or make Oliver argue his case.",
        ])

    elif reciprocity == "medium":
        lines.extend([
            "- Oliver has supplied a personal stance or preference.",
            "- React specifically to the stance rather than ignoring it.",
            "- A challenge or one focused question is welcome when there is something genuinely interesting to pursue.",
            "- Do not immediately turn Oliver's statement into an interview. A sharp reaction or counterpoint may be better than a question.",
        ])

    return "\n".join(
        lines
    )


def find_conversation_policy_violations(
    response_text,
):
    """
    Catch deterministic policy regressions.

    Canon correctness itself cannot be reliably regex-validated, so
    epistemic restraint is primarily enforced during generation.
    """

    text = _normalise(
        response_text
    )

    violations = []

    for pattern in GENERIC_ENDING_PATTERNS:
        if re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "generic conversational follow-up"
            )
            break

    human_experience_patterns = [
        r"\bwhen i watched\b",
        r"\bi watched (?:it|that|the)\b",
        r"\bwhen i read\b",
        r"\bi read (?:it|that|the)\b",
        r"\bwhen i played\b",
        r"\bi played (?:it|that|the)\b",
    ]

    if _matches_any(
        text,
        human_experience_patterns,
    ):
        violations.append(
            "claimed human-style media consumption"
        )

    return violations
