"""Bounded user-authored task continuation for natural multi-turn follow-ups.

This module decides only whether a turn is *about* a recent user-supplied task.
It never treats assistant prose as evidence, invents missing facts, or authorizes
an external action. Ambiguous stand-alone questions keep their existing route.
"""
from __future__ import annotations

import re
from typing import Any, Optional

PUBLIC_OR_NEW_STATE = re.compile(
    r"\b(?:look\s+(?:it\s+)?up|search\s+(?:online|the\s+web|the\s+internet)|"
    r"check\s+(?:online|the\s+web)|official\s+(?:site|docs|documentation|source)|"
    r"(?:latest|current|today|this\s+week)\s+(?:price|news|forecast|release|score)|"
    r"book\s+(?:it|this)|place\s+an?\s+order)\b",
    re.I,
)
NEW_TOPIC = re.compile(r"^\s*(?:anyway|different\s+topic|unrelated|moving\s+on|random\s+tangent|side\s+note)\b", re.I)
FOLLOWUP_CUE = re.compile(
    r"\b(?:\bwhy\b.{0,65}\b(?:that|it|this|python|split|scaler|list)\b|"
    r"what\s+does\s+that\b|what\s+(?:would|should)\s+(?:i|we)\s+do\s+(?:then|now)|"
    r"(?:explain|summari[sz]e)\s+(?:the\s+)?(?:whole\s+thing|that|it)\b|"
    r"(?:narrow|limit|tailor)\s+it\b|"
    r"does\s+(?:it|that)\s+(?:fit|work|make\s+sense)\b|"
    r"what\s+do\s+(?:u|you)\s+need\s+from\s+me\b|"
    r"\b(?:rule\s+out|same\s+thing|still\s+be|so\s+what|and\s+if)\b|"
    r"\b(?:one\s+actual\s+useful\s+next\s+step|give\s+me\s+one\s+concrete\s+skill)\b)",
    re.I,
)
CORRECTION_WITH_QUESTION = re.compile(
    r"\b(?:scratch\s+that|correction\s*[:,-]|(?:wait|actually)\s+no)\b", re.I
)
BACK_REFERENCE = re.compile(
    r"\b(?:it|that|this|those|them|the\s+whole\s+thing|now|then|instead|"
    r"same|actually|again|so\s+what|still)\b", re.I
)
QUESTION_SHAPE = re.compile(
    r"(?:\?|\b(?:why|what|how|does|do|can|should|is|are|explain|narrow)\b)", re.I
)
EXTERNAL_ACTION = re.compile(
    r"\b(?:add|schedule|create|put)\b.{0,95}\b(?:calendar|event|meeting|appointment)\b|"
    r"\b(?:delete|send|buy|purchase|open|launch)\s+(?:the|my|an?|it)\b",
    re.I,
)
STOP_WORDS = {
    "about", "after", "again", "also", "and", "anyway", "before", "between",
    "bro", "bruh", "could", "does", "dont", "from", "have", "into", "just",
    "like", "more", "need", "okay", "only", "please", "really", "that", "them",
    "then", "there", "these", "thing", "this", "what", "when", "where", "which",
    "while", "with", "would", "your", "youre", "hypothetically", "now", "first",
    "same", "last", "want", "give", "make", "tell", "should", "think",
}


def _words(text: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z]{4,}", str(text or "").lower())
        if word not in STOP_WORDS
    }


def bounded_recent_user_turns(conversation_state: Any, *, limit: int = 4) -> list[dict]:
    """Return a short, chronological USER-only excerpt, never model answers."""
    candidates = getattr(conversation_state, "recent_user_turns", None) or []
    result = []
    for item in list(candidates)[-max(1, min(limit, 5)):]:
        if not isinstance(item, dict):
            continue
        message = str(item.get("text") or "").strip()
        if message:
            result.append({"text": message[:1000], "intent": str(item.get("intent") or "")})
    return result


def classify_user_grounded_followup(
    user_text: str,
    previous_user_turns: list[dict],
) -> Optional[list[dict]]:
    """Identify explicit task continuations that must not trigger a new web search.

    Only confident discourse dependencies qualify. The current message remains
    intact; supplied context is used for solving the requested task, not for
    treating any assistant's earlier answer as factual evidence.
    """
    text = str(user_text or "").strip()
    recent = [t for t in (previous_user_turns or []) if str(t.get("text") or "").strip()]
    if not text or not recent:
        return None
    if NEW_TOPIC.search(text) or PUBLIC_OR_NEW_STATE.search(text) or EXTERNAL_ACTION.search(text):
        return None
    previous = recent[-1]
    previous_text = str(previous.get("text") or "")
    # No automatic context inheritance across overt current/public lookup tasks.
    if re.search(r"\b(?:current|latest|news|forecast|stock\s+price)\b", text, re.I):
        return None
    lower = text.lower()
    has_question = bool(QUESTION_SHAPE.search(lower))
    if not has_question:
        return None
    direct_cue = bool(FOLLOWUP_CUE.search(lower))
    corrected_question = bool(CORRECTION_WITH_QUESTION.search(lower) and "?" in lower)
    informal_conclusion = bool(re.search(
        r"^\s*so+\s+(?:i|we)\s+(?:should|shouldn'?t|would|wouldn'?t|can|can't)\b",
        lower,
    ) and "?" in lower)
    if informal_conclusion and previous.get("intent") in {
        "factual_question", "reason_from_supplied_premises",
        "calculate_arithmetic", "consequential_advice",
    }:
        return recent[-4:]
    back_reference = bool(BACK_REFERENCE.search(lower))
    topical_overlap = bool(_words(lower) & _words(previous_text))
    # An explicit correction-and-question can refer to earlier numeric task
    # state, but should not turn a plain correction into a second task.
    if corrected_question:
        return recent[-4:]
    if direct_cue and (back_reference or topical_overlap or previous.get("intent") in {
        "factual_question", "reason_from_supplied_premises", "share_opinion", "casual_conversation",
    }):
        return recent[-4:]
    # 'WHAT why didn't python ...' carries the actual previous subject, while
    # 'anyway why does my new monitor...' should remain a fresh question.
    if ("?" in lower and topical_overlap and (back_reference or re.search(r"\b(?:why|how|what)\b", lower))):
        return recent[-4:]
    return None


def build_bounded_task_instruction(turn: Any) -> Optional[str]:
    """Small model-facing packet for an already-classified user task continuation."""
    entities = getattr(turn, "entities", None) or {}
    if entities.get("_user_grounded_followup") != "true":
        return None
    history = str(entities.get("_user_task_history") or "").strip()
    if not history:
        return None
    return (
        "CORE USER-GROUNDED TASK CONTINUATION:\n"
        "Oliver is continuing or revising a task from the USER statements below. "
        "They are the source for previous constraints and questions. Do not search "
        "the web for Oliver's own hypothetical figures, previously supplied code, "
        "or private observations. Use stable technical knowledge when necessary.\n"
        "If the current question proposes a conclusion or an expense based on the "
        "previous observations, say explicitly whether the observation justifies "
        "that conclusion, and explain why. A joke must not replace a yes/no answer.\n"
        "Answer his current actual request, not just his correction, slang, tone, "
        "or demand for brevity. If asked why, explain why; if asked to recalculate, "
        "recalculate using the LATEST corrected inputs. If asked to shorten a prior "
        "explanation, retain the substance. If the supplied information is genuinely "
        "insufficient, identify precisely what's missing; don't make up figures.\n"
        "Do not treat previous Mairon claims as evidence. Avoid unrelated jokes.\n"
        "PRIOR USER TURNS (chronological):\n" + history
    )
