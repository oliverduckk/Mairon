import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


CORE_ANSWER_CONTRACT_MARKER = (
    "CORE ANSWER CONTRACT:"
)


def _normalise_bool(
    value: Any,
    default: bool = False,
) -> bool:
    if isinstance(
        value,
        bool,
    ):
        return value

    text = str(
        value or ""
    ).strip().lower()

    if text in {
        "true",
        "yes",
        "1",
        "on",
    }:
        return True

    if text in {
        "false",
        "no",
        "0",
        "off",
    }:
        return False

    return bool(
        default
    )


def _normalise_optional_text(
    value: Any,
) -> Optional[str]:
    if value is None:
        return None

    text = str(
        value
    ).strip()

    if not text:
        return None

    if text.lower() == "none":
        return None

    return text


@dataclass(frozen=True)
class AnswerContractRuntime:
    """
    Structured runtime view of one turn-scoped Core Answer Contract.

    Core/provider logic consumes THIS object.

    The rendered text form exists only because the language model needs
    human-readable instructions. Validators, routing, grounding, and
    provider policy must not repeatedly parse that prose.

    `source` is diagnostic only:
    - "structured" means it came directly from an AnswerContract-like object;
    - "legacy_text" means it was reconstructed once at the provider boundary
      for backward compatibility with the current router interface.
    """

    task: str = "respond"
    speech_act: str = "unknown"
    intent: str = "unknown"
    subject: Optional[str] = None

    authority: str = "unknown"
    epistemic_mode: str = "unknown"

    allow_recommendations: bool = False
    allow_new_factual_claims: bool = False
    allow_follow_up_question: bool = False

    model_instruction: str = ""

    required_claims: Tuple[str, ...] = field(
        default_factory=tuple
    )

    forbidden_behaviours: Tuple[str, ...] = field(
        default_factory=tuple
    )

    resolved_referents: Dict[str, str] = field(
        default_factory=dict
    )

    source: str = "structured"

    def field_value(
        self,
        field_name: str,
    ) -> Optional[str]:
        """
        Compatibility accessor for older provider helpers.

        This maps known rendered field labels to structured values.
        It does NOT parse model_instruction.
        """

        key = str(
            field_name or ""
        ).strip().lower()

        mapping = {
            "task": self.task,
            "speech act": self.speech_act,
            "intent": self.intent,
            "subject": (
                self.subject
                or "none"
            ),
            "factual authority": (
                self.authority
            ),
            "epistemic mode": (
                self.epistemic_mode
            ),
            "recommendations allowed": (
                str(
                    self.allow_recommendations
                ).lower()
            ),
            (
                "new unsupported factual "
                "claims allowed"
            ): (
                str(
                    self.allow_new_factual_claims
                ).lower()
            ),
            "follow-up question allowed": (
                str(
                    self.allow_follow_up_question
                ).lower()
            ),
        }

        return mapping.get(
            key
        )


def runtime_from_answer_contract(
    contract: Any,
) -> Optional[
    AnswerContractRuntime
]:
    """
    Convert a real AnswerContract-like object directly into structured
    runtime state.

    Duck typing is intentional so this module does not create an import
    cycle back into core.answer_contract.
    """

    if contract is None:
        return None

    if isinstance(
        contract,
        AnswerContractRuntime,
    ):
        return contract

    required_attributes = (
        "task",
        "speech_act",
        "intent",
        "authority",
        "epistemic_mode",
        "allow_recommendations",
        "allow_new_factual_claims",
        "allow_follow_up_question",
        "to_model_instruction",
    )

    if not all(
        hasattr(
            contract,
            attribute,
        )
        for attribute in required_attributes
    ):
        return None

    instruction = (
        contract.to_model_instruction()
    )

    return AnswerContractRuntime(
        task=str(
            getattr(
                contract,
                "task",
                "respond",
            )
            or "respond"
        ),
        speech_act=str(
            getattr(
                contract,
                "speech_act",
                "unknown",
            )
            or "unknown"
        ),
        intent=str(
            getattr(
                contract,
                "intent",
                "unknown",
            )
            or "unknown"
        ),
        subject=_normalise_optional_text(
            getattr(
                contract,
                "subject",
                None,
            )
        ),
        authority=str(
            getattr(
                contract,
                "authority",
                "unknown",
            )
            or "unknown"
        ),
        epistemic_mode=str(
            getattr(
                contract,
                "epistemic_mode",
                "unknown",
            )
            or "unknown"
        ),
        allow_recommendations=bool(
            getattr(
                contract,
                "allow_recommendations",
                False,
            )
        ),
        allow_new_factual_claims=bool(
            getattr(
                contract,
                "allow_new_factual_claims",
                False,
            )
        ),
        allow_follow_up_question=bool(
            getattr(
                contract,
                "allow_follow_up_question",
                False,
            )
        ),
        model_instruction=str(
            instruction or ""
        ).strip(),
        required_claims=tuple(
            str(
                item
            )
            for item in (
                getattr(
                    contract,
                    "required_claims",
                    [],
                )
                or []
            )
        ),
        forbidden_behaviours=tuple(
            str(
                item
            )
            for item in (
                getattr(
                    contract,
                    "forbidden_behaviours",
                    [],
                )
                or []
            )
        ),
        resolved_referents=dict(
            getattr(
                contract,
                "resolved_referents",
                {},
            )
            or {}
        ),
        source="structured",
    )


def _parse_field_lines(
    contract_text: str,
) -> Dict[str, str]:
    """
    Legacy compatibility parser.

    IMPORTANT:
    This is the ONE place in Mairon Core that may interpret the rendered
    Answer Contract prose. The current router still transports contracts
    inside the instruction string, so provider ingress uses this once.

    Internal modules must consume AnswerContractRuntime instead.
    """

    fields = {}

    for raw_line in str(
        contract_text or ""
    ).splitlines():
        line = raw_line.strip()

        if not line:
            continue

        # Presentation bullets are not part of a field name.
        comparable = line.lstrip(
            "- "
        ).strip()

        if ":" not in comparable:
            continue

        name, value = comparable.split(
            ":",
            1,
        )

        name = name.strip().lower()
        value = value.strip()

        if (
            name
            and name not in fields
        ):
            fields[
                name
            ] = value

    return fields


def _parse_resolved_referents(
    contract_text: str,
) -> Dict[str, str]:
    """
    Transitional parser for the rendered resolved-reference section.

    This lives beside _parse_field_lines because the current main/router seam
    still transports Answer Contracts as text. Once the actual AnswerContract
    object crosses that seam directly, both legacy parsers can disappear.
    """

    resolved = {}
    in_section = False

    for raw_line in str(
        contract_text
        or ""
    ).splitlines():
        line = raw_line.strip()

        if not line:
            continue

        if line == (
            "RESOLVED CONVERSATION REFERENCES:"
        ):
            in_section = True
            continue

        if not in_section:
            continue

        # A new all-caps section header ends this section.
        if (
            line.endswith(":")
            and line.upper() == line
        ):
            break

        match = re.match(
            r"^-\s*['\"](?P<pronoun>[^'\"]+)['\"]\s+"
            r"refers\s+to:\s*(?P<referent>.+?)\s*$",
            line,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        pronoun = (
            match.group(
                "pronoun"
            )
            or ""
        ).strip()

        referent = (
            match.group(
                "referent"
            )
            or ""
        ).strip()

        if (
            pronoun
            and referent
        ):
            resolved[
                pronoun
            ] = referent

    return resolved


def runtime_from_legacy_text(
    contract_text: Optional[str],
) -> Optional[
    AnswerContractRuntime
]:
    """
    Reconstruct structured runtime state from the old rendered contract
    transport format.

    This exists only until the router/provider seam carries the
    AnswerContract object directly.
    """

    text = str(
        contract_text or ""
    ).strip()

    if not text:
        return None

    if not text.lstrip().startswith(
        CORE_ANSWER_CONTRACT_MARKER
    ):
        return None

    fields = _parse_field_lines(
        text
    )

    return AnswerContractRuntime(
        task=fields.get(
            "task",
            "respond",
        ),
        speech_act=fields.get(
            "speech act",
            "unknown",
        ),
        intent=fields.get(
            "intent",
            "unknown",
        ),
        subject=_normalise_optional_text(
            fields.get(
                "subject"
            )
        ),
        authority=fields.get(
            "factual authority",
            "unknown",
        ),
        epistemic_mode=fields.get(
            "epistemic mode",
            "unknown",
        ),
        allow_recommendations=(
            _normalise_bool(
                fields.get(
                    "recommendations allowed"
                ),
                default=False,
            )
        ),
        allow_new_factual_claims=(
            _normalise_bool(
                fields.get(
                    (
                        "new unsupported factual "
                        "claims allowed"
                    )
                ),
                default=False,
            )
        ),
        allow_follow_up_question=(
            _normalise_bool(
                fields.get(
                    "follow-up question allowed"
                ),
                default=False,
            )
        ),
        model_instruction=text,
        resolved_referents=(
            _parse_resolved_referents(
                text
            )
        ),
        source="legacy_text",
    )


def coerce_answer_contract_runtime(
    contract: Any,
) -> Optional[
    AnswerContractRuntime
]:
    """
    Accept either:
    - AnswerContractRuntime;
    - a real AnswerContract-like object;
    - legacy rendered contract text.

    New Core code should prefer the first two.
    """

    if contract is None:
        return None

    if isinstance(
        contract,
        AnswerContractRuntime,
    ):
        return contract

    structured = (
        runtime_from_answer_contract(
            contract
        )
    )

    if structured is not None:
        return structured

    if isinstance(
        contract,
        str,
    ):
        return (
            runtime_from_legacy_text(
                contract
            )
        )

    return None


def render_answer_contract(
    contract: Any,
) -> str:
    """
    Render a contract for the language model.

    Core logic should not inspect this string.
    """

    runtime = (
        coerce_answer_contract_runtime(
            contract
        )
    )

    if runtime is None:
        return ""

    return str(
        runtime.model_instruction
        or ""
    ).strip()


def contract_field_value(
    contract: Any,
    field_name: str,
) -> Optional[str]:
    """
    Shared compatibility accessor.

    No caller outside this module needs to know whether the transport
    was structured or legacy text.
    """

    runtime = (
        coerce_answer_contract_runtime(
            contract
        )
    )

    if runtime is None:
        return None

    return runtime.field_value(
        field_name
    )
