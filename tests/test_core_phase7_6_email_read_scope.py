import sys
import ast
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SRC_DIR),
    )


from core.answer_contract_runtime import (
    AnswerContractRuntime,
)
from ai import ollama_provider


def _no_recommendations_contract():
    return AnswerContractRuntime(
        task="respond",
        speech_act="question",
        intent="email_read",
        subject="selected Gmail message",
        authority="gmail",
        epistemic_mode="tool_verified",
        allow_recommendations=False,
        allow_new_factual_claims=False,
        allow_follow_up_question=False,
        source="structured",
    )


def run():
    contract = _no_recommendations_contract()

    # --------------------------------------------------
    # 1. Bare imperative advice is rejected.
    # --------------------------------------------------

    bad = (
        "Typical corporate update - read the policy page or ignore it.",
        "Nothing urgent. Check the settings before Sunday.",
        "FYI only — review the details when you get a chance.",
        "No action is required; click the link if you care.",
    )

    for draft in bad:
        violations = (
            ollama_provider
            .find_forbidden_recommendation_violations(
                response_text=draft,
                core_answer_contract=contract,
            )
        )

        assert violations, draft

    # --------------------------------------------------
    # 2. Source-authored imperative instructions remain reportable.
    # --------------------------------------------------

    good = (
        "The email says: review the changes before 5 PM.",
        "The message says you should verify your account.",
        "The sender instructed you to reply by Friday.",
    )

    for draft in good:
        violations = (
            ollama_provider
            .find_forbidden_recommendation_violations(
                response_text=draft,
                core_answer_contract=contract,
            )
        )

        assert not violations, (
            draft,
            violations,
        )

    # --------------------------------------------------
    # 3. Pure summary remains valid.
    # --------------------------------------------------

    neutral = (
        "PayPal is updating its legal agreements. "
        "The email says no action is required."
    )

    assert not (
        ollama_provider
        .find_forbidden_recommendation_violations(
            response_text=neutral,
            core_answer_contract=contract,
        )
    )

    # --------------------------------------------------
    # 4. No benchmark-specific production strings.
    # --------------------------------------------------

    provider_path = (
        SRC_DIR
        / "ai"
        / "ollama_provider.py"
    )

    provider_source = provider_path.read_text(
        encoding="utf-8",
    )

    tree = ast.parse(
        provider_source,
        filename=str(
            provider_path
        ),
    )

    executable_strings = []

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.Constant,
        ):
            continue

        if not isinstance(
            node.value,
            str,
        ):
            continue

        # Ignore module/function/class docstrings. They are documentation,
        # not executable benchmark-specific behaviour.
        parent_is_docstring = False

        for owner in ast.walk(
            tree
        ):
            body = getattr(
                owner,
                "body",
                None,
            )

            if not isinstance(
                body,
                list,
            ) or not body:
                continue

            first = body[0]

            if (
                isinstance(
                    first,
                    ast.Expr,
                )
                and isinstance(
                    first.value,
                    ast.Constant,
                )
                and isinstance(
                    first.value.value,
                    str,
                )
                and first.value is node
            ):
                parent_is_docstring = True
                break

        if not parent_is_docstring:
            executable_strings.append(
                node.value.lower()
            )

    executable_text = "\n".join(
        executable_strings
    )

    for forbidden in (
        "read the policy page or ignore it",
        "typical corporate update",
        "paypal yesterday",
        "10.97s",
        "6.57s",
    ):
        assert forbidden not in executable_text

    print(
        "Mairon Phase 7.6 no-recommendation imperative "
        "enforcement tests: PASS"
    )


if __name__ == "__main__":
    run()
