import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.turn_state import TurnState


PRONOUN_PATTERN = re.compile(
    r"\b(it|that|this|they|them|those|these)\b",
    flags=re.IGNORECASE,
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

    # Keep the last Steam-game action separate from desktop-app referents.
    # Until game close/control is implemented, this prevents "close it" from
    # accidentally targeting an older desktop app after a game launch.
    active_steam_game_title: Optional[str] = None

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

    def update_from_turn(self, turn: TurnState) -> None:
        if turn.subject:
            self.remember_subject(
                turn.subject
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

                self.active_entities[
                    str(key)
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

        elif turn.intent == "launch_steam_game":
            self.active_desktop_target = None

            self.active_steam_game_title = str(
                turn.entities.get(
                    "steam_game_title",
                    "",
                )
                or ""
            ).strip() or None

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
        text = turn.raw_text

        pronouns = [
            match.group(1).lower()
            for match in (
                PRONOUN_PATTERN.finditer(
                    text
                )
            )
        ]

        if not pronouns:
            return turn

        if not self.active_subject:
            turn.unresolved_referents.extend(
                pronouns
            )

            turn.add_reason(
                "follow-up pronoun present but no active subject exists"
            )

            return turn

        for pronoun in pronouns:
            turn.resolved_referents[
                pronoun
            ] = self.active_subject

        turn.is_follow_up = True

        if not turn.subject:
            turn.subject = (
                self.active_subject
            )

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
