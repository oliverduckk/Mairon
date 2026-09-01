from dataclasses import dataclass
from typing import Optional

from core.answer_contract import (
    AnswerContract,
    build_answer_contract,
)
from core.conversation_state import (
    ConversationState,
)
from core.epistemic_router import (
    EpistemicRoute,
    route_epistemic_authority,
)
from core.intent_router import (
    classify_turn,
)
from core.turn_state import (
    TurnState,
)
from core.workflow_result import (
    WorkflowResult,
)
from core.workflows.email_search import (
    search_email,
)
from core.workflows.order_status import (
    check_order_status,
)


@dataclass
class CoreDecision:
    """
    Output of Mairon Core before the language/personality layer.

    direct_response:
        Core already has an authoritative concise answer. The language
        model is optional and may be skipped entirely.

    answer_contract:
        Rules for a later language layer when natural generation is useful.
    """

    turn: TurnState
    epistemic_route: EpistemicRoute

    answer_contract: AnswerContract

    workflow_result: Optional[
        WorkflowResult
    ] = None

    direct_response: Optional[str] = None

    needs_clarification: bool = False
    clarification_question: Optional[str] = None


class MaironCore:
    """
    First Core orchestration layer.

    v1 deliberately handles only the workflows we have earned through
    real failures. Additional capabilities should be added as explicit
    routes/workflows rather than by turning this into another giant
    provider file.
    """

    def __init__(
        self,
    ):
        self.conversation_state = (
            ConversationState()
        )

    def reset_conversation_state(
        self,
    ) -> None:
        self.conversation_state = (
            ConversationState()
        )

    def _resolve_turn(
        self,
        user_input: str,
    ) -> TurnState:
        turn = classify_turn(
            user_input=user_input,
            conversation_state=(
                self.conversation_state
            ),
        )

        turn = (
            self.conversation_state.resolve_follow_up(
                turn
            )
        )

        return turn

    def _merchant_for_turn(
        self,
        turn: TurnState,
    ) -> Optional[str]:
        merchant = turn.entities.get(
            "merchant"
        )

        if merchant:
            return str(
                merchant
            ).strip()

        merchant = (
            self.conversation_state
            .active_entities
            .get(
                "merchant"
            )
        )

        if merchant:
            return str(
                merchant
            ).strip()

        return None

    def _email_search_text_for_turn(
        self,
        turn: TurnState,
    ) -> Optional[str]:
        search_text = turn.entities.get(
            "search_text"
        )

        if search_text:
            return str(
                search_text
            ).strip()

        return None

    def _email_days_for_turn(
        self,
        turn: TurnState,
    ) -> int:
        value = turn.entities.get(
            "days",
            30,
        )

        try:
            days = int(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            days = 30

        return max(
            1,
            min(
                days,
                365,
            ),
        )

    def _email_time_scope_for_turn(
        self,
        turn: TurnState,
    ) -> str:
        value = turn.entities.get(
            "time_scope",
            "rolling_days",
        )

        value = str(
            value
            or "rolling_days"
        ).strip().lower()

        if value not in {
            "rolling_days",
            "today",
            "yesterday",
        }:
            value = "rolling_days"

        return value

    def prepare_turn(
        self,
        user_input: str,
    ) -> CoreDecision:
        """
        Classify, resolve context, route factual authority, and execute any
        deterministic workflow Core already owns.
        """

        turn = self._resolve_turn(
            user_input
        )

        route = (
            route_epistemic_authority(
                turn
            )
        )

        workflow_result = None
        direct_response = None

        # --------------------------------------------------
        # Deterministic targeted Gmail workflow
        # --------------------------------------------------

        if turn.intent == "email_search":
            search_text = (
                self._email_search_text_for_turn(
                    turn
                )
            )

            if not search_text:
                contract = build_answer_contract(
                    turn=turn,
                    route=route,
                )

                self.conversation_state.update_from_turn(
                    turn
                )

                return CoreDecision(
                    turn=turn,
                    epistemic_route=route,
                    answer_contract=contract,
                    needs_clarification=True,
                    clarification_question=(
                        "What should I search your email for?"
                    ),
                )

            days = self._email_days_for_turn(
                turn
            )

            time_scope = (
                self._email_time_scope_for_turn(
                    turn
                )
            )

            workflow_result = search_email(
                search_text=search_text,
                days=days,
                time_scope=time_scope,
            )

            contract = build_answer_contract(
                turn=turn,
                route=route,
                evidence=(
                    workflow_result.evidence
                    if workflow_result
                    else None
                ),
            )

            if (
                workflow_result
                and workflow_result.answer_fact
            ):
                contract.required_claims.append(
                    workflow_result.answer_fact
                )

            direct_response = (
                workflow_result.answer_fact
                if (
                    workflow_result
                    and workflow_result.success
                )
                else None
            )

            if (
                workflow_result
                and not workflow_result.success
            ):
                direct_response = (
                    "I couldn't check Gmail for that just now."
                )

            self.conversation_state.update_from_turn(
                turn
            )

            return CoreDecision(
                turn=turn,
                epistemic_route=route,
                answer_contract=contract,
                workflow_result=workflow_result,
                direct_response=direct_response,
            )

        # --------------------------------------------------
        # Deterministic order-status workflow
        # --------------------------------------------------

        if turn.intent == "order_status":
            merchant = self._merchant_for_turn(
                turn
            )

            if not merchant:
                contract = build_answer_contract(
                    turn=turn,
                    route=route,
                )

                self.conversation_state.update_from_turn(
                    turn
                )

                return CoreDecision(
                    turn=turn,
                    epistemic_route=route,
                    answer_contract=contract,
                    needs_clarification=True,
                    clarification_question=(
                        "Which retailer or order are you asking about?"
                    ),
                )

            turn.entities[
                "merchant"
            ] = merchant

            if not turn.subject:
                turn.subject = (
                    f"{merchant} order"
                )

            workflow_result = (
                check_order_status(
                    merchant=merchant
                )
            )

            contract = build_answer_contract(
                turn=turn,
                route=route,
                evidence=(
                    workflow_result.evidence
                    if workflow_result
                    else None
                ),
            )

            if (
                workflow_result
                and workflow_result.answer_fact
            ):
                contract.required_claims.append(
                    workflow_result.answer_fact
                )

            # For order status, reliability beats stylistic generation.
            # Core already has a concise authoritative answer, so skip the
            # model entirely in v1.
            direct_response = (
                workflow_result.answer_fact
                if (
                    workflow_result
                    and workflow_result.success
                )
                else None
            )

            if (
                workflow_result
                and not workflow_result.success
            ):
                direct_response = (
                    "I couldn't verify the order status from Gmail just now."
                )

            self.conversation_state.update_from_turn(
                turn
            )

            return CoreDecision(
                turn=turn,
                epistemic_route=route,
                answer_contract=contract,
                workflow_result=workflow_result,
                direct_response=direct_response,
            )

        # --------------------------------------------------
        # Non-workflow conversation
        # --------------------------------------------------

        contract = build_answer_contract(
            turn=turn,
            route=route,
        )

        self.conversation_state.update_from_turn(
            turn
        )

        return CoreDecision(
            turn=turn,
            epistemic_route=route,
            answer_contract=contract,
        )
