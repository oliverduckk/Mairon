"""S1: Core-owned, turn-scoped authority for provider continuation.

This is an internal capability boundary, not an authentication token or a
replacement for S2 executor admission / S3 cloud-export admission. A provider's
instructions and old conversation history can never create a PreparedAuthority.
"""
from dataclasses import dataclass
from typing import Any, Optional

from core.answer_contract_runtime import (
    AnswerContractRuntime,
    runtime_from_answer_contract,
)


class CoreAuthorityUnavailable(RuntimeError):
    """No trusted prepared authority exists for the attempted provider turn."""


@dataclass(frozen=True)
class PreparationOutcome:
    status: str  # prepared, direct, unavailable
    decision: Any = None
    stage: str = ""
    possible_prior_effect: bool = False


def prepare_core_turn(core: Any, user_text: str) -> PreparationOutcome:
    """Never substitute a model route for failed Core preparation.

    Core preparation can itself invoke workflows. A thrown exception does not
    prove a workflow was never started, so any failure is potentially uncertain.
    """
    try:
        decision = core.prepare_turn(user_text)
    except Exception:
        return PreparationOutcome(
            status="unavailable", stage="core_preparation",
            possible_prior_effect=True,
        )
    if decision is None or getattr(decision, "turn", None) is None or getattr(
        decision, "epistemic_route", None
    ) is None:
        return PreparationOutcome(
            status="unavailable", stage="missing_core_decision",
            possible_prior_effect=True,
        )
    if getattr(decision, "needs_clarification", False) or getattr(
        decision, "direct_response", None
    ) is not None:
        return PreparationOutcome(status="direct", decision=decision)
    return PreparationOutcome(status="prepared", decision=decision)


@dataclass(frozen=True)
class PreparedAuthority:
    """Trusted handoff: renderable instructions AND non-model obligations.

    The original contract/evidence are retained for trusted verification and
    provenance. The runtime is deliberately structured, never legacy-parsed.
    """
    runtime: AnswerContractRuntime
    contract: Any
    evidence: Any
    verification_required: bool
    private_data_required: bool
    live_data_required: bool

    def require_local(self) -> None:
        _require_typed_authority(self)

    def require_cloud(self) -> None:
        _require_typed_authority(self)
        r = self.runtime
        # Cloud presently lacks the local provider's specialised enforcers.
        # These requirements must not be relaxed to mere prompt instructions.
        if (
            self.verification_required
            or self.private_data_required
            or self.live_data_required
            or bool(r.required_claims)
            or bool(r.verified_evidence_claims)
            or bool(r.metadata)
            or r.epistemic_mode not in {
                "conversation", "classify_then_verify", "subjective",
            }
        ):
            raise CoreAuthorityUnavailable(
                "The cloud provider cannot satisfy this turn's required Core obligations."
            )


def _require_typed_authority(authority: Any) -> None:
    if not isinstance(authority, PreparedAuthority):
        raise CoreAuthorityUnavailable("Trusted Core authority is unavailable.")
    r = authority.runtime
    if (
        not isinstance(r, AnswerContractRuntime)
        or r.source != "structured"
        or not r.authority or r.authority.lower() == "unknown"
        or not r.epistemic_mode or r.epistemic_mode.lower() == "unknown"
        or not r.intent or r.intent.lower() == "unknown"
        or not r.model_instruction
    ):
        raise CoreAuthorityUnavailable("Required typed Core authority is incomplete.")


def seal_prepared_turn(decision: Any) -> PreparedAuthority:
    """Validate and snapshot Core's final post-policy contract.

    Call after application-owned conversation policy has modified the contract.
    If rendering or conversion raises, the caller must fail closed.
    """
    contract = getattr(decision, "answer_contract", None)
    runtime = runtime_from_answer_contract(contract)
    route = getattr(decision, "epistemic_route", None)
    turn = getattr(decision, "turn", None)
    if runtime is None or route is None or turn is None:
        raise CoreAuthorityUnavailable("Prepared turn lacks a typed Core contract.")
    if (
        runtime.authority != getattr(route, "authority", None)
        or runtime.epistemic_mode != getattr(route, "mode", None)
        or runtime.intent != getattr(turn, "intent", None)
    ):
        raise CoreAuthorityUnavailable("Core authority/contract fields disagree.")
    authority = PreparedAuthority(
        runtime=runtime,
        contract=contract,
        evidence=getattr(contract, "evidence", None),
        verification_required=bool(getattr(route, "verification_required", False)),
        private_data_required=bool(getattr(route, "private_data_required", False)),
        live_data_required=bool(getattr(route, "live_data_required", False)),
    )
    _require_typed_authority(authority)
    return authority


CORE_UNAVAILABLE_MESSAGE = (
    "I couldn't safely prepare that request, so I haven't sent it to a model "
    "or tried the action again. An earlier Core operation may have started; "
    "its outcome needs checking before retrying."
)
