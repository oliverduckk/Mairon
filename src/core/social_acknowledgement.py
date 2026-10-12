"""Tiny Core acknowledgements after an otherwise safe social turn is empty.

This helper does not infer actions, answer factual questions, or repair model
prose. The caller must first exhaust its existing generation budget and confirm
that no visible candidate and no tool activity occurred. The turn contract,
never candidate text or assistant history, supplies the non-action authority.
"""
from __future__ import annotations

import re
from typing import Any

from core.answer_contract_runtime import coerce_answer_contract_runtime


_SOCIAL_INTENTS = frozenset({
    "share_context", "acknowledge", "casual_conversation", "self_correction",
})
_SOCIAL_AUTHORITIES = frozenset({
    "user_turn", "user_turn_and_live_conversation", "live_conversation",
    "conversation", "conversation_model",
})
_SOCIAL_MODES = frozenset({
    "user_provided", "social_conversation", "conversation", "self_correction",
})
_NON_ACTION_SPEECH_ACTS = frozenset({
    "unknown", "declarative_share", "social_question", "thanks",
    "acknowledgement", "acknowledge", "self_correction", "correction", "banter",
    "statement",
})
_DEFERRAL = re.compile(
    r"\b(?:not|never)\s+(?:asking|requesting|instructing)\s+(?:you|u)\b"
    r"|\b(?:maybe|perhaps|possibly)\s+(?:later|another\s+time)\b"
    r"|\bnot\s+(?:now|yet)\b",
    re.IGNORECASE,
)


def build_empty_social_acknowledgement(
    *, user_input: str, contract: Any, tool_activity: bool = False,
) -> str | None:
    """Acknowledge a known non-action micro-act without adding world facts.

    This deliberately declines contracts with factual or result obligations.
    It returns no action proposal, persistence claim, reminder, or detail copied
    from an uncertain interpretation. It has no model, tool, or state access.
    """
    if tool_activity or not isinstance(user_input, str) or not user_input.strip():
        return None
    try:
        runtime = coerce_answer_contract_runtime(contract)
        if runtime is None or runtime.intent not in _SOCIAL_INTENTS:
            return None
        if runtime.task not in {"respond", runtime.intent}:
            return None
        if runtime.speech_act not in _NON_ACTION_SPEECH_ACTS:
            return None
        if runtime.authority not in _SOCIAL_AUTHORITIES:
            return None
        if runtime.epistemic_mode not in _SOCIAL_MODES:
            return None
        if (runtime.allow_new_factual_claims or runtime.allow_recommendations
                or runtime.required_claims or runtime.verified_evidence_claims):
            return None
    except Exception:
        return None

    if runtime.intent == "acknowledge" and runtime.speech_act == "thanks":
        return "You're welcome."
    if _DEFERRAL.search(user_input):
        return "Got it — no action for now."
    return "Got it."
