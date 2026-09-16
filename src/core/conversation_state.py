import re
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

from core.conversational_research import (
    looks_like_public_external_context,
)
from core.debate_state import (
    extract_pairwise_comparison,
    looks_like_debate_continuation,
    pairwise_subject_from_hint,
)

from core.turn_state import TurnState


PRONOUN_PATTERN = re.compile(
    r"\b("
    r"it|its|that|this|"
    r"they|them|their|theirs|those|these|"
    r"he|him|his|she|her|hers"
    r")\b",
    flags=re.IGNORECASE,
)


CONTEXTUAL_CONNECTIVE_PATTERN = re.compile(
    r"^\s*(?:"
    r"and|but|so|then|"
    r"what\s+about|how\s+about|"
    r"same|the\s+same|"
    r"do\s+you\s+think|would\s+you\s+say|"
    r"what\s+do\s+you\s+think"
    r")\b",
    flags=re.IGNORECASE,
)


TOPIC_BOUNDARY_PATTERN = re.compile(
    r"^\s*(?:"
    r"anyway|moving\s+on|different\s+topic|"
    r"unrelated(?:ly)?|side\s+note"
    r")\b",
    flags=re.IGNORECASE,
)


CONTEXTUAL_OPINION_PATTERN = re.compile(
    r"(?:"
    r"^\s*what\s+do\s+you\s+think\b|"
    r"\b(?:do|would)\s+you\s+(?:think|reckon|say)\b"
    r")",
    flags=re.IGNORECASE,
)


CONTEXTUAL_EVALUATION_PATTERN = re.compile(
    r"\b(?:"
    r"well|good|bad|better|worse|best|worst|"
    r"right|wrong|fair|unfair|worth|"
    r"effective|ineffective|handled|handling|"
    r"like|prefer|preferred|"
    r"overrated|underrated|"
    r"stronger|weaker|smart|stupid|"
    r"reasonable|unreasonable|justified"
    r")\b",
    flags=re.IGNORECASE,
)


def _infer_immediate_user_subject(
    text: str,
) -> Optional[str]:
    """
    Extract a conservative subject hint from a user-authored possessive phrase.

    This is intentionally tiny and generic. It is not named-entity recognition
    and it never calls the model. Its purpose is to preserve obvious discourse
    anchors such as:

        "Horikita's handling ..." -> "Horikita"
        "Walter White's decision ..." -> "Walter White"

    Personal/determiner-led phrases such as "my monitor's ..." are not promoted
    into a named subject by this helper.
    """

    raw = str(
        text
        or ""
    ).strip()

    if not raw:
        return None

    comparison = extract_pairwise_comparison(
        raw
    )

    if comparison:
        return comparison[
            "label"
        ]

    match = re.match(
        r"^\s*("
        r"[A-Za-z][A-Za-z0-9_.-]*"
        r"(?:\s+[A-Za-z][A-Za-z0-9_.-]*){0,3}"
        r")[’']s\b",
        raw,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    value = re.sub(
        r"\s+",
        " ",
        match.group(1).strip(),
    )

    first = (
        value.split(
            " ",
            1,
        )[
            0
        ].lower()
    )

    if first in {
        "my",
        "our",
        "your",
        "his",
        "her",
        "its",
        "their",
        "the",
        "this",
        "that",
    }:
        return None

    return value[:120] or None


def _looks_like_contextual_opinion_question(
    text: str,
) -> bool:
    """
    Distinguish an evaluative conversational follow-up from a factual lookup.

    "Do you think she handled it well?" is an opinion/judgement continuation.
    "How old is he?" remains factual and can still require public authority.
    """

    value = str(
        text
        or ""
    ).strip()

    if not value:
        return False

    if re.match(
        r"^\s*what\s+do\s+you\s+think\s*[?.!]*\s*$",
        value,
        flags=re.IGNORECASE,
    ):
        return True

    return bool(
        CONTEXTUAL_OPINION_PATTERN.search(
            value
        )
        and CONTEXTUAL_EVALUATION_PATTERN.search(
            value
        )
    )


def build_live_user_continuity_instruction(
    turn: TurnState,
) -> Optional[str]:
    """
    Build a compact user-authored context packet for the current model turn.

    The packet is interpretation context, not independent public evidence. It
    contains no prior assistant prose and therefore cannot make an old Mairon
    hallucination authoritative.
    """

    if turn is None:
        return None

    entities = (
        getattr(
            turn,
            "entities",
            {},
        )
        or {}
    )

    previous_text = str(
        entities.get(
            "_conversation_context_user_text",
            "",
        )
        or ""
    ).strip()

    if not previous_text:
        return None

    previous_text = previous_text[
        :1800
    ]

    previous_intent = str(
        entities.get(
            "_conversation_context_intent",
            "",
        )
        or ""
    ).strip()

    referents = (
        getattr(
            turn,
            "resolved_referents",
            {},
        )
        or {}
    )

    referent_lines = []

    for key, value in referents.items():
        key_value = str(
            key
            or ""
        ).strip()

        referent_value = str(
            value
            or ""
        ).strip()

        if (
            not key_value
            or not referent_value
        ):
            continue

        referent_lines.append(
            "- "
            + key_value
            + " -> "
            + referent_value[
                :240
            ]
        )

    lines = [
        "CORE LIVE USER CONTINUITY:",
        "- Oliver's current message depends on the immediately preceding "
        "USER-authored turn below.",
        "- Use it to resolve pronouns, shorthand, preferences, constraints, "
        "and the conversational topic.",
        "- It is authoritative only for what Oliver said, not for external "
        "facts about the world.",
        "- Do not invent missing details and do not treat prior Mairon prose "
        "as evidence.",
        "- If the current turn asks for a recommendation, preserve relevant "
        "constraints Oliver stated in that previous turn.",
        "",
        "PREVIOUS OLIVER TURN:",
        previous_text,
    ]

    if previous_intent:
        lines.extend([
            "",
            "PREVIOUS TURN INTENT:",
            previous_intent,
        ])

    if referent_lines:
        lines.extend([
            "",
            "CORE-RESOLVED REFERENTS:",
            *referent_lines,
        ])

    return "\n".join(
        lines
    )


def _normalise_email_referent_text(
    value: Any,
) -> str:
    text = str(
        value
        or ""
    ).lower()

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


@dataclass
class ConversationState:
    """
    Short-lived active conversational state.

    Generic conversational state and domain-specific working referents are
    intentionally separate.

    Example:
        Oliver -> "Did I get an email from PayPal yesterday?"
        Core   -> targeted Gmail result with message_id
        Oliver -> asks for an inbox review
        Oliver -> "What did that PayPal email say?"

    The inbox review may become the generic active intent, but it must not
    destroy the still-valid specific PayPal Gmail referent.
    """

    active_subject: Optional[str] = None
    active_intent: Optional[str] = None
    active_entities: Dict[str, str] = field(default_factory=dict)
    pending_question: Optional[str] = None
    pending_action: Optional[str] = None
    recent_subjects: List[str] = field(default_factory=list)

    # Phase 11.2.1 — bounded USER-authored immediate discourse state.
    #
    # This is not long-term memory and contains no assistant prose. It exists so
    # a new turn can be interpreted against what Oliver literally just said
    # before epistemic routing decides whether web/tool authority is required.
    recent_user_turns: List[
        Dict[str, Any]
    ] = field(
        default_factory=list
    )

    # Domain-specific short-lived Gmail working state.
    #
    # Each entry records one targeted email search and the verified message
    # summaries returned by Core. This is session state, not long-term memory.
    recent_email_referents: List[
        Dict[str, Any]
    ] = field(
        default_factory=list
    )

    # Desktop working referent survives unrelated social/banter turns.
    active_desktop_target: Optional[str] = None
    recent_desktop_targets: List[str] = field(
        default_factory=list
    )

    # Trusted browser-site working referent.
    #
    # Enables:
    #   "open YouTube" -> "search for Tame Impala"
    # without treating arbitrary previous assistant prose as authority.
    active_browser_site: Optional[str] = None
    recent_browser_sites: List[str] = field(
        default_factory=list
    )

    # Local-file working referent.
    #
    # Only a unique Core-verified approved path is stored here. Prior assistant
    # prose never becomes file authority.
    active_local_file_path: Optional[str] = None
    active_local_file_name: Optional[str] = None
    active_local_file_candidates: List[Dict[str, Any]] = field(
        default_factory=list
    )
    active_local_file_pending_action: Optional[str] = None

    # Keep the last Steam-game action separate from desktop-app referents.
    # Until game close/control is implemented, this prevents "close it" from
    # accidentally targeting an older desktop app after a game launch.
    active_steam_game_title: Optional[str] = None
    active_steam_game_alias_query: Optional[str] = None
    active_steam_game_candidates: List[Dict[str, Any]] = field(
        default_factory=list
    )

    def remember_subject(self, subject: Optional[str]) -> None:
        value = str(subject or "").strip()

        if not value:
            return

        self.active_subject = value

        self.recent_subjects = [
            item
            for item in self.recent_subjects
            if item != value
        ]

        self.recent_subjects.insert(
            0,
            value,
        )

        self.recent_subjects = (
            self.recent_subjects[:8]
        )

    def latest_user_turn(
        self,
    ) -> Optional[Dict[str, Any]]:
        if not self.recent_user_turns:
            return None

        return dict(
            self.recent_user_turns[
                -1
            ]
        )

    def remember_user_turn(
        self,
        turn: TurnState,
    ) -> None:
        """
        Preserve a compact record of Oliver's immediately recent turns.

        Only user-authored wording plus Core classification metadata is stored.
        Assistant answers are deliberately excluded.
        """

        if turn is None:
            return

        raw_text = str(
            getattr(
                turn,
                "raw_text",
                "",
            )
            or ""
        ).strip()

        if not raw_text:
            return

        raw_text = raw_text[
            :1800
        ]

        subject = str(
            getattr(
                turn,
                "subject",
                "",
            )
            or ""
        ).strip()

        if not subject:
            subject = (
                _infer_immediate_user_subject(
                    raw_text
                )
                or ""
            )

        item = {
            "text": raw_text,
            "intent": str(
                getattr(
                    turn,
                    "intent",
                    "",
                )
                or ""
            ).strip(),
            "speech_act": str(
                getattr(
                    turn,
                    "speech_act",
                    "",
                )
                or ""
            ).strip(),
            "subject": subject[
                :120
            ],
        }

        self.recent_user_turns.append(
            item
        )

        self.recent_user_turns = (
            self.recent_user_turns[
                -8:
            ]
        )

    def _generic_turn_depends_on_immediate_user_context(
        self,
        turn: TurnState,
        pronouns: List[str],
    ) -> bool:
        if turn is None:
            return False

        if getattr(
            turn,
            "intent",
            None,
        ) not in {
            "factual_question",
            "share_opinion",
            "share_context",
            "casual_conversation",
            "recommendation_request",
            "acknowledge",
            "correct_mairon",
            "self_correction",
        }:
            return False

        if not self.recent_user_turns:
            return False

        text = str(
            getattr(
                turn,
                "raw_text",
                "",
            )
            or ""
        )

        # An explicit pronoun/deictic still wins because it necessarily points
        # somewhere, even if Oliver starts with "anyway". But a bare discourse
        # reset such as "anyway why does my monitor flicker?" is a topic break,
        # not permission to inject the previous anime/media turn.
        if pronouns:
            return True

        if TOPIC_BOUNDARY_PATTERN.search(
            text
        ):
            return False

        # Explicit debate challenges such as "defend your take" point back to
        # the active comparison even when they contain no pronoun or connective.
        # This is discourse continuity, not factual authority.
        if (
            looks_like_debate_continuation(
                text
            )
            and (
                pairwise_subject_from_hint(
                    self.active_subject
                )
                or extract_pairwise_comparison(
                    (
                        self.latest_user_turn()
                        or {}
                    ).get(
                        "text",
                        "",
                    )
                )
            )
        ):
            return True

        if CONTEXTUAL_CONNECTIVE_PATTERN.search(
            text
        ):
            return True

        # "what should I watch then?" and similar recommendation continuations
        # may contain the backward pointer later in the sentence.
        if (
            getattr(
                turn,
                "intent",
                None,
            )
            == "recommendation_request"
            and re.search(
                r"\b(?:then|instead|one|ones|that|those|this|these)\b",
                text,
                flags=re.IGNORECASE,
            )
        ):
            return True

        return False

    def update_from_turn(self, turn: TurnState) -> None:
        subject = str(
            turn.subject
            or ""
        ).strip()

        if not subject:
            subject = (
                _infer_immediate_user_subject(
                    turn.raw_text
                )
                or ""
            )

            if subject:
                turn.subject = subject

        if subject:
            self.remember_subject(
                subject
            )

        if turn.intent:
            self.active_intent = (
                turn.intent
            )

        if turn.entities:
            for key, value in (
                turn.entities.items()
            ):
                if value is None:
                    continue

                key_value = str(
                    key
                )

                # Underscore-prefixed entities are ephemeral interpretation
                # context for the current turn. Do not promote them into the
                # generic active entity store or persisted referent authority.
                if key_value.startswith(
                    "_"
                ):
                    continue

                self.active_entities[
                    key_value
                ] = str(value)

        if turn.requested_action:
            self.pending_action = (
                turn.requested_action
            )

        if turn.speech_act == "question":
            self.pending_question = (
                turn.raw_text
            )

        if (
            turn.intent
            in {
                "launch_application",
                "close_application",
                "focus_application",
            }
        ):
            target_id = str(
                turn.entities.get(
                    "app_name",
                    "",
                )
                or ""
            ).strip().lower()

            if target_id:
                self.remember_desktop_target(
                    target_id
                )

        elif turn.intent in {
            "browser_search",
            "browser_open",
        }:
            self.remember_desktop_target(
                "chrome"
            )

            site_id = str(
                turn.entities.get(
                    "browser_site",
                    "",
                )
                or ""
            ).strip().lower()

            if site_id:
                self.remember_browser_site(
                    site_id
                )

        elif turn.intent in {
            "find_local_file",
            "open_local_file",
            "open_local_folder",
        }:
            path = str(
                turn.entities.get(
                    "local_file_path",
                    "",
                )
                or ""
            ).strip()

            name = str(
                turn.entities.get(
                    "local_file_name",
                    "",
                )
                or ""
            ).strip()

            if path:
                self.remember_local_file(
                    path=path,
                    name=name,
                )

        elif turn.intent == "launch_steam_game":
            self.active_desktop_target = None

            self.active_steam_game_title = str(
                turn.entities.get(
                    "steam_game_title",
                    "",
                )
                or ""
            ).strip() or None

        self.remember_user_turn(
            turn
        )

    def resolve_email_message_selection(
        self,
        selector: str,
        target: Optional[str] = None,
        allow_bare: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve a positional/recency selector against verified Gmail candidates.

        Authority is the stored Gmail result set and message_id values. Prior
        assistant prose is never parsed back into selection authority.
        """

        context = self.find_email_referent(
            target=target,
            require_message=True,
            allow_bare=allow_bare,
        )

        if not context:
            return None

        messages = list(
            context.get(
                "messages",
                [],
            )
            or []
        )

        if not messages:
            return None

        selector_value = str(
            selector
            or ""
        ).strip().lower()

        selector_value = " ".join(
            selector_value.split()
        )

        selected = None

        if selector_value in {
            "latest",
            "newest",
            "most recent",
            "recent",
        }:
            dated = []

            for index, message in enumerate(
                messages
            ):
                raw_date = str(
                    message.get(
                        "date",
                        "",
                    )
                    or ""
                ).strip()

                parsed = None

                if raw_date:
                    try:
                        parsed = parsedate_to_datetime(
                            raw_date
                        )
                    except Exception:
                        parsed = None

                dated.append(
                    (
                        parsed,
                        -index,
                        message,
                    )
                )

            valid = [
                item
                for item in dated
                if item[
                    0
                ] is not None
            ]

            if valid:
                valid.sort(
                    key=lambda item: (
                        item[
                            0
                        ],
                        item[
                            1
                        ],
                    ),
                    reverse=True,
                )

                selected = valid[
                    0
                ][
                    2
                ]

            else:
                # Gmail search results are already returned newest-first.
                selected = messages[
                    0
                ]

        else:
            ordinal_mapping = {
                "first": 0,
                "1st": 0,
                "one": 0,
                "second": 1,
                "2nd": 1,
                "two": 1,
                "third": 2,
                "3rd": 2,
                "three": 2,
                "fourth": 3,
                "4th": 3,
                "four": 3,
            }

            index = ordinal_mapping.get(
                selector_value
            )

            if (
                index is not None
                and 0 <= index < len(
                    messages
                )
            ):
                selected = messages[
                    index
                ]

        if not selected:
            return None

        result = dict(
            selected
        )

        result[
            "search_text"
        ] = context.get(
            "search_text"
        )

        result[
            "time_scope"
        ] = context.get(
            "time_scope"
        )

        result[
            "days"
        ] = context.get(
            "days"
        )

        return result

    # --------------------------------------------------
    # Desktop-specific working referent
    # --------------------------------------------------

    def remember_desktop_target(
        self,
        target_id: str,
    ) -> None:
        value = str(
            target_id
            or ""
        ).strip().lower()

        if not value:
            return

        self.active_desktop_target = value
        self.active_steam_game_title = None

        self.recent_desktop_targets = [
            item
            for item in self.recent_desktop_targets
            if item != value
        ]

        self.recent_desktop_targets.insert(
            0,
            value,
        )

        self.recent_desktop_targets = (
            self.recent_desktop_targets[:8]
        )

    # --------------------------------------------------
    # Steam-game ambiguity working state
    # --------------------------------------------------

    def remember_steam_game_candidates(
        self,
        alias_query: str,
        candidates: List[Dict[str, Any]],
    ) -> None:
        query = str(
            alias_query
            or ""
        ).strip()

        cleaned = []

        for candidate in list(
            candidates
            or []
        )[:3]:
            if not isinstance(
                candidate,
                dict,
            ):
                continue

            appid = str(
                candidate.get(
                    "appid",
                    "",
                )
                or ""
            ).strip()

            name = str(
                candidate.get(
                    "name",
                    "",
                )
                or ""
            ).strip()

            if (
                not appid.isdigit()
                or not name
            ):
                continue

            cleaned.append({
                "appid": appid,
                "name": name,
            })

        self.active_steam_game_alias_query = (
            query
            or None
        )
        self.active_steam_game_candidates = cleaned

    def clear_steam_game_candidates(
        self,
    ) -> None:
        self.active_steam_game_alias_query = None
        self.active_steam_game_candidates = []

    # --------------------------------------------------
    # Browser-specific working referent
    # --------------------------------------------------

    def remember_browser_site(
        self,
        site_id: str,
    ) -> None:
        value = str(
            site_id
            or ""
        ).strip().lower()

        if not value:
            return

        self.active_browser_site = value

        self.recent_browser_sites = [
            item
            for item in self.recent_browser_sites
            if item != value
        ]

        self.recent_browser_sites.insert(
            0,
            value,
        )

        self.recent_browser_sites = (
            self.recent_browser_sites[:8]
        )

    # --------------------------------------------------
    # Local-file working referent
    # --------------------------------------------------

    def remember_local_file(
        self,
        path: str,
        name: Optional[str] = None,
    ) -> None:
        value = str(
            path
            or ""
        ).strip()

        if not value:
            return

        self.active_local_file_path = value
        self.active_local_file_name = (
            str(
                name
                or ""
            ).strip()
            or None
        )

        self.active_local_file_candidates = []
        self.active_local_file_pending_action = None

    def remember_local_file_candidates(
        self,
        candidates: List[Dict[str, Any]],
        pending_action: Optional[str] = None,
    ) -> None:
        cleaned = []

        for candidate in list(
            candidates
            or []
        )[:12]:
            if not isinstance(
                candidate,
                dict,
            ):
                continue

            path = str(
                candidate.get(
                    "path",
                    "",
                )
                or ""
            ).strip()

            name = str(
                candidate.get(
                    "name",
                    "",
                )
                or ""
            ).strip()

            if not path:
                continue

            cleaned.append({
                "path": path,
                "name": name,
            })

        self.active_local_file_candidates = cleaned
        self.active_local_file_path = None
        self.active_local_file_name = None

        action = str(
            pending_action
            or ""
        ).strip().lower()

        self.active_local_file_pending_action = (
            action
            if action in {
                "open",
                "find",
            }
            else None
        )

    def clear_local_file_referent(
        self,
    ) -> None:
        self.active_local_file_path = None
        self.active_local_file_name = None
        self.active_local_file_candidates = []
        self.active_local_file_pending_action = None

    # --------------------------------------------------
    # Gmail-specific working referents
    # --------------------------------------------------

    def remember_email_search_result(
        self,
        turn: TurnState,
        workflow_result,
    ) -> Optional[Dict[str, Any]]:
        """
        Preserve one targeted Gmail search as short-lived Core state.

        Successful and zero-match searches are both remembered. Recording a
        zero-match search prevents a later bare "that email" from accidentally
        falling back to an older successful Gmail result.

        Message IDs come only from verified Gmail evidence. Raw assistant prose
        is never parsed back into authority.
        """

        if (
            turn is None
            or getattr(
                turn,
                "intent",
                None,
            )
            != "email_search"
            or workflow_result is None
        ):
            return None

        result_data = (
            getattr(
                workflow_result,
                "data",
                {},
            )
            or {}
        )

        search_text = str(
            result_data.get(
                "search_text"
            )
            or turn.entities.get(
                "search_text",
                "",
            )
            or ""
        ).strip()

        if not search_text:
            return None

        time_scope = str(
            result_data.get(
                "time_scope"
            )
            or turn.entities.get(
                "time_scope",
                "rolling_days",
            )
            or "rolling_days"
        ).strip().lower()

        days_value = (
            result_data.get(
                "days"
            )
            or turn.entities.get(
                "days",
                30,
            )
            or 30
        )

        try:
            days = int(
                days_value
            )

        except (
            TypeError,
            ValueError,
        ):
            days = 30

        messages = []

        evidence_bundle = getattr(
            workflow_result,
            "evidence",
            None,
        )

        evidence_items = (
            getattr(
                evidence_bundle,
                "evidence",
                [],
            )
            if evidence_bundle is not None
            else []
        )

        for item in evidence_items:
            message_id = str(
                getattr(
                    item,
                    "source_id",
                    None,
                )
                or ""
            ).strip()

            if not message_id:
                continue

            item_data = (
                getattr(
                    item,
                    "data",
                    {},
                )
                or {}
            )

            message = {
                "message_id": message_id,
                "subject": str(
                    item_data.get(
                        "subject"
                    )
                    or getattr(
                        item,
                        "source_name",
                        None,
                    )
                    or ""
                ).strip(),
                "sender": str(
                    item_data.get(
                        "sender"
                    )
                    or ""
                ).strip(),
                "date": str(
                    getattr(
                        item,
                        "observed_at",
                        None,
                    )
                    or ""
                ).strip(),
            }

            messages.append(
                message
            )

        context = {
            "search_text": search_text,
            "time_scope": time_scope,
            "days": days,
            "status": str(
                getattr(
                    workflow_result,
                    "status",
                    "",
                )
                or ""
            ),
            "messages": messages,
        }

        search_key = (
            _normalise_email_referent_text(
                search_text
            )
        )

        # A repeated search for the same target + scope supersedes the older
        # copy. Different scopes remain available because "PayPal yesterday"
        # and "PayPal today" are legitimately different search episodes.
        retained = []

        for item in (
            self.recent_email_referents
        ):
            item_key = (
                _normalise_email_referent_text(
                    item.get(
                        "search_text"
                    )
                )
            )

            if (
                item_key == search_key
                and str(
                    item.get(
                        "time_scope",
                        "",
                    )
                ).lower()
                == time_scope
            ):
                continue

            retained.append(
                item
            )

        self.recent_email_referents = [
            context,
            *retained,
        ][
            :8
        ]

        return dict(
            context
        )

    def find_email_referent(
        self,
        target: Optional[str] = None,
        require_message: bool = True,
        allow_bare: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve a previously verified targeted Gmail context.

        Explicit target:
            May look through recent Gmail referents even when another workflow
            (such as inbox triage) became the generic active intent.

        Bare/deictic target:
            Only resolves while a specific targeted email search/read remains
            the generic active intent. An intervening inbox review therefore
            makes "that email" ambiguous rather than silently guessing.
        """

        contexts = list(
            self.recent_email_referents
            or []
        )

        if not contexts:
            return None

        if target:
            target_key = (
                _normalise_email_referent_text(
                    target
                )
            )

            if not target_key:
                return None

            scored = []

            for index, context in enumerate(
                contexts
            ):
                messages = list(
                    context.get(
                        "messages",
                        [],
                    )
                    or []
                )

                if (
                    require_message
                    and not messages
                ):
                    continue

                search_key = (
                    _normalise_email_referent_text(
                        context.get(
                            "search_text"
                        )
                    )
                )

                score = 0

                if target_key == search_key:
                    score = 100

                elif (
                    target_key
                    and search_key
                    and (
                        target_key in search_key
                        or search_key in target_key
                    )
                ):
                    score = 85

                for message in messages:
                    subject_key = (
                        _normalise_email_referent_text(
                            message.get(
                                "subject"
                            )
                        )
                    )

                    sender_key = (
                        _normalise_email_referent_text(
                            message.get(
                                "sender"
                            )
                        )
                    )

                    if target_key in {
                        subject_key,
                        sender_key,
                    }:
                        score = max(
                            score,
                            80,
                        )

                    elif (
                        target_key
                        and (
                            target_key in subject_key
                            or target_key in sender_key
                        )
                    ):
                        score = max(
                            score,
                            70,
                        )

                if score:
                    # Recency only breaks semantic ties.
                    scored.append(
                        (
                            score,
                            -index,
                            context,
                        )
                    )

            if not scored:
                return None

            scored.sort(
                key=lambda item: (
                    item[0],
                    item[1],
                ),
                reverse=True,
            )

            return dict(
                scored[0][2]
            )

        if not allow_bare:
            return None

        if self.active_intent not in {
            "email_search",
            "email_read",
        }:
            return None

        latest = contexts[
            0
        ]

        if (
            require_message
            and not latest.get(
                "messages"
            )
        ):
            return None

        return dict(
            latest
        )

    def resolve_single_email_message(
        self,
        target: Optional[str] = None,
        allow_bare: bool = False,
    ) -> Optional[Dict[str, Any]]:
        context = self.find_email_referent(
            target=target,
            require_message=True,
            allow_bare=allow_bare,
        )

        if not context:
            return None

        messages = list(
            context.get(
                "messages",
                [],
            )
            or []
        )

        if len(
            messages
        ) != 1:
            return None

        result = dict(
            messages[0]
        )

        result[
            "search_text"
        ] = context.get(
            "search_text"
        )

        result[
            "time_scope"
        ] = context.get(
            "time_scope"
        )

        result[
            "days"
        ] = context.get(
            "days"
        )

        return result

    def resolve_follow_up(self, turn: TurnState) -> TurnState:
        """
        Resolve immediate conversational dependence BEFORE epistemic routing.

        Phase 11.2.1 deliberately uses only Core-owned state derived from
        Oliver's own previous turn. Prior assistant prose is never promoted into
        factual authority here.
        """

        text = str(
            turn.raw_text
            or ""
        )

        pronouns = [
            match.group(1).lower()
            for match in (
                PRONOUN_PATTERN.finditer(
                    text
                )
            )
        ]

        previous = (
            self.latest_user_turn()
        )

        depends_on_previous = (
            self._generic_turn_depends_on_immediate_user_context(
                turn,
                pronouns,
            )
        )

        if (
            depends_on_previous
            and previous
        ):
            previous_text = str(
                previous.get(
                    "text",
                    "",
                )
                or ""
            ).strip()

            previous_subject = str(
                previous.get(
                    "subject",
                    "",
                )
                or ""
            ).strip()

            if previous_text:
                turn.entities[
                    "_conversation_context_user_text"
                ] = previous_text

                turn.entities[
                    "_conversation_context_intent"
                ] = str(
                    previous.get(
                        "intent",
                        "",
                    )
                    or ""
                ).strip()

            if pronouns:
                referent = (
                    previous_subject
                    or previous_text
                )

                if referent:
                    for pronoun in pronouns:
                        turn.resolved_referents[
                            pronoun
                        ] = referent

            if (
                previous_subject
                and not turn.subject
            ):
                turn.subject = (
                    previous_subject
                )

            turn.is_follow_up = True

            turn.add_reason(
                "resolved immediate conversational dependence from the "
                "previous user-authored turn before epistemic routing"
            )

            debate_continuation = (
                looks_like_debate_continuation(
                    text
                )
            )

            if debate_continuation:
                debate_subject = (
                    extract_pairwise_comparison(
                        previous_text
                    )
                    or pairwise_subject_from_hint(
                        previous_subject
                    )
                    or pairwise_subject_from_hint(
                        self.active_subject
                    )
                )

                if debate_subject:
                    turn.speech_act = "opinion_challenge"
                    turn.intent = "share_opinion"
                    turn.subject = debate_subject[
                        "label"
                    ]
                    turn.factuality = "subjective"
                    turn.preferred_authority = None
                    turn.requires_private_data = False
                    turn.requires_live_data = False
                    turn.should_use_tools = False
                    turn.should_answer_directly = True
                    turn.should_recommend = False
                    turn.should_continue_conversation = True
                    turn.confidence = max(
                        float(
                            turn.confidence
                            or 0.0
                        ),
                        0.97,
                    )

                    turn.entities[
                        "_debate_continuation"
                    ] = "true"

                    turn.entities[
                        "_debate_subject_key"
                    ] = debate_subject[
                        "key"
                    ]

                    turn.entities[
                        "_pairwise_left"
                    ] = debate_subject[
                        "left"
                    ]

                    turn.entities[
                        "_pairwise_right"
                    ] = debate_subject[
                        "right"
                    ]

                    turn.entities[
                        "_pairwise_asserted_side"
                    ] = debate_subject.get(
                        "asserted_side",
                        "left",
                    )

                    turn.entities[
                        "_pairwise_relation"
                    ] = debate_subject.get(
                        "relation",
                        "",
                    )

                    turn.add_reason(
                        "resolved explicit debate challenge against the active "
                        "pairwise comparison before epistemic routing"
                    )

                    # Existing privacy-aware public-context detection still owns
                    # whether external research is appropriate. Bare personal
                    # names are never auto-promoted to public web research merely
                    # because they appear in a comparison.
                    if looks_like_public_external_context(
                        previous_text
                    ):
                        turn.entities[
                            "_conversation_public_grounding_required"
                        ] = "true"

                        turn.add_reason(
                            "active debate has an explicit public/external context "
                            "signal and may use factual grounding before judgement"
                        )

            # A contextual evaluative question asks for Mairon's judgement, not
            # a fresh standalone public-world lookup. This prevents a phrase
            # such as "do you think she handled it well?" from being searched
            # on the web without its antecedent.
            if (
                turn.intent
                == "factual_question"
                and _looks_like_contextual_opinion_question(
                    text
                )
            ):
                turn.speech_act = "question"
                turn.intent = "share_opinion"
                turn.factuality = "subjective"
                turn.preferred_authority = None
                turn.requires_private_data = False
                turn.requires_live_data = False
                turn.should_use_tools = False
                turn.should_answer_directly = True
                turn.should_recommend = False
                turn.should_continue_conversation = True
                turn.confidence = max(
                    float(
                        turn.confidence
                        or 0.0
                    ),
                    0.9,
                )

                turn.add_reason(
                    "contextual evaluative question asks for conversational "
                    "judgement rather than standalone factual lookup"
                )

                if looks_like_public_external_context(
                    previous_text
                ):
                    turn.entities[
                        "_conversation_public_grounding_required"
                    ] = "true"

                    turn.add_reason(
                        "contextual opinion concerns a clearly public/external "
                        "subject and needs factual grounding before judgement"
                    )

        elif pronouns:
            # Preserve the pre-11.2 generic active-subject contract for
            # deterministic/domain workflows that already established an
            # authoritative subject (for example an order-status referent).
            # Immediate USER context above takes precedence when available.
            active_subject = str(
                self.active_subject
                or ""
            ).strip()

            if active_subject:
                for pronoun in pronouns:
                    turn.resolved_referents[
                        pronoun
                    ] = active_subject

                turn.is_follow_up = True

                if not turn.subject:
                    turn.subject = (
                        active_subject
                    )

                turn.add_reason(
                    "resolved follow-up pronoun against the existing "
                    "Core-owned active subject"
                )

            else:
                turn.unresolved_referents.extend(
                    pronoun
                    for pronoun in pronouns
                    if pronoun not in (
                        turn.unresolved_referents
                    )
                )

                turn.add_reason(
                    "follow-up pronoun present but no safe immediate "
                    "user-authored or Core-owned referent exists"
                )

        # Existing deterministic order-status inheritance remains intact.
        if (
            turn.intent == "email_search"
            and self.active_intent
            == "order_status"
        ):
            turn.intent = "order_status"
            turn.requested_action = (
                "check_order_status"
            )
            turn.preferred_authority = (
                "gmail"
            )
            turn.requires_private_data = True
            turn.requires_live_data = True
            turn.should_use_tools = True
            turn.should_answer_directly = False
            turn.factuality = "tool_verified"

            if (
                "merchant"
                in self.active_entities
            ):
                turn.entities[
                    "merchant"
                ] = self.active_entities[
                    "merchant"
                ]

            turn.add_reason(
                "inherited active order-status workflow from conversation state"
            )

        return turn


def append_visible_turn_to_model_history(
    current_state,
    user_input,
    assistant_text,
    system_instructions=None,
):
    """
    Add a Core-owned visible exchange to the local provider's conversation
    history without calling the language model.

    This keeps one continuous live conversation even when Core answered a
    turn deterministically.

    Example:
        Oliver -> Core/Gmail -> "ready to collect"
        Oliver -> Qwen follow-up

    Qwen should see the first exchange rather than starting from a blank
    conversational history.
    """

    if current_state is None:
        state = []

        if system_instructions:
            state.append({
                "role": "system",
                "content": str(
                    system_instructions
                ),
            })

    else:
        state = list(
            current_state
        )

    state.append({
        "role": "user",
        "content": str(
            user_input
        ),
    })

    state.append({
        "role": "assistant",
        "content": str(
            assistant_text
        ),
    })

    return state
