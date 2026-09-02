import re
from typing import Optional

from core.turn_state import TurnState


THANKS_PATTERNS = [
    r"^\s*thanks\b",
    r"^\s*thank you\b",
    r"^\s*cheers\b",
    r"\bthanks mairon\b",
]

QUESTION_PATTERNS = [
    r"\?$",
    r"^\s*(?:what|why|who|where|when|how|does|do|did|is|are|can|could|would|should|has|have|will)\b",
]

APPLICATION_LAUNCH_PATTERN = re.compile(
    r"\b(?:open|launch|start)(?:\s+up)?\s+(?:the\s+)?"
    r"(?P<app>calculator|notepad)\b",
    flags=re.IGNORECASE,
)


ACTION_PATTERNS = [
    r"^\s*(?:check|send|turn|open|close|start|stop|set|remind|search|find|look|show|tell|wake|shutdown|shut down|restart|download|upload|move|copy)\b",
]

ORDER_STATUS_PATTERNS = [
    r"\b(?:order|package|parcel|delivery)\b.{0,80}\b(?:arrived|delivered|ready|collect|collection|status|where)\b",
    r"\b(?:arrived|delivered|ready to collect|awaiting collection)\b.{0,80}\b(?:order|package|parcel|delivery)\b",
    r"\bhas my .{0,80}\b(?:arrived|been delivered)\b",
    r"\bwhere(?:'s| is) my .{0,80}\b(?:order|package|parcel)\b",
]

EMAIL_REQUEST_PATTERNS = [
    r"\b(?:check|search|look through|look at|find)\b.{0,60}\b(?:email|emails|inbox|gmail)\b",
    r"\b(?:email|emails|inbox|gmail)\b.{0,60}\b(?:check|search|find)\b",
]

EMAIL_LOOKUP_PATTERNS = [
    r"\bhave i (?:received|got|had) (?:an |any )?(?:email|emails|message|messages)\b",
    r"\bdid i (?:receive|get) (?:an |any )?(?:email|emails|message|messages)\b",
    r"\b(?:any|an) (?:email|emails|message|messages) from\b",
    r"\bhas .{1,80} emailed me\b",
    r"\bdid .{1,80} email me\b",
    r"\b(?:email|emails|message|messages) from .{1,100}\b",
    r"\b(?:email|emails|message|messages) about .{1,100}\b",
]

CONTEXTUAL_EMAIL_FOLLOWUP_PATTERNS = [
    r"\bdid i get anything from\b",
    r"\bdid i receive anything from\b",
    r"\bhave i got anything from\b",
    r"\bhave i received anything from\b",
    r"\banything from .{1,100}\b",
    r"\banything from (?:them|him|her)\b",
]

DECLARATIVE_SHARE_PATTERNS = [
    r"^\s*(?:they|it|these|those|this)\s+(?:are|is|were|was)\b",
    r"^\s*i(?:'m| am| just| bought| got| have| own| use| read| watch| like| love| hate| reckon| think)\b",

    # First-person plural updates are also user-provided context:
    #
    # - "We aren't driving anywhere."
    # - "We are taking trains."
    # - "We have one domestic flight."
    #
    # These should not fall through to generic casual conversation.
    r"^\s*we(?:'re| are| aren't| arent| were| weren't| werent| have| haven't| havent| got| take| are taking| will| won't| wont| plan| planned)\b",

    # Personal/household status updates often begin with a possessive noun
    # phrase rather than "I" or "they":
    #
    # - "My XT6s have arrived for my China trip in November!"
    # - "My new monitor is here."
    # - "My exam got moved."
    # - "Our flight has changed."
    #
    # These are declarative user-provided context. They must not fall through
    # to generic casual conversation, because generic conversation may enable
    # unrelated long-term retrieval.
    r"^\s*(?:my|our)\s+[^?]{1,140}?\s+"
    r"(?:is|are|was|were|has|have|had|got|gets|came|arrived|changed|moved|turned|looks|feels|seems)\b",

    r"\bfor my trip\b",
    r"\bgotta\b",
    r"\byou know\b",
]

OPINION_PATTERNS = [
    r"\bi think\b",
    r"\bi reckon\b",
    r"\bin my opinion\b",
    r"\bfor me\b",
    r"\bis the best\b",
    r"\bis better\b",
    r"\bis worse\b",
    r"\boverrated\b",
    r"\bunderrated\b",
]

CONVERSATION_RECALL_PATTERNS = [
    r"\bwhat did i say\b",
    r"\bwhat did i tell you\b",
    r"\bwhat was it i said\b",
    r"\bremind me what i said\b",
    r"\bwhat did you say\b",
    r"\bwhat did you tell me\b",
]

SELF_CORRECTION_PATTERNS = [
    r"\bscratch that\b",
    r"\bi meant\b",
    r"\bcorrection\s*[:,]",
    r"\bi got that wrong\b",
    r"\bi said that wrong\b",
    r"\blet me correct myself\b",
]

MAIRON_CORRECTION_PATTERNS = [
    r"\byou(?:'re| are) wrong\b",
    r"\bthat's wrong\b",
    r"\bthat is wrong\b",
    r"\byou just said\b",
    r"\byou said\b",

    # Challenges to Mairon's immediately preceding claim/source.
    r"\bwhere\s+(?:are|were)\s+you\s+getting\b",
    r"\bwhere\s+did\s+you\s+get\b",
    r"\bi\s+never(?:\s+even)?\s+asked\b",
    r"\bi\s+didn'?t\s+ask\b",
    r"\bi\s+did\s+not\s+ask\b",
]

# Backward-compatible name for any older tests/helpers that imported the
# original constant directly. New routing uses the more precise name above.
CORRECTION_PATTERNS = MAIRON_CORRECTION_PATTERNS

BANTER_PATTERNS = [
    r"\blmao\b",
    r"\blol\b",
    r"\bhahaha+\b",
    r"\bbro\b",
    r"\bbruh\b",
    r"\bdumb cunt\b",
    r"\byou idiot\b",
]

RECOMMENDATION_REQUEST_PATTERNS = [
    r"\bwhat should i buy\b",
    r"\bwhat do you recommend\b",
    r"\brecommend\b",
    r"\bany suggestions\b",
    r"\bwhat shoes should\b",
    r"\bwhat would you buy\b",
]

FOLLOW_UP_PRONOUNS = {
    "it", "that", "this", "they", "them", "those", "these", "he", "she",
}


def _extract_application_name(
    text: str,
) -> Optional[str]:
    match = APPLICATION_LAUNCH_PATTERN.search(
        str(
            text or ""
        )
    )

    if not match:
        return None

    app_name = (
        match.group(
            "app"
        )
        or ""
    ).strip().lower()

    if app_name not in {
        "calculator",
        "notepad",
    }:
        return None

    return app_name


DISCOURSE_PREFIX_PATTERN = re.compile(
    r"^(?:(?:mate|bro|bruh|dude|man|yeah|yep|nah|nope|okay|ok|lol|lmao|haha+|"
    r"anyway|well|also|at\s+least)"
    r"(?:\s*[,!.-]\s*|\s+))+",
    flags=re.IGNORECASE,
)


def _normalise(text: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(
            text or ""
        ).strip().lower(),
    )


def _strip_discourse_prefixes(
    text: str,
) -> str:
    """
    Remove casual conversation lead-ins ONLY for intent classification.

    Raw user text is preserved everywhere else.

    Examples:
    - "Mate they are currently on my feet" -> "they are currently on my feet"
    - "Bro can you open the calculator?" -> "can you open the calculator?"
    """

    value = str(
        text or ""
    ).strip()

    previous = None

    while (
        value
        and value != previous
    ):
        previous = value

        value = DISCOURSE_PREFIX_PATTERN.sub(
            "",
            value,
            count=1,
        ).strip()

    return value


def _matches_any(text: str, patterns) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _is_personal_declarative_share(
    text: str,
) -> bool:
    """
    Recognise ordinary user-provided personal/context statements without
    enumerating every verb Oliver might use.

    This is intentionally a speech-act test, not a factual-domain test.
    Questions and request-shaped first-person sentences are excluded.
    """

    value = str(
        text
        or ""
    ).strip()

    if not value:
        return False

    if _matches_any(
        value,
        QUESTION_PATTERNS,
    ):
        return False

    # "I need you to...", "I want you to..." and similar request shapes
    # are not declarative context merely because they begin with "I".
    if re.match(
        r"^\s*i\s+(?:need|want|would\s+like|want\s+you|need\s+you|"
        r"am\s+asking\s+you|ask\s+you)\b",
        value,
        flags=re.IGNORECASE,
    ):
        return False

    if re.match(
        r"^\s*i\b",
        value,
        flags=re.IGNORECASE,
    ):
        return True

    if re.match(
        r"^\s*(?:my|our|we)\b",
        value,
        flags=re.IGNORECASE,
    ):
        return True

    if re.match(
        r"^\s*(?:it|this|that|they|these|those)\b",
        value,
        flags=re.IGNORECASE,
    ):
        return True

    return False


def _extract_merchant_from_order_text(text: str) -> Optional[str]:
    patterns = [
        r"\b(?:order|package|parcel)\s+from\s+(.+?)\s+(?:arrived|been delivered|ready|status)\b",
        r"\bmy\s+(.+?)\s+(?:order|package|parcel)\s+(?:arrived|been delivered|ready|status)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue

        value = re.sub(r"\s+", " ", match.group(1).strip(" ?!.,"))
        if value and len(value) <= 80:
            return value

    return None


def _extract_email_search_text(
    text: str,
) -> Optional[str]:
    """
    Extract the person/company/topic Oliver wants Gmail searched for.

    Examples:
    - "Have I received any emails from Prosple in the last couple days?"
      -> "Prosple"
    - "Did Richard from Prosple email me?"
      -> "Richard from Prosple"
    - "Check my emails for CyberCX"
      -> "CyberCX"
    """

    patterns = [
        r"\b(?:email|emails|message|messages)\s+from\s+(.+?)(?=\s+(?:in|over|during|within|since|today|yesterday|this|last|past)\b|[?.!,]|$)",
        r"\b(?:email|emails|message|messages)\s+about\s+(.+?)(?=\s+(?:in|over|during|within|since|today|yesterday|this|last|past)\b|[?.!,]|$)",
        r"\b(?:received|receive|got|get|had)\s+(?:an\s+|any\s+)?(?:email|emails|message|messages)\s+from\s+(.+?)(?=\s+(?:in|over|during|within|since|today|yesterday|this|last|past)\b|[?.!,]|$)",
        r"\b(?:check|search|find|look through|look at)\s+(?:my\s+)?(?:email|emails|inbox|gmail)\s+(?:for|from|about)\s+(.+?)(?=\s+(?:in|over|during|within|since|today|yesterday|this|last|past)\b|[?.!,]|$)",
        r"\bhas\s+(.+?)\s+emailed\s+me\b",
        r"\bdid\s+(.+?)\s+email\s+me\b",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        value = re.sub(
            r"\s+",
            " ",
            match.group(1).strip(" ?!.,"),
        )

        if value and len(value) <= 120:
            return value

    return None


def _active_email_search_text(
    conversation_state,
) -> Optional[str]:
    if conversation_state is None:
        return None

    if (
        getattr(
            conversation_state,
            "active_intent",
            None,
        )
        != "email_search"
    ):
        return None

    active_entities = getattr(
        conversation_state,
        "active_entities",
        {},
    ) or {}

    value = active_entities.get(
        "search_text"
    )

    if not value:
        return None

    value = str(
        value
    ).strip()

    return value or None


def _is_contextual_email_followup(
    text: str,
    conversation_state,
) -> bool:
    if not _active_email_search_text(
        conversation_state
    ):
        return False

    return _matches_any(
        text,
        CONTEXTUAL_EMAIL_FOLLOWUP_PATTERNS,
    )


def _extract_contextual_email_search_text(
    text: str,
    conversation_state,
) -> Optional[str]:
    """
    Resolve a follow-up such as:
    - "Did I get anything from Prosple yesterday?"
    - "Did I get anything from them yesterday?"
    """

    match = re.search(
        r"\bfrom\s+(.+?)(?=\s+(?:today|yesterday|in|over|during|within|since|this|last|past|previous)\b|[?.!,]|$)",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return _active_email_search_text(
            conversation_state
        )

    value = re.sub(
        r"\s+",
        " ",
        match.group(1).strip(" ?!.,"),
    )

    if value.lower() in {
        "them",
        "him",
        "her",
        "it",
        "that",
    }:
        return _active_email_search_text(
            conversation_state
        )

    return value or _active_email_search_text(
        conversation_state
    )


def _extract_email_time_scope(
    text: str,
) -> str:
    value = text.lower()

    if re.search(
        r"\byesterday\b",
        value,
    ):
        return "yesterday"

    if re.search(
        r"\btoday\b",
        value,
    ):
        return "today"

    return "rolling_days"


def _extract_email_days(
    text: str,
) -> int:
    """
    Convert common conversational time windows to the existing Gmail
    find_emails(days=...) interface.

    This is intentionally conservative. Exact calendar-date searching can
    become a richer Gmail workflow later.
    """

    value = text.lower()

    if re.search(
        r"\b(?:last|past|previous)\s+couple(?:\s+of)?\s+days\b",
        value,
    ):
        return 2

    numeric_days = re.search(
        r"\b(?:last|past|previous)\s+(\d{1,3})\s+days?\b",
        value,
    )

    if numeric_days:
        return max(
            1,
            min(
                int(numeric_days.group(1)),
                365,
            ),
        )

    if re.search(
        r"\b(?:today|last 24 hours?|past 24 hours?)\b",
        value,
    ):
        return 1

    if re.search(
        r"\byesterday\b",
        value,
    ):
        return 2

    if re.search(
        r"\b(?:this|last|past|previous)\s+week\b",
        value,
    ):
        return 7

    numeric_weeks = re.search(
        r"\b(?:last|past|previous)\s+(\d{1,2})\s+weeks?\b",
        value,
    )

    if numeric_weeks:
        return max(
            1,
            min(
                int(numeric_weeks.group(1)) * 7,
                365,
            ),
        )

    if re.search(
        r"\b(?:this|last|past|previous)\s+month\b",
        value,
    ):
        return 30

    numeric_months = re.search(
        r"\b(?:last|past|previous)\s+(\d{1,2})\s+months?\b",
        value,
    )

    if numeric_months:
        return max(
            1,
            min(
                int(numeric_months.group(1)) * 30,
                365,
            ),
        )

    # Existing Gmail search behaviour defaults to a useful recent window.
    return 30


def _contains_follow_up_pronoun(text: str) -> bool:
    tokens = re.findall(r"[a-z']+", text.lower())
    return any(token in FOLLOW_UP_PRONOUNS for token in tokens)


def classify_turn(user_input: str, conversation_state=None) -> TurnState:
    raw = str(user_input or "").strip()

    text = _strip_discourse_prefixes(
        _normalise(
            raw
        )
    )

    state = TurnState(raw_text=raw)

    if not text:
        state.speech_act = "empty"
        state.intent = "none"
        state.confidence = 1.0
        state.should_answer_directly = False
        state.add_reason("empty input")
        return state

    app_name = _extract_application_name(
        raw
    )

    if app_name:
        state.speech_act = "request_action"
        state.intent = "launch_application"
        state.subject = app_name
        state.entities[
            "app_name"
        ] = app_name
        state.requested_action = "launch_application"
        state.requires_private_data = False
        state.requires_live_data = True
        state.factuality = "action_result"
        state.preferred_authority = "desktop"
        state.should_use_tools = True
        state.should_answer_directly = False
        state.should_recommend = False
        state.should_continue_conversation = False
        state.confidence = 0.99

        state.add_reason(
            "explicit launch request for an approved desktop application"
        )

        return state

    if _matches_any(text, ORDER_STATUS_PATTERNS):
        state.speech_act = "question"
        state.intent = "order_status"
        state.requested_action = "check_order_status"
        state.requires_private_data = True
        state.requires_live_data = True
        state.factuality = "tool_verified"
        state.preferred_authority = "gmail"
        state.should_use_tools = True
        state.should_answer_directly = False
        state.should_recommend = False
        state.confidence = 0.98

        merchant = _extract_merchant_from_order_text(raw)
        if merchant:
            state.entities["merchant"] = merchant
            state.subject = f"{merchant} order"
        else:
            state.subject = "order"

        state.add_reason("explicit order/delivery status question")
        return state

    contextual_email_followup = (
        _is_contextual_email_followup(
            text,
            conversation_state,
        )
    )

    if (
        _matches_any(
            text,
            EMAIL_REQUEST_PATTERNS,
        )
        or _matches_any(
            text,
            EMAIL_LOOKUP_PATTERNS,
        )
        or contextual_email_followup
    ):
        natural_question = (
            _matches_any(
                text,
                EMAIL_LOOKUP_PATTERNS,
            )
            or contextual_email_followup
        )

        state.speech_act = (
            "question"
            if natural_question
            else "request_action"
        )
        state.intent = "email_search"
        state.requested_action = "search_email"
        state.requires_private_data = True
        state.requires_live_data = True
        state.factuality = "tool_verified"
        state.preferred_authority = "gmail"
        state.should_use_tools = True
        state.should_answer_directly = False
        state.should_recommend = False
        state.confidence = (
            0.98
            if contextual_email_followup
            else (
                0.97
                if natural_question
                else 0.94
            )
        )

        if contextual_email_followup:
            search_text = (
                _extract_contextual_email_search_text(
                    raw,
                    conversation_state,
                )
            )
            state.is_follow_up = True
            state.add_reason(
                "inherited active Gmail lookup context"
            )
        else:
            search_text = (
                _extract_email_search_text(
                    raw
                )
            )

        if search_text:
            state.entities[
                "search_text"
            ] = search_text

            state.subject = (
                f"email matching {search_text}"
            )

        state.entities[
            "days"
        ] = _extract_email_days(
            raw
        )

        state.entities[
            "time_scope"
        ] = _extract_email_time_scope(
            raw
        )

        if _contains_follow_up_pronoun(text):
            state.is_follow_up = True
            state.add_reason(
                "email request contains a follow-up pronoun"
            )

        state.add_reason(
            (
                "contextual email follow-up"
                if contextual_email_followup
                else (
                    "natural email existence/lookup question"
                    if natural_question
                    else "explicit email search request"
                )
            )
        )
        return state

    if _matches_any(
        text,
        CONVERSATION_RECALL_PATTERNS,
    ):
        state.speech_act = "question"
        state.intent = "conversation_recall"
        state.factuality = "conversation_grounded"
        state.should_continue_conversation = False
        state.should_recommend = False
        state.should_use_tools = False
        state.confidence = 0.97
        state.add_reason(
            "user explicitly asks what was said in conversation"
        )
        return state

    if _matches_any(
        text,
        SELF_CORRECTION_PATTERNS,
    ):
        state.speech_act = "self_correction"
        state.intent = "self_correction"
        state.factuality = "user_provided_revision"
        state.should_continue_conversation = False
        state.should_recommend = False
        state.should_use_tools = False
        state.confidence = 0.96
        state.add_reason(
            "user explicitly revises their own earlier statement"
        )
        return state

    if _matches_any(
        text,
        MAIRON_CORRECTION_PATTERNS,
    ):
        state.speech_act = "correction"
        state.intent = "correct_mairon"
        state.factuality = "requires_reconciliation"
        state.should_continue_conversation = True
        state.confidence = 0.9
        state.add_reason(
            "user appears to be correcting or challenging a previous Mairon claim"
        )
        return state

    if _matches_any(text, THANKS_PATTERNS):
        state.speech_act = "thanks"
        state.intent = "acknowledge"
        state.factuality = "none"
        state.should_recommend = False
        state.should_continue_conversation = False
        state.confidence = 0.98
        state.add_reason("gratitude/acknowledgement")
        return state

    if _matches_any(text, RECOMMENDATION_REQUEST_PATTERNS):
        state.speech_act = "question"
        state.intent = "recommendation_request"
        state.should_recommend = True
        state.should_continue_conversation = True
        state.factuality = "mixed"
        state.confidence = 0.92
        state.add_reason("explicit recommendation request")
        return state

    if _matches_any(text, OPINION_PATTERNS):
        state.speech_act = "opinion"
        state.intent = "share_opinion"
        state.should_recommend = False
        state.should_continue_conversation = True
        state.factuality = "subjective"
        state.confidence = 0.84
        state.add_reason("user is expressing an opinion or evaluation")
        return state

    if (
        (
            _is_personal_declarative_share(
                text
            )
            or _matches_any(
                text,
                DECLARATIVE_SHARE_PATTERNS,
            )
        )
        and not _matches_any(
            text,
            QUESTION_PATTERNS,
        )
    ):
        state.speech_act = "declarative_share"
        state.intent = "share_context"
        state.should_recommend = False
        state.should_continue_conversation = True
        state.factuality = "user_provided"
        state.confidence = 0.82
        state.add_reason("user is sharing context rather than asking for a solution")

        if _matches_any(text, BANTER_PATTERNS):
            state.entities["tone"] = "casual"

        return state

    if _matches_any(text, ACTION_PATTERNS):
        state.speech_act = "request_action"
        state.intent = "action_request"
        state.should_use_tools = True
        state.should_answer_directly = False
        state.factuality = "action_result"
        state.confidence = 0.78
        state.add_reason("imperative/action wording")
        return state

    if _matches_any(text, QUESTION_PATTERNS):
        state.speech_act = "question"
        state.intent = "factual_question"
        state.factuality = "requires_epistemic_routing"
        state.should_continue_conversation = True
        state.confidence = 0.72
        state.add_reason("generic question requiring later epistemic routing")
        return state

    if _matches_any(text, BANTER_PATTERNS):
        state.speech_act = "banter"
        state.intent = "casual_conversation"
        state.factuality = "none"
        state.should_continue_conversation = True
        state.confidence = 0.72
        state.add_reason("casual banter fallback")
        return state

    state.speech_act = "statement"
    state.intent = "casual_conversation"
    state.factuality = "unknown"
    state.should_continue_conversation = True
    state.should_recommend = False
    state.confidence = 0.5
    state.add_reason("generic conversational fallback")
    return state
