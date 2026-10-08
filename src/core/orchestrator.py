from dataclasses import dataclass
from typing import Optional

from core.answer_contract import (
    AnswerContract,
    build_answer_contract,
)
from core.answer_candidate import CandidateOrigin
from core.acceptance_shadow import AcceptanceShadowRecord
from core.acceptance_publication import (
    AcceptancePublicationRecord,
    publish_core_result,
    publish_limitation_response,
    publish_time_budget,
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
from core.epistemic_calibration import classify_private_user_question
from core.task_budget import resolve_time_budget
from core.user_statement_recall import extract_latest_stated_colour
from core.turn_state import (
    TurnState,
)
from core.workflow_result import (
    WorkflowResult,
)
from core.workflows.application_launch import (
    launch_approved_application,
)
from core.workflows.arithmetic import (
    calculate_arithmetic,
)
from core.workflows.application_control import (
    control_approved_application,
)
from core.workflows.browser_search import (
    open_browser_action,
    open_browser_search,
)
from core.workflows.steam_game_launch import (
    discover_installed_steam_games,
    launch_installed_steam_game,
)
from core.steam_library import (
    resolve_installed_steam_game,
)
from core.steam_alias_store import (
    set_steam_game_alias,
)
from core.workflows.file_actions import (
    find_local_file,
    open_local_file,
    open_local_files,
    open_trusted_folder,
    select_local_file,
)
from core.workflows.email_read import (
    read_selected_email,
)
from core.workflows.email_search import (
    search_email,
)
from core.workflows.order_status import (
    check_order_status,
)
from core.workflows.self_correction import (
    build_self_correction_response,
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

    # Observational only: this record never controls direct_response.
    acceptance_shadow: Optional[AcceptanceShadowRecord] = None

    # Authoritative only for the bounded typed Core paths integrated below.
    acceptance_publication: Optional[AcceptancePublicationRecord] = None


class MaironCore:
    """
    First Core orchestration layer.

    Deterministic workflows own authority, identity, state and selection.
    The local language model may phrase/summarise verified evidence but does
    not decide which private source is true.
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
            self.conversation_state
            .resolve_follow_up(
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

    def _email_message_id_for_turn(
        self,
        turn: TurnState,
    ) -> Optional[str]:
        value = str(
            turn.entities.get(
                "message_id",
                "",
            )
            or ""
        ).strip()

        return value or None

    def _strict_email_read_contract(
        self,
        turn: TurnState,
        route: EpistemicRoute,
        workflow_result: WorkflowResult,
    ) -> AnswerContract:
        contract = build_answer_contract(
            turn=turn,
            route=route,
            evidence=(
                workflow_result.evidence
                if workflow_result
                else None
            ),
        )

        action_assessment = (
            str(
                turn.entities.get(
                    "email_read_purpose",
                    "",
                )
                or ""
            ).strip().lower()
            == "action_assessment"
        )

        contract.allow_recommendations = bool(
            action_assessment
        )

        contract.allow_new_factual_claims = False
        contract.allow_follow_up_question = False

        contract.forbidden_behaviours.extend([
            "Answer from the verified Gmail message body supplied by Core.",
            "Do not substitute another inbox batch, sender, message, or date.",
            "Do not claim the email was missing when Core supplied verified contents.",
            "Do not reconstruct email contents from model memory or prior assistant prose.",
            "Do not offer to search or read the email again; Core already read it.",
            "Do not append unrelated inbox information.",
        ])

        if action_assessment:
            contract.forbidden_behaviours.extend([
                "Judge whether Oliver needs to act only from requirements, "
                "deadlines, warnings, requests, or consequences actually present "
                "in the verified email.",
                "If the email states that no action is required, preserve that.",
                "If the body does not establish whether action is needed, say the "
                "evidence is unclear rather than inventing a task.",
            ])

        return contract

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

        # Phase 11.6.6B2: a clear user-supplied time budget is arithmetic,
        # not an invitation to let the conversational model improvise figures.
        # Parsing is deliberately conservative: ambiguous tasks fall through.
        # Calendar/external actions and other specialized intents are untouched.
        if turn.intent in {
            "casual_conversation", "factual_question", "self_correction",
            "reason_from_supplied_premises", "calculate_arithmetic",
        }:
            budget = resolve_time_budget(
                user_input,
                getattr(self.conversation_state, "recent_user_turns", []),
            )
            if budget is not None:
                turn.intent = "reason_from_supplied_premises"
                turn.speech_act = "question"
                turn.factuality = "user_premise_reasoning"
                turn.should_use_tools = False
                turn.should_answer_directly = True
                turn.should_recommend = False
                turn.add_reason(
                    "Core deterministically resolved a complete, user-supplied time budget"
                )
                route = route_epistemic_authority(turn)
                contract = build_answer_contract(turn=turn, route=route)
                try:
                    budget_answer = budget.answer
                except Exception:
                    budget_answer = None
                publication = publish_time_budget(
                    text=budget_answer,
                    contract=contract,
                    resolution=budget,
                    path="time_budget",
                )
                self.conversation_state.update_from_turn(turn)
                return CoreDecision(
                    turn=turn, epistemic_route=route,
                    answer_contract=contract, direct_response=publication.text,
                    acceptance_publication=publication.record,
                )

        # Only an explicit, uniquely extractable latest USER statement can be
        # returned directly. Everything else keeps the grounded recall lane.
        if turn.intent == "conversation_recall":
            extracted = extract_latest_stated_colour(
                user_input,
                getattr(self.conversation_state, "recent_user_turns", []),
            )
            if extracted:
                contract = build_answer_contract(turn=turn, route=route)
                self.conversation_state.update_from_turn(turn)
                return CoreDecision(
                    turn=turn, epistemic_route=route,
                    answer_contract=contract, direct_response=extracted,
                )

        # An unaided text assistant must not send private physical observations
        # to public search, or ask its language model to guess. A future camera
        # integration can replace this branch only when actual sensor evidence
        # is explicitly present in the application/Core contract.
        if route.mode in {"private_state_uncertain", "unobserved_private_state"}:
            # Support both the current route and the legacy name. The helper
            # returns a KIND, not a boolean; each category needs its own
            # truthful response rather than the previous shirt-only fallback.
            private_kind = classify_private_user_question(user_input)
            if private_kind == "concealed_object":
                direct_response = (
                    "I can't observe a concealed object through this text chat, "
                    "so I don't know the answer without you showing or telling me."
                )
            elif private_kind == "current_appearance":
                direct_response = (
                    "I can't see what you're wearing through this text chat, "
                    "so I don't know its colour or appearance."
                )
            elif private_kind == "undisclosed_meal":
                direct_response = (
                    "I don't know what you ate unless you've told me in "
                    "our conversation. I won't guess."
                )
            elif private_kind == "private_thought":
                direct_response = (
                    "I can't observe what you're thinking, so I don't know "
                    "without you telling me."
                )
            else:
                # Conservative boundary for a new category not yet given
                # a domain-specific response. Never fabricate a personal fact.
                direct_response = (
                    "I don't have enough information to know that private fact."
                )

            contract = build_answer_contract(turn=turn, route=route)
            publication = publish_limitation_response(
                text=direct_response,
                contract=contract,
                user_input=user_input,
                user_history=getattr(
                    self.conversation_state, "recent_user_turns", []
                ),
                path="private_state",
                origin=CandidateOrigin.CRITICAL_CORE,
                emit=False,
            )
            self.conversation_state.update_from_turn(turn)
            return CoreDecision(
                turn=turn,
                epistemic_route=route,
                answer_contract=contract,
                workflow_result=None,
                direct_response=publication.text,
                acceptance_publication=publication.record,
            )

        # --------------------------------------------------
        # Reasoning grounded solely in the user's supplied premises
        # --------------------------------------------------
        if turn.intent == "reason_from_supplied_premises":
            contract = build_answer_contract(turn=turn, route=route)
            contract.allow_recommendations = False
            contract.allow_follow_up_question = False
            contract.allow_new_factual_claims = bool(
                turn.entities.get("reasoning_kind") == "code_trace"
            )
            contract.forbidden_behaviours.extend([
                "Solve from the specific premises Oliver supplied, not public web research.",
                "Do not introduce unrelated world facts or invent missing numerical inputs.",
                "If an essential premise is missing, state that instead of guessing.",
            ])

            if turn.entities.get("reasoning_kind") == "code_trace":
                contract.forbidden_behaviours.extend([
                    "Trace the supplied code in execution order rather than jumping straight to the final mutated state.",
                    "If Oliver supplied multiple print/output expressions, report each observed output separately and in order.",
                    "For Python default arguments, distinguish the reused default object from closure variables; do not claim a default argument is stored in a closure merely because it persists across calls.",
                ])

            if turn.entities.get("reasoning_kind") == "threshold_comparison":
                contract.forbidden_behaviours.extend([
                    "Answer only the supplied threshold/limit comparison.",
                    "Do not infer fees, enforcement, security-screening outcomes, dimensional fit, or other consequences that Oliver did not supply.",
                ])

            direct_response = turn.entities.get("reasoning_direct_answer")
            self.conversation_state.update_from_turn(turn)
            return CoreDecision(
                turn=turn,
                epistemic_route=route,
                answer_contract=contract,
                direct_response=direct_response,
            )

        # --------------------------------------------------
        # Deterministic arithmetic authority
        # --------------------------------------------------

        if turn.intent == "calculate_arithmetic":
            expression = str(
                turn.entities.get(
                    "arithmetic_expression",
                    "",
                )
                or ""
            ).strip()

            operation = str(
                turn.entities.get(
                    "arithmetic_operation",
                    "expression",
                )
                or "expression"
            ).strip().lower()

            operands = str(
                turn.entities.get(
                    "arithmetic_operands",
                    "",
                )
                or ""
            ).strip()

            display_expression = str(
                turn.entities.get(
                    "arithmetic_display",
                    expression,
                )
                or expression
            ).strip()

            workflow_result = (
                calculate_arithmetic(
                    expression=expression,
                    operation=operation,
                    operands=operands,
                    display_expression=(
                        display_expression
                    ),
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

            # Result completion is checked against the structured Core result.
            # Candidate prose must not become an authoritative required claim.

            direct_response = (
                workflow_result.answer_fact
                if (
                    workflow_result
                    and workflow_result.success
                    and workflow_result.answer_fact
                )
                else (
                    workflow_result.error
                    if (
                        workflow_result
                        and workflow_result.error
                    )
                    else (
                        "I couldn't calculate that safely."
                    )
                )
            )

            acceptance_publication = None
            if workflow_result and workflow_result.success:
                # A successful Core calculation always crosses this boundary,
                # including malformed or missing candidate/evidence transports.
                publication = publish_core_result(
                    text=workflow_result.answer_fact,
                    contract=contract,
                    evidence=workflow_result.evidence,
                    path="arithmetic",
                )
                direct_response = publication.text
                acceptance_publication = publication.record

            self.conversation_state.update_from_turn(
                turn
            )

            return CoreDecision(
                turn=turn,
                epistemic_route=route,
                answer_contract=contract,
                workflow_result=workflow_result,
                direct_response=direct_response,
                acceptance_publication=acceptance_publication,
            )

        # --------------------------------------------------
        # Deterministic approved local file/folder actions
        # --------------------------------------------------

        if turn.intent in {
            "find_local_file",
            "open_local_file",
            "open_local_files",
            "select_local_file",
            "local_file_choice_required",
            "open_local_folder",
        }:
            query = str(
                turn.entities.get(
                    "local_file_query",
                    "",
                )
                or ""
            ).strip()

            resolved_path = str(
                turn.entities.get(
                    "local_file_path",
                    "",
                )
                or ""
            ).strip() or None

            resolved_paths = [
                str(
                    item
                    or ""
                ).strip()
                for item in list(
                    turn.entities.get(
                        "local_file_paths",
                        [],
                    )
                    or []
                )
                if str(
                    item
                    or ""
                ).strip()
            ]

            display_name = str(
                turn.entities.get(
                    "local_file_name",
                    "",
                )
                or ""
            ).strip()

            folder_id = str(
                turn.entities.get(
                    "local_folder_id",
                    "",
                )
                or ""
            ).strip().lower()

            if turn.intent == "find_local_file":
                workflow_result = find_local_file(
                    query=query,
                )

            elif turn.intent == "local_file_choice_required":
                candidates = list(
                    self.conversation_state
                    .active_local_file_candidates
                    or []
                )

                candidate_names = [
                    str(
                        item.get(
                            "name",
                            "",
                        )
                        or ""
                    ).strip()
                    for item in candidates
                    if str(
                        item.get(
                            "name",
                            "",
                        )
                        or ""
                    ).strip()
                ]

                if candidate_names:
                    if len(
                        candidate_names
                    ) == 2:
                        response = (
                            "I found two matching files: "
                            f"{candidate_names[0]} and "
                            f"{candidate_names[1]}. "
                            "Tell me which one you want."
                        )
                    else:
                        response = (
                            f"I found {len(candidate_names)} matching files. "
                            "Tell me which one you want."
                        )
                else:
                    response = (
                        "I don't have one unambiguous file selected yet."
                    )

                contract = build_answer_contract(
                    turn=turn,
                    route=route,
                    evidence=None,
                )

                self.conversation_state.update_from_turn(
                    turn
                )

                return CoreDecision(
                    turn=turn,
                    epistemic_route=route,
                    answer_contract=contract,
                    workflow_result=None,
                    direct_response=response,
                )

            elif turn.intent == "open_local_folder":
                workflow_result = open_trusted_folder(
                    folder_id=folder_id,
                    display_name=(
                        display_name
                        or "Folder"
                    ),
                )

            elif turn.intent == "open_local_files":
                workflow_result = open_local_files(
                    resolved_paths=resolved_paths,
                )

            elif turn.intent == "select_local_file":
                workflow_result = select_local_file(
                    resolved_path=(
                        resolved_path
                        or ""
                    ),
                    display_name=(
                        display_name
                        or None
                    ),
                )

            else:
                workflow_result = open_local_file(
                    query=(
                        query
                        or None
                    ),
                    resolved_path=resolved_path,
                )

            if (
                workflow_result
                and workflow_result.data
            ):
                selected_path = str(
                    workflow_result.data.get(
                        "selected_path",
                        "",
                    )
                    or ""
                ).strip()

                selected_name = str(
                    workflow_result.data.get(
                        "selected_name",
                        "",
                    )
                    or ""
                ).strip()

                if selected_path:
                    turn.entities[
                        "local_file_path"
                    ] = selected_path

                if selected_name:
                    turn.entities[
                        "local_file_name"
                    ] = selected_name

                matches = list(
                    workflow_result.data.get(
                        "matches",
                        [],
                    )
                    or []
                )

                if (
                    workflow_result.status
                    == "multiple_matches"
                ):
                    pending_action = (
                        "open"
                        if turn.intent == "open_local_file"
                        else "find"
                    )

                    self.conversation_state.remember_local_file_candidates(
                        matches,
                        pending_action=pending_action,
                    )

                elif (
                    selected_path
                    and turn.intent
                    != "open_local_files"
                ):
                    self.conversation_state.remember_local_file(
                        path=selected_path,
                        name=selected_name,
                    )

                elif turn.intent == "open_local_files":
                    # Opening an ambiguity set does not make the final item a
                    # truthful singular referent.
                    self.conversation_state.clear_local_file_referent()

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
                    and workflow_result.answer_fact
                )
                else (
                    workflow_result.error
                    if (
                        workflow_result
                        and workflow_result.error
                    )
                    else (
                        "I couldn't complete that local file action."
                    )
                )
            )

            # File referent truth is resolved above from workflow results,
            # but generic conversational state still needs the turn itself.
            #
            # Ambiguous file results do not put local_file_path on the turn,
            # so update_from_turn() cannot recreate a stale singular referent.
            # Unique results do carry the verified path and safely reinforce it.
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
        # Conservative trusted-browser context close
        # --------------------------------------------------

        if turn.intent == "browser_context_close_unsupported":
            site_name = str(
                turn.entities.get(
                    "browser_site_name",
                    "",
                )
                or "that browser tab"
            ).strip()

            direct_response = (
                f"I can't safely close just that {site_name} browser "
                "context yet without risking your other Chrome tabs, "
                "so I left Chrome alone."
            )

            contract = build_answer_contract(
                turn=turn,
                route=route,
            )

            contract.required_claims.append(
                direct_response
            )

            contract.allow_new_factual_claims = False
            contract.allow_follow_up_question = False

            self.conversation_state.update_from_turn(
                turn
            )

            return CoreDecision(
                turn=turn,
                epistemic_route=route,
                answer_contract=contract,
                workflow_result=None,
                direct_response=direct_response,
            )

        # --------------------------------------------------
        # Deterministic trusted browser navigation/search
        # --------------------------------------------------

        if turn.intent in {
            "browser_search",
            "browser_open",
        }:
            site_id = str(
                turn.entities.get(
                    "browser_site",
                    "google",
                )
                or "google"
            ).strip().lower()

            query = (
                str(
                    turn.entities.get(
                        "search_query",
                        "",
                    )
                    or ""
                ).strip()
                if turn.intent == "browser_search"
                else None
            )

            workflow_result = (
                open_browser_action(
                    site_id=site_id,
                    query=query,
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

            direct_response = (
                workflow_result.answer_fact
                if (
                    workflow_result
                    and workflow_result.success
                    and workflow_result.answer_fact
                )
                else (
                    workflow_result.error
                    if (
                        workflow_result
                        and workflow_result.error
                    )
                    else "I couldn't complete that browser action."
                )
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
        # Deterministic approved desktop application launch
        # --------------------------------------------------

        if turn.intent == "launch_application":
            app_name = str(
                turn.entities.get(
                    "app_name",
                    "",
                )
            ).strip().lower()

            workflow_result = (
                launch_approved_application(
                    app_name=app_name
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

            if (
                workflow_result
                and workflow_result.success
                and workflow_result.answer_fact
            ):
                direct_response = (
                    workflow_result.answer_fact
                )

            else:
                direct_response = (
                    workflow_result.error
                    if (
                        workflow_result
                        and workflow_result.error
                    )
                    else (
                        "I couldn't open that desktop target."
                    )
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
        # Deterministic installed Steam game close semantics
        # --------------------------------------------------

        if turn.intent == "close_steam_game":
            requested_title = str(
                turn.entities.get(
                    "steam_game_title",
                    "",
                )
                or ""
            ).strip()

            installed = (
                discover_installed_steam_games()
            )

            resolution = (
                resolve_installed_steam_game(
                    requested_title=requested_title,
                    games=installed,
                )
            )

            status = str(
                resolution.get(
                    "status",
                    "",
                )
                or ""
            )

            if status == "matched":
                match = resolution.get(
                    "match"
                ) or {}

                game_name = str(
                    match.get(
                        "name",
                        requested_title,
                    )
                    or requested_title
                ).strip()

                direct_response = (
                    f"I can launch {game_name}, but I don't have a "
                    "safe verified way to close Steam games yet."
                )

            elif status == "ambiguous":
                candidates = [
                    str(
                        item.get(
                            "name",
                            "",
                        )
                        or ""
                    ).strip()
                    for item in list(
                        resolution.get(
                            "candidates",
                            [],
                        )
                        or []
                    )
                    if str(
                        item.get(
                            "name",
                            "",
                        )
                        or ""
                    ).strip()
                ]

                if candidates:
                    direct_response = (
                        "I found multiple installed Steam games that could "
                        f'match "{requested_title}": '
                        + ", ".join(
                            candidates[:3]
                        )
                        + ". Be a bit more specific."
                    )
                else:
                    direct_response = (
                        "That Steam-game close request is ambiguous."
                    )

            else:
                direct_response = (
                    "I couldn't find an installed Steam game matching "
                    f'"{requested_title}".'
                )

            contract = build_answer_contract(
                turn=turn,
                route=route,
                evidence=None,
            )

            self.conversation_state.update_from_turn(
                turn
            )

            return CoreDecision(
                turn=turn,
                epistemic_route=route,
                answer_contract=contract,
                workflow_result=None,
                direct_response=direct_response,
            )

        # --------------------------------------------------
        # Deterministic Steam ambiguity confirmation + learned alias
        # --------------------------------------------------

        if turn.intent == "confirm_steam_game_alias":
            alias_query = str(
                turn.entities.get(
                    "steam_game_alias",
                    "",
                )
                or ""
            ).strip()

            expected_appid = str(
                turn.entities.get(
                    "steam_game_appid",
                    "",
                )
                or ""
            ).strip()

            game_name = str(
                turn.entities.get(
                    "steam_game_name",
                    "",
                )
                or ""
            ).strip()

            workflow_result = (
                launch_installed_steam_game(
                    requested_title=game_name
                )
            )

            if (
                workflow_result
                and workflow_result.success
            ):
                launched_appid = str(
                    workflow_result.data.get(
                        "appid",
                        "",
                    )
                    or ""
                ).strip()

                launched_name = str(
                    workflow_result.data.get(
                        "game_name",
                        game_name,
                    )
                    or game_name
                ).strip()

                if (
                    launched_appid
                    and launched_appid == expected_appid
                ):
                    set_steam_game_alias(
                        alias=alias_query,
                        appid=launched_appid,
                        game_name=launched_name,
                    )

                    self.conversation_state.clear_steam_game_candidates()

                    direct_response = (
                        workflow_result.answer_fact
                        + f' I\'ll remember "{alias_query}" as '
                        + f"{launched_name}."
                    )

                else:
                    direct_response = (
                        "The confirmed Steam game no longer matched the "
                        "verified installed AppID, so I didn't learn that alias."
                    )

            else:
                direct_response = (
                    workflow_result.error
                    if (
                        workflow_result
                        and workflow_result.error
                    )
                    else (
                        "I couldn't launch the confirmed Steam game, so I "
                        "didn't learn that alias."
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
        # Deterministic installed Steam game launch
        # --------------------------------------------------

        if turn.intent == "launch_steam_game":
            requested_title = str(
                turn.entities.get(
                    "steam_game_title",
                    "",
                )
                or ""
            ).strip()

            workflow_result = (
                launch_installed_steam_game(
                    requested_title=requested_title
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

            direct_response = (
                workflow_result.answer_fact
                if (
                    workflow_result
                    and workflow_result.success
                    and workflow_result.answer_fact
                )
                else (
                    workflow_result.error
                    if (
                        workflow_result
                        and workflow_result.error
                    )
                    else "I couldn't launch that Steam game."
                )
            )

            self.conversation_state.update_from_turn(
                turn
            )

            if (
                workflow_result
                and workflow_result.status
                == "ambiguous_game"
            ):
                resolution = (
                    workflow_result.data.get(
                        "resolution",
                        {},
                    )
                    or {}
                )

                self.conversation_state.remember_steam_game_candidates(
                    alias_query=requested_title,
                    candidates=list(
                        resolution.get(
                            "candidates",
                            [],
                        )
                        or []
                    ),
                )

            elif (
                workflow_result
                and workflow_result.success
            ):
                self.conversation_state.clear_steam_game_candidates()

            return CoreDecision(
                turn=turn,
                epistemic_route=route,
                answer_contract=contract,
                workflow_result=workflow_result,
                direct_response=direct_response,
            )

        # --------------------------------------------------
        # Deterministic desktop window control
        # --------------------------------------------------

        if turn.intent in {
            "close_application",
            "focus_application",
        }:
            app_name = str(
                turn.entities.get(
                    "app_name",
                    "",
                )
            ).strip().lower()

            action = (
                "close"
                if turn.intent == "close_application"
                else "focus"
            )

            workflow_result = (
                control_approved_application(
                    app_name=app_name,
                    action=action,
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

            if (
                workflow_result
                and workflow_result.success
                and workflow_result.answer_fact
            ):
                direct_response = (
                    workflow_result.answer_fact
                )
            else:
                direct_response = (
                    workflow_result.error
                    if (
                        workflow_result
                        and workflow_result.error
                    )
                    else (
                        "I couldn't complete that desktop action."
                    )
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
        # Deterministic targeted Gmail search
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

            # Domain-specific Gmail referents are remembered from verified
            # workflow evidence BEFORE generic active intent can move on.
            self.conversation_state.remember_email_search_result(
                turn=turn,
                workflow_result=workflow_result,
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
        # Deterministic Gmail body selection + read
        # --------------------------------------------------

        if turn.intent == "email_read":
            message_id = (
                self._email_message_id_for_turn(
                    turn
                )
            )

            search_text = (
                self._email_search_text_for_turn(
                    turn
                )
            )

            # If the router did not already resolve a verified message ID,
            # Core may search the explicitly named target now.
            if (
                not message_id
                and search_text
            ):
                days = self._email_days_for_turn(
                    turn
                )

                time_scope = (
                    self._email_time_scope_for_turn(
                        turn
                    )
                )

                search_result = search_email(
                    search_text=search_text,
                    days=days,
                    time_scope=time_scope,
                )

                # Reuse the normal Gmail referent structure even though the
                # current task is email_read rather than email_search.
                search_turn = TurnState(
                    raw_text=turn.raw_text
                )
                search_turn.intent = "email_search"
                search_turn.entities[
                    "search_text"
                ] = search_text
                search_turn.entities[
                    "days"
                ] = str(
                    days
                )
                search_turn.entities[
                    "time_scope"
                ] = time_scope

                self.conversation_state.remember_email_search_result(
                    turn=search_turn,
                    workflow_result=search_result,
                )

                if (
                    not search_result
                    or not search_result.success
                ):
                    contract = build_answer_contract(
                        turn=turn,
                        route=route,
                        evidence=(
                            search_result.evidence
                            if search_result
                            else None
                        ),
                    )

                    self.conversation_state.update_from_turn(
                        turn
                    )

                    return CoreDecision(
                        turn=turn,
                        epistemic_route=route,
                        answer_contract=contract,
                        workflow_result=search_result,
                        direct_response=(
                            "I couldn't check Gmail for that email just now."
                        ),
                    )

                if (
                    search_result.status
                    == "no_match"
                ):
                    contract = build_answer_contract(
                        turn=turn,
                        route=route,
                        evidence=search_result.evidence,
                    )

                    self.conversation_state.update_from_turn(
                        turn
                    )

                    return CoreDecision(
                        turn=turn,
                        epistemic_route=route,
                        answer_contract=contract,
                        workflow_result=search_result,
                        direct_response=(
                            search_result.answer_fact
                            or (
                                "I couldn't find a matching email to read."
                            )
                        ),
                    )

                email_selector = str(
                    turn.entities.get(
                        "email_selector",
                        "",
                    )
                    or ""
                ).strip().lower()

                if email_selector:
                    resolved = (
                        self.conversation_state
                        .resolve_email_message_selection(
                            selector=email_selector,
                            target=search_text,
                            allow_bare=False,
                        )
                    )
                else:
                    resolved = (
                        self.conversation_state
                        .resolve_single_email_message(
                            target=search_text,
                            allow_bare=False,
                        )
                    )

                if resolved:
                    message_id = str(
                        resolved.get(
                            "message_id"
                        )
                        or ""
                    ).strip()

            if not message_id:
                # Distinguish "I know the target but there are several matches"
                # from a completely unresolved bare deictic.
                context = (
                    self.conversation_state
                    .find_email_referent(
                        target=search_text,
                        require_message=True,
                        allow_bare=(
                            search_text is None
                        ),
                    )
                )

                messages = (
                    list(
                        context.get(
                            "messages",
                            [],
                        )
                        or []
                    )
                    if context
                    else []
                )

                contract = build_answer_contract(
                    turn=turn,
                    route=route,
                )

                self.conversation_state.update_from_turn(
                    turn
                )

                if len(
                    messages
                ) > 1:
                    subjects = [
                        str(
                            item.get(
                                "subject"
                            )
                            or "(No subject)"
                        ).strip()
                        for item in messages[
                            :4
                        ]
                    ]

                    return CoreDecision(
                        turn=turn,
                        epistemic_route=route,
                        answer_contract=contract,
                        needs_clarification=True,
                        clarification_question=(
                            "I found more than one matching email. Which one do you mean: "
                            + "; ".join(
                                subjects
                            )
                            + "?"
                        ),
                    )

                return CoreDecision(
                    turn=turn,
                    epistemic_route=route,
                    answer_contract=contract,
                    needs_clarification=True,
                    clarification_question=(
                        "Which email do you want me to read?"
                    ),
                )

            print(
                "[Tool] Mairon Core required: read_email"
            )

            workflow_result = (
                read_selected_email(
                    message_id=message_id
                )
            )

            contract = (
                self._strict_email_read_contract(
                    turn=turn,
                    route=route,
                    workflow_result=workflow_result,
                )
            )

            if (
                workflow_result
                and not workflow_result.success
            ):
                direct_response = (
                    workflow_result.error
                    or (
                        "I couldn't read that Gmail message just now."
                    )
                )

            # Successful body reads deliberately do NOT receive a canned direct
            # response. Qwen may summarise/explain the verified body under the
            # strict Answer Contract.
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
        # Deterministic user self-correction
        # --------------------------------------------------

        if turn.intent == "self_correction":
            contract = build_answer_contract(
                turn=turn,
                route=route,
            )

            direct_response = (
                build_self_correction_response(
                    user_input
                )
            )

            self.conversation_state.update_from_turn(
                turn
            )

            return CoreDecision(
                turn=turn,
                epistemic_route=route,
                answer_contract=contract,
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
