import ast
import sys
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


from core.claim_grounding import (
    find_incidental_public_attribution_violations,
)


def _load_provider_function(provider_text, function_name):
    tree = ast.parse(provider_text)

    node = next(
        node
        for node in tree.body
        if isinstance(
            node,
            ast.FunctionDef,
        )
        and node.name == function_name
    )

    namespace = {}

    exec(
        compile(
            ast.Module(
                body=[node],
                type_ignores=[],
            ),
            "ollama_provider.py",
            "exec",
        ),
        namespace,
    )

    return namespace[
        function_name
    ]


def run():
    # --------------------------------------------------
    # 1. Opinion lane must stay fast: Qwen thinking is disabled.
    # --------------------------------------------------
    provider_path = (
        PROJECT_ROOT
        / "src"
        / "ai"
        / "ollama_provider.py"
    )

    provider_text = provider_path.read_text(
        encoding="utf-8"
    )

    build_direct_think_setting = (
        _load_provider_function(
            provider_text,
            "build_direct_think_setting",
        )
    )

    assert (
        build_direct_think_setting(
            "share_opinion",
            model_name="qwen3.5:9b",
        )
        is False
    )

    # The fast factual lane remains unchanged by this cleanup.
    assert (
        build_direct_think_setting(
            "factual_question",
            model_name="qwen3.5:9b",
        )
        is False
    )

    # Do not globally disable hidden reasoning for every possible lane.
    assert (
        build_direct_think_setting(
            "recommendation_request",
            model_name="qwen3.5:9b",
        )
        is None
    )

    # Acceptance cleanup 3 rewrote the opinion-lane instruction for
    # compactness/latency, so do not freeze the old heading string.
    # Verify the dedicated opinion response-mode block and the factual
    # hygiene guarantee still exist.
    assert (
        'if core_intent == "share_opinion":'
        in provider_text
    )

    assert (
        "fabricated credits are not"
        in provider_text.lower()
    )

    # --------------------------------------------------
    # 2. Exact live hallucination: invented named era/credit is blocked.
    # --------------------------------------------------
    prompt = "What is your top 3 mangas?"

    bad_era_draft = (
        "Chainsaw Man, Berserk (post-Masamune era), and Monster."
    )

    violations = (
        find_incidental_public_attribution_violations(
            user_input=prompt,
            draft=bad_era_draft,
            core_answer_contract=None,
            conversation=[],
        )
    )

    assert any(
        "incidental public attribution" in violation
        and "Masamune" in violation
        and "creative-era" in violation
        for violation in violations
    ), violations

    # A plain subjective manga ranking remains allowed.
    safe_draft = (
        "Chainsaw Man, Berserk, and Monster. That's my three."
    )

    assert (
        find_incidental_public_attribution_violations(
            user_input=prompt,
            draft=safe_draft,
            core_answer_contract=None,
            conversation=[],
        )
        == []
    )

    # If Oliver himself supplied the named era/credit label, Core may repeat it.
    grounded_prompt = (
        "I call it the post-Miura era of Berserk. What do you think about it?"
    )

    grounded_draft = (
        "The post-Miura era is a difficult thing to judge in isolation."
    )

    assert (
        find_incidental_public_attribution_violations(
            user_input=grounded_prompt,
            draft=grounded_draft,
            core_answer_contract=None,
            conversation=[],
        )
        == []
    )

    print(
        "Mairon acceptance cleanup 2 latency/fact-hygiene tests: PASS"
    )


if __name__ == "__main__":
    run()
