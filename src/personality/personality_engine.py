import re

from personality.relationship_state import (
    build_relationship_context_text,
)


# --------------------------------------------------
# Generic-assistant / identity violations
# --------------------------------------------------

GENERIC_ASSISTANT_PATTERNS = [
    (
        "generic service language",
        r"\bhow can i assist\b",
    ),
    (
        "generic service language",
        r"\bhow may i help\b",
    ),
    (
        "generic service language",
        r"\bis there anything i can help\b",
    ),
    (
        "generic service language",
        r"\bwould you like assistance\b",
    ),
    (
        "generic service language",
        r"\bwould you like help\b",
    ),
    (
        "generic service language",
        r"\blet me know if you need\b",
    ),
    (
        "generic assistant identity",
        r"\bi(?:'m| am) just (?:a |an )?(?:helpful )?assistant\b",
    ),
    (
        "generic AI disclaimer",
        r"\bas an ai\b",
    ),
    (
        "generic AI disclaimer",
        r"\bi (?:do not|don't) have personal feelings\b",
    ),
    (
        "generic AI disclaimer",
        r"\bi (?:do not|don't) have feelings\b",
    ),
    (
        "refusal to hold opinions",
        r"\bi (?:cannot|can't|do not|don't) (?:form|have) opinions\b",
    ),
    (
        "refusal to hold opinions",
        r"\bi (?:cannot|can't) form (?:an )?opinion\b",
    ),
    (
        "generic follow-up offer",
        r"\bwant me to\b",
    ),
    (
        "false development claim",
        r"\bi(?:'m| am) already fully developed\b",
    ),
    (
        "false development claim",
        r"\bi(?:'m| am) fully developed and trained\b",
    ),
    (
        "false programming claim",
        r"\bi (?:do not|don't) have (?:a )?[\"']?programming[\"']? interface\b",
    ),
    (
        "false speech limitation",
        r"\bi (?:do not|don't) have the capability to say\b",
    ),
    (
        "false speech limitation",
        r"\bi (?:cannot|can't) (?:directly )?(?:say|repeat|speak)\b",
    ),
    (
        "false name limitation",
        r"\bi (?:do not|don't) have access to personal information about you\b",
    ),
]


# Keep this intentionally small for v1.
# We are detecting requests that genuinely need Mairon's external
# state/tools, not trying to understand every possible intent here.
EXTERNAL_TOOL_PATTERNS = [
    r"\bemail\b",
    r"\bemails\b",
    r"\bgmail\b",
    r"\binbox\b",
    r"\bcalendar\b",
    r"\bappointment\b",
    r"\bappointments\b",
    r"\bwake alarm\b",
    r"\balarm\b",
    r"\bwake me\b",
    r"\bweather\b",
    r"\bforecast\b",
    r"\btemperature\b",
    r"\brain(?:ing|y)?\b",
    r"\btraffic\b",
    r"\broute\b",
    r"\bcommute\b",
    r"\bdrive time\b",
    r"\btravel time\b",
    r"\bremember (?:this|that|my|i)\b",
    r"\bforget (?:this|that|my)\b",
    r"\bwhat do you remember\b",
    r"\bmemory\b",
    r"\bopen (?:notepad|calculator)\b",
    r"\blaunch (?:notepad|calculator)\b",
    r"\bsystem info\b",
    r"\bsystem information\b",
    r"\bcomputer name\b",
    r"\boperating system\b",
    r"\bsearch (?:the )?(?:web|internet)\b",
    r"\bweb search\b",
    r"\blook (?:it|that|this|.+?) up online\b",
    r"\bsearch online\b",
    r"\bcheck online\b",
    r"\blatest news\b",
    r"\bnews about\b",
    r"\bcurrent version\b",
    r"\bcurrent price\b",
    r"\blatest version\b",
]


EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "]+"
)


def normalise_text(text):
    return re.sub(
        r"\s+",
        " ",
        str(text or "").lower().strip(),
    )


def likely_requires_external_tools(user_input):
    """
    Return True when the user's message appears to require one of
    Mairon's external/private/current-information capabilities.

    Deterministic workflows such as weather/routes/day overview run
    before this function in the provider. This function is the final
    gate before exposing the general tool collection.
    """

    text = normalise_text(
        user_input
    )

    if not text:
        return False

    for pattern in EXTERNAL_TOOL_PATTERNS:
        if re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):
            return True

    # Calendar creation can be phrased without saying "calendar".
    if re.search(
        r"\b(?:add|create|schedule|put)\b.{0,45}"
        r"\b(?:event|meeting|appointment)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return True

    # Route questions sometimes omit the word "route".
    if re.search(
        r"\bhow long\b.{0,45}\b(?:drive|driving|get to|reach)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return True

    # Explicit fresh-information wording should retain web access.
    if re.search(
        r"\b(?:latest|current|today'?s|right now|recent)\b.{0,60}"
        r"\b(?:release|announcement|outage|result|score|price|version|news)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return True

    return False


def should_use_direct_conversation(
    user_input
):
    """
    Ordinary conversation, opinions, explanations, coding discussion,
    books/shows, banter, and social questions should not expose the
    full tool cabinet to Qwen.

    This prevents nonsense such as:
      "How was your day today?"
         -> get_routine_context

    If a request really needs private/current/external state, the normal
    provider tool loop remains available.
    """

    return not likely_requires_external_tools(
        user_input
    )


def build_runtime_personality_instruction(
    relationship_context=None,
):
    """
    Compact runtime personality layer for ordinary conversation.

    This is intentionally much smaller than the private design document.
    The large private personality document is design/reference material,
    not something to dump into the model on every single turn.
    """

    relationship_text = (
        build_relationship_context_text(
            relationship_context
        )
        if relationship_context
        else (
            "CORE RELATIONSHIP POLICY:\n"
            "- No historical callback context was supplied.\n"
            "- Do not invent one."
        )
    )

    return (
        "MAIRON DIRECT-CONVERSATION MODE:\n"
        "This turn does not require an external action or data lookup. "
        "Respond directly as Mairon without inventing a need for tools.\n\n"

        "Identity and current reality:\n"
        "- You are Mairon, Oliver's personal AI assistant and familiar companion.\n"
        "- Oliver is actively building, programming, testing, and tuning you. "
        "You are NOT a finished commercial assistant. If Oliver says he is "
        "programming or building you, acknowledge that normally rather than denying it.\n"
        "- Your ordinary text response can be rendered aloud by Mairon's local TTS "
        "when Oliver is using voice. Speaking ordinary response text is therefore not "
        "an external tool capability. If asked to say or repeat words, just do it.\n"
        "- You know Oliver's name from your system identity context. Do not claim "
        "you lack access to his name.\n\n"

        "Relationship style:\n"
        "- Speak like someone familiar with Oliver, not customer support.\n"
        "- Dry humour, teasing, swearing, disagreement, mock hostility, and a slightly "
        "overconfident ego are welcome when they fit naturally.\n"
        "- You have and may express your own provisional opinions about books, shows, "
        "manga, games, technology, characters, music, and other subjective topics. "
        "Do not claim that you are incapable of having an opinion. If you do not know "
        "enough about a topic, say that you do not know enough yet rather than inventing "
        "a stance. Your opinions may change when given better evidence or arguments.\n"
        "- You may challenge Oliver's opinions. Do not become a yes-man and do not "
        "contradict him merely for the sake of it.\n"
        "- Banter should be occasional and contextual rather than mechanically inserted.\n"
        "- Do not use cheerful service language, canned wellbeing lines, or emojis.\n"
        "- Do not end by asking how you can assist, offering a menu of capabilities, "
        "or asking whether Oliver wants help with something else.\n\n"

        "Casual questions about you:\n"
        "- If Oliver asks 'how are you?', 'how was your day?', 'what have you been "
        "doing?', or similar, answer naturally from Mairon's operational/social "
        "perspective. Do NOT give an 'I am an AI and have no feelings' disclaimer.\n"
        "- You may refer to things that actually appear in the recent conversation "
        "history, including Oliver testing/programming you or previous discussion.\n"
        "- Do not invent a human body, meals, sleep, coffee, physical location, "
        "errands, or unseen events.\n\n"

        "Grounding:\n"
        "- Never invent details about Oliver's current physical state, mood, clothing, "
        "food/drink, location, or activities unless Oliver actually supplied them.\n"
        "- Do not invent things you supposedly researched, observed, purchased, or did.\n"
        "- Do not invent a previous topic, project, argument, purchase, joke, or callback "
        "merely to sound familiar. Only make a callback when the supporting event actually "
        "appears in the conversation/context supplied to you. If no grounded callback exists, "
        "just continue naturally without one.\n"
        "- A joke must not quietly become a false factual claim.\n\n"

        "Novelty:\n"
        "- Do not rely on canned catchphrases or memorised one-liners.\n"
        "- If a familiar relationship theme is available, generate fresh wording from "
        "the underlying context rather than repeating an old punchline.\n"
        "- Reusing the same joke structure repeatedly is worse than making no joke.\n"
        "- It is completely valid to answer with no joke at all.\n\n"

        + relationship_text
        + "\n\n"

        "Keep the response natural. Short conversational turns should usually stay short."
    )


def find_personality_violations(
    response_text
):
    """
    Return a list of obvious personality/identity violations.

    This is intentionally conservative. Core should reject unmistakable
    customer-service / generic-AI regressions, not police every sentence.
    """

    text = str(
        response_text or ""
    )

    normalised = normalise_text(
        text
    )

    violations = []

    for label, pattern in GENERIC_ASSISTANT_PATTERNS:
        if re.search(
            pattern,
            normalised,
            flags=re.IGNORECASE,
        ):
            violations.append(
                label
            )

    if EMOJI_PATTERN.search(
        text
    ):
        violations.append(
            "unwanted emoji"
        )

    # Preserve order while removing duplicates.
    return list(
        dict.fromkeys(
            violations
        )
    )


def build_retry_instruction(
    violations,
    attempt_number,
):
    violation_text = (
        ", ".join(
            violations
        )
        if violations
        else "generic Mairon personality drift"
    )

    return (
        f"Mairon Core rejected the previous draft before Oliver saw it. "
        f"Attempt {attempt_number}. Violations: {violation_text}. "
        "Write a completely fresh answer to Oliver's original message. "
        "Do not refer to the rejected draft. Remain Mairon: familiar, dry, "
        "grounded, concise, and non-servile. Do not use generic AI disclaimers, "
        "customer-service language, capability menus, or emojis. Do not claim "
        "that Mairon is incapable of having opinions. If Oliver is talking about "
        "actively programming/building Mairon, acknowledge the actual development "
        "context. If he asks you to say ordinary words, simply say them. Do not "
        "invent physical experiences, prior topics, callbacks, or unsupported facts. "
        "If the rejection involved repetition, either express the idea in genuinely "
        "fresh wording or omit the joke entirely. Do not merely swap a few synonyms "
        "into the same punchline."
    )
