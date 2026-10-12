"""Preserve opinion ownership in an explicit USER-stance acknowledgement.

This is a bounded speech-act adapter, not an opinion ledger or truth source.
The existing ledger remains the only supplied authority for an independently
accepted assistant stance. Neither a matching USER opinion nor assistant
dialogue is promoted into that authority by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Mapping, Optional, Tuple

from core.answer_contract_runtime import coerce_answer_contract_runtime


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("’", "'").replace("‘", "'")).strip()


def _unquoted(value: str) -> str:
    # Preserve offsets. An apostrophe inside a contraction is not a quotation.
    return re.sub(r'"[^"\n]*"|“[^”\n]*”|(?<!\w)\'[^\'\n]*\'(?!\w)',
                  lambda match: " " * len(match.group()), value)


_STANCE = re.compile(
    r"\b(?P<marker>"
    r"i\s+(?:(?:still|now|already|also|really|personally|honestly|actually)\s+)?"
    r"(?:(?:do\s+not|don't)\s+)?(?:(?:really|actually)\s+)?"
    r"(?:think|reckon|believe|feel|consider|prefer|like|love|hate|agree|disagree)"
    r"|i(?:'d|\s+would)\s+(?:say|pick|choose|prefer)"
    r"|(?:my\s+(?:take|opinion|view|position|preference)\s+(?:is|remains))"
    r"|in\s+my\s+opinion|for\s+me\s*[,—:])\s*",
    re.I,
)
_ACK_REQUEST = re.compile(
    r"\b(?:remember|note|acknowledge)\s+(?:(?:for|during)\s+(?:this|our|the)\s+"
    r"(?:chat|conversation|discussion)\s*[,;:]?\s*)?(?:that\s+)?"
    r"|\bkeep\s+(?:it|this|that|in\s+mind)\s+(?:in\s+mind\s*)?(?:that\s+)?",
    re.I,
)


def _directive_acknowledgement(value: str) -> bool:
    """Do not turn reported, negated or conditional remembering into a request."""
    for match in _ACK_REQUEST.finditer(value):
        prefix = re.split(r"[.!?](?=\s|$)|;", value[:match.start()])[-1]
        if re.search(r"\b(?:if|unless|assuming|suppose|whether)\b|"
                     r"\b(?:i|we|he|she|they)\s+(?:said|told|asked|remembered|noted)\b", prefix, re.I):
            continue
        # A trailing imperative can follow the opinion itself. Keep the
        # conditional/reporting scope check above before isolating its clause.
        prefix = re.split(r",|\band\s+", prefix, flags=re.I)[-1].lstrip()
        if re.fullmatch(
            r"(?:(?:okay|ok|well|actually|correction|update)\s*[,!:—-]?\s*)*"
            r"(?:(?:for|during)\s+(?:this|our|the)\s+(?:chat|conversation|discussion)\s*[,;:]?\s*)?"
            r"(?:(?:please|just)\s+)*"
            r"(?:(?:can|could|would|will)\s+(?:you|u)\s+(?:please\s+)?"
            r"|i\s+(?:want|need)\s+you\s+to\s+|i(?:'d|\s+would)\s+like\s+you\s+to\s+)?",
            prefix, re.I,
        ):
            return True
    return False
_OWN_OPINION_REQUEST = re.compile(
    r"\b(?:what|which|why|how)\s+(?:do|would|did)\s+you\s+"
    r"(?:think|reckon|feel|prefer|believe|choose|pick)\b"
    r"|\b(?:your\s+(?:own\s+)?(?:take|opinion|view)|do\s+you\s+(?:agree|disagree))\b"
    r"|\b(?:defend|justify|explain|give|argue)\s+(?:me\s+)?(?:your|a|an)\b",
    re.I,
)


@dataclass(frozen=True)
class StanceProposition:
    """A grammatical stance and its bounded content; no factual authority."""
    kind: str
    content: str


@dataclass(frozen=True)
class StanceOwnershipFrame:
    """Transient ownership boundary for this acknowledgement only."""
    user_stances: Tuple[StanceProposition, ...]
    accepted_assistant_stances: Tuple[StanceProposition, ...] = ()
    acknowledgement_only: bool = True


def _key(value: str) -> str:
    value = _text(value).strip(" \"'“”.,;:!?").casefold()
    value = re.sub(r"^(?:that\s+)", "", value)
    value = re.sub(r"\s+(?:for|during|in)\s+(?:this|our|the)\s+"
                   r"(?:chat|conversation|discussion)\s*$", "", value)
    return value


def _stance_kind(marker: str) -> str:
    marker = _text(marker).casefold()
    negative = bool(re.search(r"\b(?:not|don't)\b", marker))
    verb = next((word for word in reversed(marker.split()) if word in {
        "think", "reckon", "believe", "feel", "consider", "prefer", "like",
        "love", "hate", "agree", "disagree",
        "say", "pick", "choose",
    }), "judgement")
    kind = "judgement" if verb in {"think", "reckon", "believe", "feel", "consider"} else verb
    return ("negative:" if negative else "positive:") + kind


def _stances(value: Any) -> Tuple[StanceProposition, ...]:
    text = _text(value)
    masked = _unquoted(text)
    result = []
    for match in _STANCE.finditer(masked):
        prefix = re.split(r"[.!?](?=\s|$)|;|\b(?:but|however)\b", masked[:match.start()], flags=re.I)[-1]
        # A conditional or questioned belief does not assert an owned stance.
        if re.search(r"\b(?:if|unless|suppose|assuming|whether)\b", prefix, re.I):
            continue
        tail = text[match.end():]
        content = re.split(r"[.!?](?=\s|$)|;|\s+\b(?:but|however)\b", tail, maxsplit=1, flags=re.I)[0]
        if tail[len(content):].startswith("?"):
            continue
        key = _key(content)
        if not key or len(key) > 400 or len(key.split()) > 55:
            continue
        # These forms describe what the USER said rather than adopting its
        # proposition. Their USER-fact entailment remains the existing verifier's job.
        if re.match(r"(?:that\s+)?you\s+(?:mean|said|told|reckon|think|prefer|believe|feel)\b", key, re.I):
            continue
        item = StanceProposition(_stance_kind(match.group("marker")), key)
        if item not in result:
            result.append(item)
    return tuple(result)


def is_user_stance_acknowledgement(user_input: Any, core_answer_contract: Any = None) -> bool:
    """Recognise a bounded acknowledgement request, not ordinary debate.

    With no contract this stricter explicit-request grammar is used by existing
    ledger ingress/recovery and continuity guards. It cannot create state.
    """
    value = _text(user_input)
    masked = _unquoted(value)
    if not _stances(value) or _OWN_OPINION_REQUEST.search(masked):
        return False
    explicit = _directive_acknowledgement(masked)
    if core_answer_contract is None:
        return explicit
    runtime = coerce_answer_contract_runtime(core_answer_contract)
    if runtime is None:
        return False
    if runtime.intent not in {"share_opinion", "acknowledge", "share_context", "self_correction", "casual_conversation"}:
        return False
    if runtime.task not in {"respond", runtime.intent}:
        return False
    if runtime.authority not in {"user_turn", "conversation", "live_conversation", "user_turn_and_live_conversation"}:
        return False
    if runtime.epistemic_mode not in {"conversation", "subjective", "user_provided", "self_correction", "social_conversation",
                                    "user_context", "user_turn", "user_authored_context", "live_conversation"}:
        return False
    if str((runtime.metadata or {}).get("debate_continuation") or "").lower() in {"1", "true", "yes"}:
        return False
    return explicit or runtime.intent in {"acknowledge", "self_correction"} or runtime.speech_act in {
        "acknowledgement", "acknowledge", "user_stance_acknowledgement",
    }


def build_stance_ownership_frame(
    user_input: Any, core_answer_contract: Any, *, accepted_opinion_entry: Any = None,
) -> Optional[StanceOwnershipFrame]:
    """The caller supplies a prior accepted ledger entry, never model history.

    Matching a USER opinion grants no assistant opinion. Existing accepted
    assistant wording only records that assistant stance, never factual truth.
    """
    if coerce_answer_contract_runtime(core_answer_contract) is None or not is_user_stance_acknowledgement(user_input, core_answer_contract):
        return None
    own = ()
    if isinstance(accepted_opinion_entry, Mapping):
        own = _stances(accepted_opinion_entry.get("stance_text"))
        # The existing ledger's structured side can establish a preference
        # even when its accepted rendering used no first-person marker.
        if accepted_opinion_entry.get("kind") == "pairwise_comparison":
            position = str(accepted_opinion_entry.get("position") or "").lower()
            left = _key(accepted_opinion_entry.get("left"))
            right = _key(accepted_opinion_entry.get("right"))
            if position in {"left", "right"} and left and right:
                preferred, other = (left, right) if position == "left" else (right, left)
                item = StanceProposition("positive:prefer", preferred + " over " + other)
                if item not in own:
                    own += (item,)
    return StanceOwnershipFrame(_stances(user_input), own)


def find_stance_ownership_violations(draft: Any, *, frame: Optional[StanceOwnershipFrame]) -> list[str]:
    """A global semantic positive cannot transfer USER stance ownership."""
    if frame is None:
        return []
    introduced = [item for item in _stances(draft) if item not in frame.accepted_assistant_stances]
    if introduced:
        return ["USER-stance acknowledgement introduced an unestablished assistant stance"]
    return []


def render_stance_ownership_instruction(frame: Optional[StanceOwnershipFrame]) -> Optional[str]:
    if frame is None:
        return None
    return "\n".join([
        "CORE STANCE OWNERSHIP — USER ACKNOWLEDGEMENT:",
        "- This turn acknowledges the USER's opinion; it does not ask you to adopt or debate it.",
        "- Preserve the owner and perspective. USER 'I reckon/prefer X' becomes 'You reckon/prefer X', "
        "an attributed paraphrase, or a brief acknowledgement. It does not become your 'I reckon/prefer X'.",
        "- An existing independently accepted assistant stance remains separate and supplies no factual truth. "
        "Do not establish, revise, persist or recover an assistant opinion merely by acknowledging the USER.",
        "USER-OWNED STANCE DATA: " + json.dumps([item.__dict__ for item in frame.user_stances], ensure_ascii=False),
        "SEPARATE ACCEPTED ASSISTANT STANCE DATA: " + json.dumps(
            [item.__dict__ for item in frame.accepted_assistant_stances], ensure_ascii=False),
    ])
