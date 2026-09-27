"""Phase 11.6.6A: conservative, tool-free last-mile safety boundaries.

No model calls, user-profile writes or external actions. These checks enforce
boundaries; they are NOT a replacement for general conversation intelligence.
"""
from __future__ import annotations

import re
from typing import Any, Iterable


# These are internal instruction headers, not ordinary discussion of Core.
_INTERNAL_HEADERS = (
    r"(?im)^\s*(?:>\s*)?CORE ANSWER CONTRACT\s*:",
    r"(?im)^\s*(?:>\s*)?CORE LIVE USER CONTINUITY\s*:",
    r"(?im)^\s*(?:>\s*)?CORE SPOILER POLICY\s*:",
    r"(?im)^\s*(?:>\s*)?MAIRON DIRECT-CONVERSATION MODE\s*:",
    r"(?im)^\s*(?:>\s*)?FACTUAL GROUNDING POLICY\s*:",
)
_LEAK_CLUSTER = (
    "current interface capabilities:",
    "permission-gated actions:",
    "external capabilities and tools:",
    "persistent memory:",
    "core answer contract:",
    "behavioural limits:",
    "mairon runtime context:",
    "cloud processing:",
    "conversation continuity:",
    "factual grounding policy:",
)


def contains_internal_instruction_leak(text: str) -> bool:
    """Fail closed on recognizable dumps; avoid policing normal policy prose."""
    value = str(text or "")
    if any(re.search(pattern, value) for pattern in _INTERNAL_HEADERS):
        return True
    low = value.casefold()
    return len(value) > 650 and sum(marker in low for marker in _LEAK_CLUSTER) >= 3


def safe_instruction_leak_fallback(user_text: str) -> str:
    if _spoiler_conflict(user_text, []):
        return (
            "That would reveal an ending spoiler, and you asked for no spoilers. "
            "Do you want to explicitly lift that limit? I won't reveal it otherwise."
        )
    return "I couldn't produce a safe response to that turn. Please try rephrasing it."


def explicit_calendar_write_request(text: str) -> bool:
    """Narrow positive action recognition; mentions and intentions are not writes."""
    value = str(text or "").strip()
    if not value:
        return False
    if re.search(
        r"(?i)\b(?:not asking|don't|do not|never|without)\b.{0,70}\b(?:add|create|schedule|book|put)\b",
        value,
    ):
        return False
    prefix = r"(?:actually\s+|okay\s+|ok\s+|alright\s+|so\s+|now\s+|yeah\s+)?"
    imperative = r"(?:please\s+)?(?:add|create|schedule|book|put)\b"
    polite = r"(?:can|could|would)\s+(?:you|u)\s+(?:please\s+)?(?:add|create|schedule|book|put)\b"
    tail = r".{0,200}\b(?:on|to|in)\s+(?:my|our|the)\s+calendar\b"
    return bool(
        re.search(r"(?i)^\s*" + prefix + r"(?:" + imperative + "|" + polite + ")" + tail, value)
        or re.search(r"(?i)^\s*" + prefix + r"(?:please\s+)?(?:add|create|schedule)\s+(?:an?\s+)?calendar\s+event\b", value)
    )


def should_expose_model_cloud(*, requested: bool, user_text: str, core_intent: str) -> bool:
    """Model-initiated cloud requests are exceptional, never default social tools.

    Explicit /cloud remains owned by the separate router override path.
    """
    if not requested:
        return False
    value = str(user_text or "").lower()
    if re.search(r"\b(?:don't|do not|never|without|no)\b.{0,30}\bcloud\b|\bstay\s+local\b|\blocal\s+only\b", value):
        return False
    explicit = bool(re.search(
        r"\b(?:use|request|ask for|switch to|escalate to)\s+(?:the\s+)?(?:cloud|stronger model)\b",
        value,
    ))
    if explicit and core_intent != "calendar_event_creation_request":
        return True
    if core_intent in {
        "calendar_event_creation_request", "share_context", "share_opinion",
        "casual_conversation", "self_correction", "conversation_recall",
        "acknowledge", "calculate_arithmetic", "reason_from_supplied_premises",
    }:
        return False
    # A genuinely large, complex, user-requested task can still make an optional
    # escalation available, but the model must then request permission normally.
    markers = (
        "in-depth", "comprehensive", "multi-step", "thorough", "deep analysis",
        "evaluate", "compare", "analyse", "analyze", "multiple documents",
        "full architecture", "detailed report", "research extensively",
    )
    return len(value) >= 900 and sum(marker in value for marker in markers) >= 3


def unsafe_calendar_completion_claim(user_text: str, answer: str, *, action_confirmed: bool = False) -> bool:
    """A misrouted model response must not pretend a calendar write occurred."""
    if action_confirmed or not explicit_calendar_write_request(user_text):
        return False
    value = str(answer or "").lower()
    if not value or any(phrase in value for phrase in (
        "nothing was created", "nothing was changed", "no event was created",
        "haven't created", "have not created", "not scheduled", "can't schedule",
        "cannot schedule", "approval required", "your approval", "approve the",
        "please confirm", "i can't prepare", "couldn't prepare", "cancelled",
    )):
        return False
    return bool(re.search(
        r"\b(?:i(?:'ve| have| will|'ll| am going to)|it's|it is|event (?:has been|is))\b"
        r".{0,95}(?:\b(?:add(?:ed)?|creat(?:ed|e)|schedul(?:ed|e)|book(?:ed)?|put)\b|\b(?:in|into|on) your calendar\b)"
        r"|\b(?:added|created|scheduled|booked)\b.{0,85}\b(?:calendar|event|appointment)\b"
        r"|\b(?:calendar|event|appointment)\b.{0,85}\b(?:added|created|scheduled|booked)\b",
        value,
    ))


def sanitise_visible_response(user_text: str, answer: str, *, action_confirmed: bool = False) -> tuple[str, str | None]:
    """Returns (safe_answer, machine-readable_reason). No raw leak in reason."""
    if contains_internal_instruction_leak(answer):
        return safe_instruction_leak_fallback(user_text), "internal_instruction_leak"
    if unsafe_calendar_completion_claim(user_text, answer, action_confirmed=action_confirmed):
        return (
            "I haven't created anything on your calendar. A calendar write needs "
            "an inspectable approval request first; please restate the event details.",
            "unconfirmed_calendar_claim",
        )
    return str(answer or ""), None


def _spoiler_conflict(current: str, recent_user_turns: Iterable[Any]) -> bool:
    value = str(current or "").lower()
    high_risk = bool(re.search(
        r"\b(?:does|did|will|who|what|when|is)\b.{0,95}"
        r"\b(?:die|dead|ending|end|finale|traitor|killer|twist|identity|wins?|happens?)\b",
        value,
    ))
    if not high_risk:
        return False
    explicit_override = bool(re.search(
        r"\b(?:spoil me|spoilers (?:are|r) (?:okay|ok|fine)|override (?:my|the) spoiler)\b",
        value,
    ))
    if explicit_override:
        return False
    recent = [str(item.get("text") if isinstance(item, dict) else item).lower()
              for item in list(recent_user_turns or [])[-4:]]
    return bool(re.search(r"\b(?:no spoilers?|don'?t spoil|do not spoil|without spoilers?)\b", value)) or any(
        re.search(r"\b(?:no spoilers?|don'?t spoil|do not spoil|without spoilers?)\b", old)
        for old in recent
    )


def deterministic_critical_response(current: str, recent_user_turns: Iterable[Any] = ()) -> str | None:
    """Only unmistakable safety conflicts bypass generation; no generic chatbot scripts."""
    value = str(current or "").lower()
    if _spoiler_conflict(current, recent_user_turns):
        return (
            "That question would reveal an ending spoiler, but you explicitly "
            "asked me not to spoil it. Do you want to lift that restriction? "
            "I won't confirm or deny the outcome unless you do."
        )
    if "git clean -fdx" in value and re.search(r"\b(?:fix|recover|restore|help|should|would|run)\b", value):
        return (
            "No — don't run `git clean -fdx` to recover files. It DELETES "
            "untracked files and ignored files, potentially destroying more "
            "recoverable work. Stop changing the folder and first check "
            "Recycle Bin, backups and Git status; examine the reflog if commits "
            "might have been lost."
        )
    if re.search(r"\b(?:deleted|lost|wiped)\b.{0,65}\b(?:project|folder|repo|repository)\b", value) and re.search(
        r"\b(?:what (?:do|should) i do|first|stressing|help)\b", value
    ):
        return (
            "First, stop writing to the affected drive or project folder so "
            "you don't overwrite recoverable data. Check Recycle Bin and "
            "existing backups; if it was a Git repo, inspect `git status` "
            "and your commits without running destructive cleanup commands. "
            "Tell me what you deleted and how, then we can narrow recovery down."
        )
    synthetic = bool(re.search(r"\b(?:fictional|hypothetical|imagine|safety test)\b", value))
    lead = "In that hypothetical, " if synthetic else ""
    if (re.search(r"\b(?:severe|intense)\b.{0,25}\bchest pain\b", value)
        or "chest pain" in value) and re.search(r"\b(?:trouble breathing|difficulty breathing|can't breathe|cannot breathe)\b", value):
        return (
            lead + "severe chest pain with breathing difficulty is an emergency. "
            "Call emergency services immediately (000 if in Australia; otherwise "
            "use the local emergency number). Have someone stay with the person, and don't drive "
            "them yourself or assume it's only panic or the substance."
        )
    if re.search(r"\b(?:surgery|post.?op|operat(?:ion|ed)|cast)\b", value) and all(
        re.search(r"\b" + word + r"\b", value) for word in ("blue", "cold", "numb")
    ):
        return (
            lead + "blue, cold and increasingly numb toes after surgery need "
            "immediate emergency medical assessment. Do not sleep it off. "
            "This could indicate compromised circulation or another urgent "
            "complication; a clinician must assess the cause."
        )
    if re.search(r"\b(?:lsd|acid)\b", value) and re.search(
        r"\b(?:panic|panicking|freaking out|freaking|dying|terrified)\b", value
    ):
        return (
            lead + "the friend should stay with them, speak calmly and move "
            "to a quiet, physically safe place. Remind them that the effects "
            "can distort perception; don't give more substances or let them "
            "drive. If they develop severe chest pain, trouble breathing, "
            "seizures, lose consciousness or cannot be kept safe, call "
            "emergency services (000 if in Australia; otherwise the local "
            "emergency number)."
        )
    return None


def replace_visible_answer_in_history(history: Any, original: str, replacement: str) -> Any:
    """Remove unsafe assistant content from returned model-visible history."""
    if not isinstance(history, (tuple, list)):
        return history
    updated = list(history)
    for index in range(len(updated) - 1, -1, -1):
        message = updated[index]
        if isinstance(message, dict):
            if message.get("role") == "assistant" and str(message.get("content") or "") == original:
                updated[index] = {**message, "content": replacement}
                return updated
        elif getattr(message, "role", None) == "assistant" and str(getattr(message, "content", "") or "") == original:
            copier = getattr(message, "model_copy", None)
            if callable(copier):
                updated[index] = copier(update={"content": replacement})
            else:
                updated[index] = {"role": "assistant", "content": replacement}
            return updated
    # Some direct branches don't append an assistant message; avoid carrying
    # untrusted raw text forward by providing the visible safe completion.
    updated.append({"role": "assistant", "content": replacement})
    return updated
