"""Internal results of scoped typed semantic validation.

These values supplement Core acceptance; they are neither evidence producers
nor publication decisions. Validators must cover an entire original unit and
derive obligations from trusted evidence and contracts, never candidate origin.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Tuple


@dataclass(frozen=True)
class TypedUnitValidation:
    evidence_ids: Tuple[str, ...] = ()
    obligations: Tuple[str, ...] = ()
    violated_invariants: Tuple[str, ...] = ()
    reasons: Tuple[str, ...] = ()
    limitation_preserved: bool = False

    def __post_init__(self):
        for name in ("evidence_ids", "obligations", "violated_invariants", "reasons"):
            value = getattr(self, name)
            if not isinstance(value, (tuple, list)) or any(not isinstance(item, str) for item in value):
                raise TypeError(f"{name} must contain strings")
            object.__setattr__(self, name, tuple(value))
        if type(self.limitation_preserved) is not bool:
            raise TypeError("limitation_preserved must be a bool")


@dataclass(frozen=True)
class TypedEvaluation:
    validator: str
    units: Mapping[int, TypedUnitValidation]
    required_claim_obligations: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    completion_obligations: Tuple[str, ...] = ()
    global_violations: Tuple[str, ...] = ()
    global_reasons: Tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.validator, str) or not self.validator:
            raise TypeError("validator must be a nonempty identifier")
        if not isinstance(self.units, Mapping) or any(
            type(index) is not int or index < 1 or not isinstance(value, TypedUnitValidation)
            for index, value in self.units.items()
        ):
            raise TypeError("Typed units require positive indexes and typed validations")
        requirements = {}
        for claim, obligations in self.required_claim_obligations.items():
            if not isinstance(claim, str) or not isinstance(obligations, (tuple, list)) or any(
                not isinstance(value, str) for value in obligations
            ):
                raise TypeError("Required claim obligations must be string sequences")
            requirements[claim] = tuple(obligations)
        object.__setattr__(self, "units", MappingProxyType(dict(self.units)))
        object.__setattr__(self, "required_claim_obligations", MappingProxyType(requirements))
        for name in ("completion_obligations", "global_violations", "global_reasons"):
            value = getattr(self, name)
            if not isinstance(value, (tuple, list)) or any(not isinstance(item, str) for item in value):
                raise TypeError(f"{name} must contain strings")
            object.__setattr__(self, name, tuple(value))


def validate_typed_evidence(candidate, units) -> Tuple[TypedEvaluation, ...]:
    # Domain modules depend on this small model, not on evaluator internals.
    from core.acceptance_results import validate_results
    from core.acceptance_limits import validate_limits
    return tuple(result for result in (
        validate_results(candidate, units), validate_limits(candidate, units),
    ) if result is not None)
