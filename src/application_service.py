from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from dotenv import load_dotenv

from ai.provider import create_provider
from core.action_manager import (
    describe_action,
)
from core.conversation_state import (
    append_visible_turn_to_model_history,
)
from core.orchestrator import (
    MaironCore,
)
from core.response_timer import (
    ResponseTimer,
)
from core.router import (
    approve_cloud_escalation,
    approve_pending_action,
    decline_cloud_escalation,
    decline_pending_action,
    route_message,
)
from continuity.conversation_journal import (
    get_response_timing_report,
    record_conversation_turn,
)
from mairon_identity import (
    build_mairon_instructions,
)
from memory.preference_store import (
    build_user_preference_recall_response,
    capture_user_preference,
)


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]


@dataclass
class ApplicationTurn:
    """
    One UI-neutral Mairon application result.

    `status` is one of:
      - answered
      - system
      - cloud_approval_required
      - action_approval_required
      - pending_approval_exists
      - error
    """

    status: str
    user_text: str = ""
    answer: Optional[str] = None
    response_seconds: Optional[float] = None

    intent: Optional[str] = None
    authority: Optional[str] = None

    approval_kind: Optional[str] = None
    approval_title: Optional[str] = None
    approval_detail: Optional[str] = None
    reason: Optional[str] = None

    channel: str = "text"


@dataclass
class _PendingApproval:
    kind: str
    router_result: Any
    user_text: str
    instructions: str
    response_timer: ResponseTimer
    channel: str


class MaironApplication:
    """
    UI-neutral Mairon session.

    This is the boundary desktop/mobile/terminal clients should call.
    The UI never gets to bypass Core, router permissions, or provider state.
    """

    def __init__(
        self,
        user_name: Optional[str] = None,
        *,
        local_ai=None,
        cloud_ai=None,
        core: Optional[MaironCore] = None,
        create_providers: bool = True,
        event_sink: Optional[
            Callable[
                [
                    str,
                ],
                None,
            ]
        ] = None,
    ):
        load_dotenv(
            PROJECT_ROOT
            / ".env"
        )

        configured_name = str(
            user_name
            or os.getenv(
                "MAIRON_USER_NAME",
                "",
            )
            or os.getenv(
                "USERNAME",
                "",
            )
            or "User"
        ).strip()

        self.user_name = (
            configured_name
            or "User"
        )

        self.local_model_name = str(
            os.getenv(
                "MAIRON_LOCAL_MODEL",
                "qwen3.5:9b",
            )
            or "qwen3.5:9b"
        ).strip()

        self.event_sink = (
            event_sink
            or (
                lambda message: None
            )
        )

        self.local_ai = local_ai
        self.cloud_ai = cloud_ai

        if create_providers:
            if self.local_ai is None:
                try:
                    self.local_ai = (
                        create_provider(
                            "ollama"
                        )
                    )

                except Exception as exc:
                    raise RuntimeError(
                        "Failed to start the local AI provider: "
                        + str(
                            exc
                        )
                    ) from exc

            if self.cloud_ai is None:
                api_key = os.getenv(
                    "OPENAI_API_KEY"
                )

                if api_key:
                    try:
                        self.cloud_ai = (
                            create_provider(
                                "openai",
                                api_key,
                            )
                        )

                    except Exception as exc:
                        self._emit_event(
                            "Cloud AI provider unavailable: "
                            + str(
                                exc
                            )
                        )

        self.core = (
            core
            or MaironCore()
        )

        self.instructions = (
            build_mairon_instructions(
                self.user_name
            )
        )

        self.local_state = None
        self.cloud_state = None

        self.last_user_input = None
        self.last_assistant_answer = None

        self._pending: Optional[
            _PendingApproval
        ] = None

    # --------------------------------------------------
    # Public status
    # --------------------------------------------------

    @property
    def cloud_available(
        self,
    ) -> bool:
        return (
            self.cloud_ai
            is not None
        )

    @property
    def has_pending_approval(
        self,
    ) -> bool:
        return (
            self._pending
            is not None
        )

    def session_status(
        self,
    ) -> dict:
        return {
            "user_name": self.user_name,
            "local_model": (
                self.local_model_name
            ),
            "cloud_available": (
                self.cloud_available
            ),
            "pending_approval": (
                self._pending.kind
                if self._pending
                else None
            ),
        }

    # --------------------------------------------------
    # Core turn entrypoint
    # --------------------------------------------------

    def submit_text(
        self,
        user_text: str,
        *,
        channel: str = "text",
    ) -> ApplicationTurn:
        text = str(
            user_text
            or ""
        ).strip()

        channel_value = (
            "voice"
            if str(
                channel
                or ""
            ).strip().lower()
            == "voice"
            else "text"
        )

        if not text:
            return ApplicationTurn(
                status="error",
                user_text="",
                answer=(
                    "There isn't anything to send."
                ),
                channel=channel_value,
            )

        if self._pending is not None:
            return ApplicationTurn(
                status="pending_approval_exists",
                user_text=text,
                answer=(
                    "Resolve the pending approval before sending another request."
                ),
                approval_kind=(
                    self._pending.kind
                ),
                channel=channel_value,
            )

        if text.lower() == "/timing":
            return ApplicationTurn(
                status="system",
                user_text=text,
                answer=(
                    self._build_timing_report()
                ),
                channel=channel_value,
            )

        response_timer = (
            ResponseTimer()
        )

        # --------------------------------------------------
        # Typed preference capture
        # --------------------------------------------------

        try:
            preference_result = (
                capture_user_preference(
                    user_text=text,
                    previous_assistant_text=(
                        self.last_assistant_answer
                    ),
                    previous_user_text=(
                        self.last_user_input
                    ),
                )
            )

            if (
                preference_result
                and preference_result.get(
                    "changed"
                )
            ):
                self._emit_event(
                    "[Preference] Updated "
                    + self.user_name
                    + " "
                    + str(
                        preference_result.get(
                            "domain",
                            "",
                        )
                    )
                    + " "
                    + str(
                        preference_result.get(
                            "preference_key",
                            "",
                        )
                    ).replace(
                        "_",
                        " ",
                    )
                    + "."
                )

        except Exception as exc:
            self._emit_event(
                "[Preference] Capture failed: "
                + str(
                    exc
                )
            )

        try:
            preference_answer = (
                build_user_preference_recall_response(
                    user_text=text,
                    user_name=self.user_name,
                )
            )

        except Exception as exc:
            self._emit_event(
                "[Preference] Recall failed: "
                + str(
                    exc
                )
            )

            preference_answer = None

        if preference_answer is not None:
            self._emit_event(
                "[Preference] Core-owned preference recall."
            )

            return self._finalize_direct_response(
                user_text=text,
                answer=preference_answer,
                timer=response_timer,
                channel=channel_value,
                intent="preference_recall",
                authority="memory",
            )

        # --------------------------------------------------
        # Core routing/workflows
        # --------------------------------------------------

        core_decision = None

        try:
            core_decision = (
                self.core.prepare_turn(
                    text
                )
            )

        except Exception as exc:
            # Preserve the current terminal behaviour: a Core routing bug
            # degrades to the provider path rather than killing the session.
            self._emit_event(
                "[Core] Pre-routing failed: "
                + str(
                    exc
                )
            )

        intent = None
        authority = None

        if core_decision is not None:
            turn = (
                core_decision.turn
            )

            route = (
                core_decision.epistemic_route
            )

            intent = str(
                getattr(
                    turn,
                    "intent",
                    "",
                )
                or ""
            ).strip() or None

            authority = str(
                getattr(
                    route,
                    "authority",
                    "",
                )
                or ""
            ).strip() or None

            if (
                intent
                not in {
                    "casual_conversation",
                    "factual_question",
                }
                or str(
                    getattr(
                        route,
                        "mode",
                        "",
                    )
                    or ""
                )
                not in {
                    "conversation",
                    "classify_then_verify",
                }
            ):
                self._emit_event(
                    "[Core] "
                    + str(
                        intent
                        or "unknown"
                    )
                    + " -> "
                    + str(
                        authority
                        or "unknown"
                    )
                )

            if core_decision.needs_clarification:
                answer = (
                    core_decision.clarification_question
                    or (
                        "I need a little more information "
                        "before I can do that."
                    )
                )

                return self._finalize_direct_response(
                    user_text=text,
                    answer=answer,
                    timer=response_timer,
                    channel=channel_value,
                    intent=intent,
                    authority=authority,
                )

            if (
                core_decision.direct_response
                is not None
            ):
                return self._finalize_direct_response(
                    user_text=text,
                    answer=(
                        core_decision.direct_response
                    ),
                    timer=response_timer,
                    channel=channel_value,
                    intent=intent,
                    authority=authority,
                )

            turn_instructions = (
                self.instructions
                + "\n\n"
                + (
                    core_decision
                    .answer_contract
                    .to_model_instruction()
                )
            )

        else:
            turn_instructions = (
                self.instructions
            )

        # --------------------------------------------------
        # Provider/router
        # --------------------------------------------------

        if self.local_ai is None:
            return self._finalize_error(
                user_text=text,
                answer=(
                    "The local AI provider isn't available."
                ),
                timer=response_timer,
                channel=channel_value,
                intent=intent,
                authority=authority,
            )

        try:
            result = route_message(
                self.local_ai,
                self.cloud_ai,
                text,
                turn_instructions,
                self.local_state,
                self.cloud_state,
            )

        except Exception as exc:
            return self._finalize_error(
                user_text=text,
                answer=(
                    "Mairon's response pipeline failed: "
                    + str(
                        exc
                    )
                ),
                timer=response_timer,
                channel=channel_value,
                intent=intent,
                authority=authority,
            )

        self.local_state = (
            result.local_state
        )

        self.cloud_state = (
            result.cloud_state
        )

        if result.status == (
            "cloud_approval_required"
        ):
            response_timer.pause()

            self._pending = (
                _PendingApproval(
                    kind="cloud",
                    router_result=result,
                    user_text=text,
                    instructions=turn_instructions,
                    response_timer=response_timer,
                    channel=channel_value,
                )
            )

            return ApplicationTurn(
                status="cloud_approval_required",
                user_text=text,
                reason=(
                    str(
                        result.reason
                        or ""
                    ).strip()
                    or None
                ),
                approval_kind="cloud",
                approval_title=(
                    "Use GPT-5.6 Luna?"
                ),
                approval_detail=(
                    str(
                        result.reason
                        or ""
                    ).strip()
                    or (
                        "Mairon recommends cloud processing for this request."
                    )
                ),
                intent=intent,
                authority=authority,
                channel=channel_value,
            )

        if result.status == (
            "action_approval_required"
        ):
            response_timer.pause()

            self._pending = (
                _PendingApproval(
                    kind="action",
                    router_result=result,
                    user_text=text,
                    instructions=turn_instructions,
                    response_timer=response_timer,
                    channel=channel_value,
                )
            )

            return ApplicationTurn(
                status="action_approval_required",
                user_text=text,
                approval_kind="action",
                approval_title=(
                    "Approve calendar change?"
                ),
                approval_detail=(
                    self._describe_pending_action(
                        result.pending_action
                    )
                ),
                intent=intent,
                authority=authority,
                channel=channel_value,
            )

        return self._finalize_router_response(
            user_text=text,
            result=result,
            timer=response_timer,
            channel=channel_value,
            intent=intent,
            authority=authority,
        )

    # --------------------------------------------------
    # Approval continuation
    # --------------------------------------------------

    def resolve_pending_approval(
        self,
        approved: bool,
    ) -> ApplicationTurn:
        pending = (
            self._pending
        )

        if pending is None:
            return ApplicationTurn(
                status="error",
                answer=(
                    "There isn't a pending approval."
                ),
            )

        self._pending = None

        pending.response_timer.resume()

        result = (
            pending.router_result
        )

        try:
            if pending.kind == "cloud":
                if approved:
                    result = (
                        approve_cloud_escalation(
                            self.cloud_ai,
                            result.pending_prompt,
                            pending.instructions,
                            self.local_state,
                            self.cloud_state,
                        )
                    )

                else:
                    result = (
                        decline_cloud_escalation(
                            self.local_ai,
                            result.pending_prompt,
                            pending.instructions,
                            self.local_state,
                            self.cloud_state,
                        )
                    )

            elif pending.kind == "action":
                if approved:
                    result = (
                        approve_pending_action(
                            result
                        )
                    )

                else:
                    result = (
                        decline_pending_action(
                            result
                        )
                    )

            else:
                return self._finalize_error(
                    user_text=pending.user_text,
                    answer=(
                        "The pending approval type is invalid."
                    ),
                    timer=pending.response_timer,
                    channel=pending.channel,
                )

        except Exception as exc:
            return self._finalize_error(
                user_text=pending.user_text,
                answer=(
                    "The approval action failed: "
                    + str(
                        exc
                    )
                ),
                timer=pending.response_timer,
                channel=pending.channel,
            )

        self.local_state = (
            result.local_state
        )

        self.cloud_state = (
            result.cloud_state
        )

        # Declining cloud can legitimately fall back to local generation,
        # which may itself request a permission-gated action.
        if result.status == (
            "action_approval_required"
        ):
            pending.response_timer.pause()

            self._pending = (
                _PendingApproval(
                    kind="action",
                    router_result=result,
                    user_text=(
                        pending.user_text
                    ),
                    instructions=(
                        pending.instructions
                    ),
                    response_timer=(
                        pending.response_timer
                    ),
                    channel=pending.channel,
                )
            )

            return ApplicationTurn(
                status="action_approval_required",
                user_text=(
                    pending.user_text
                ),
                approval_kind="action",
                approval_title=(
                    "Approve calendar change?"
                ),
                approval_detail=(
                    self._describe_pending_action(
                        result.pending_action
                    )
                ),
                channel=pending.channel,
            )

        return self._finalize_router_response(
            user_text=pending.user_text,
            result=result,
            timer=pending.response_timer,
            channel=pending.channel,
        )

    # --------------------------------------------------
    # Finalisation
    # --------------------------------------------------

    def _finalize_direct_response(
        self,
        *,
        user_text: str,
        answer: str,
        timer: ResponseTimer,
        channel: str,
        intent: Optional[str],
        authority: Optional[str],
    ) -> ApplicationTurn:
        answer_value = str(
            answer
            or ""
        )

        self.local_state = (
            append_visible_turn_to_model_history(
                current_state=(
                    self.local_state
                ),
                user_input=user_text,
                assistant_text=answer_value,
                system_instructions=(
                    self.instructions
                ),
            )
        )

        return self._record_final_turn(
            user_text=user_text,
            answer=answer_value,
            timer=timer,
            channel=channel,
            intent=intent,
            authority=authority,
            status="answered",
        )

    def _finalize_router_response(
        self,
        *,
        user_text: str,
        result,
        timer: ResponseTimer,
        channel: str,
        intent: Optional[str] = None,
        authority: Optional[str] = None,
    ) -> ApplicationTurn:
        answer = str(
            getattr(
                result,
                "answer",
                "",
            )
            or ""
        )

        if not answer:
            answer = (
                "I couldn't produce a response."
            )

        return self._record_final_turn(
            user_text=user_text,
            answer=answer,
            timer=timer,
            channel=channel,
            intent=intent,
            authority=authority,
            status="answered",
        )

    def _finalize_error(
        self,
        *,
        user_text: str,
        answer: str,
        timer: ResponseTimer,
        channel: str,
        intent: Optional[str] = None,
        authority: Optional[str] = None,
    ) -> ApplicationTurn:
        return self._record_final_turn(
            user_text=user_text,
            answer=answer,
            timer=timer,
            channel=channel,
            intent=intent,
            authority=authority,
            status="error",
        )

    def _record_final_turn(
        self,
        *,
        user_text: str,
        answer: str,
        timer: ResponseTimer,
        channel: str,
        intent: Optional[str],
        authority: Optional[str],
        status: str,
    ) -> ApplicationTurn:
        response_seconds = (
            timer.stop()
        )

        try:
            record_conversation_turn(
                user_text=user_text,
                assistant_text=answer,
                channel=channel,
                response_seconds=(
                    response_seconds
                ),
            )

        except Exception as exc:
            self._emit_event(
                "[Context] Conversation journal write failed: "
                + str(
                    exc
                )
            )

        self.last_user_input = (
            str(
                user_text
                or ""
            )
        )

        self.last_assistant_answer = (
            str(
                answer
                or ""
            )
        )

        return ApplicationTurn(
            status=status,
            user_text=user_text,
            answer=answer,
            response_seconds=(
                response_seconds
            ),
            intent=intent,
            authority=authority,
            channel=channel,
        )

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    def _describe_pending_action(
        self,
        action,
    ) -> str:
        try:
            return str(
                describe_action(
                    action
                )
            )

        except Exception:
            return (
                "Mairon is requesting permission "
                "for a calendar write."
            )

    def _emit_event(
        self,
        message: str,
    ) -> None:
        try:
            self.event_sink(
                str(
                    message
                    or ""
                )
            )

        except Exception:
            pass

    def _build_timing_report(
        self,
    ) -> str:
        try:
            report = (
                get_response_timing_report(
                    recent_limit=20
                )
            )

        except Exception as exc:
            return (
                "Could not read timing statistics: "
                + str(
                    exc
                )
            )

        lines = [
            "Response-ready statistics",
            "Only turns recorded since timing was enabled are included.",
        ]

        for label, key in (
            (
                "This session",
                "session",
            ),
            (
                "Last 20",
                "recent",
            ),
            (
                "Lifetime",
                "lifetime",
            ),
        ):
            stats = (
                report[
                    key
                ]
            )

            count = int(
                stats.get(
                    "count",
                    0,
                )
                or 0
            )

            if count == 0:
                lines.append(
                    f"{label}: no measured turns yet"
                )

                continue

            lines.append(
                f"{label}: "
                f"{count} turns | "
                "avg "
                + self._format_seconds(
                    stats.get(
                        "average_seconds"
                    )
                )
                + " | median "
                + self._format_seconds(
                    stats.get(
                        "median_seconds"
                    )
                )
                + " | p95 "
                + self._format_seconds(
                    stats.get(
                        "p95_seconds"
                    )
                )
                + " | fastest "
                + self._format_seconds(
                    stats.get(
                        "fastest_seconds"
                    )
                )
                + " | slowest "
                + self._format_seconds(
                    stats.get(
                        "slowest_seconds"
                    )
                )
            )

        return "\n".join(
            lines
        )

    @staticmethod
    def _format_seconds(
        value,
    ) -> str:
        if value is None:
            return "-"

        return (
            f"{float(value):.2f}s"
        )
