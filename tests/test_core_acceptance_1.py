import ast
import re
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


from core.intent_router import classify_turn
from core.claim_grounding import (
    find_incidental_public_attribution_violations,
)


def _runtime_for_intent(
    intent,
):
    """
    Tiny contract stub sufficient for grounding-text rendering helpers.

    The public-attribution guard only needs the contract to be renderable;
    None is also supported, so tests deliberately use None below to avoid
    coupling this acceptance regression to unrelated AnswerContract internals.
    """

    return None


def run():
    # --------------------------------------------------
    # 1. Assistant preference/ranking questions are subjective,
    #    not generic factual questions.
    # --------------------------------------------------
    preference_prompts = (
        "What is your top 3 mangas?",
        "What are your top 3 anime?",
        "What's your favourite manga?",
        "What is your favorite game?",
        "Which one do you prefer?",
        "What do you think about Berserk?",
        "How would you rank these three?",
        "Which would you pick?",
    )

    for prompt in preference_prompts:
        turn = classify_turn(
            prompt
        )

        assert turn.intent == "share_opinion", (
            prompt,
            turn.intent,
            turn.reasons,
        )

        assert turn.factuality == "subjective", (
            prompt,
            turn.factuality,
        )

    # Ordinary public facts remain on the factual lane.
    factual = classify_turn(
        "What is the capital of Canada?"
    )
    assert factual.intent == "factual_question", factual.intent

    inference = classify_turn(
        "What do you think happened to the connection?"
    )
    assert inference.intent == "factual_question", (
        inference.intent
    )

    # Explicit authorship questions are ALSO factual. The attribution guard
    # must not prevent the requested answer itself.
    attribution_question = classify_turn(
        "Who wrote Vagabond?"
    )
    assert attribution_question.intent == "factual_question", (
        attribution_question.intent
    )

    # --------------------------------------------------
    # 2. Exact live hallucination: invented creator attribution is blocked.
    # --------------------------------------------------
    user_input = "What is your top 3 mangas?"

    bad_draft = (
        "1. Berserk. 2. Monster. 3. Vagabond — because "
        "Murakami Genshaku's art alone justifies the pick."
    )

    violations = (
        find_incidental_public_attribution_violations(
            user_input=user_input,
            draft=bad_draft,
            core_answer_contract=None,
            conversation=[],
        )
    )

    assert any(
        "incidental public attribution" in violation
        and "Murakami Genshaku" in violation
        for violation in violations
    ), violations

    # Subjective title picks themselves remain allowed.
    safe_opinion = (
        "Berserk, Monster, and Vagabond. That's a ridiculous top three."
    )

    assert (
        find_incidental_public_attribution_violations(
            user_input=user_input,
            draft=safe_opinion,
            core_answer_contract=None,
            conversation=[],
        )
        == []
    )

    # High-confidence explicit byline shapes are also guarded.
    byline_draft = (
        "I'd take Berserk first; it was written by Fake Author Name."
    )

    byline_violations = (
        find_incidental_public_attribution_violations(
            user_input=user_input,
            draft=byline_draft,
            core_answer_contract=None,
            conversation=[],
        )
    )

    assert any(
        "Fake Author Name" in violation
        for violation in byline_violations
    ), byline_violations

    # If Oliver supplied the creator name himself, Core may repeat it.
    grounded_user = (
        "Takehiko Inoue created Vagabond. What do you think about the manga?"
    )

    grounded_draft = (
        "Takehiko Inoue's art is a huge part of why it works for me."
    )

    assert (
        find_incidental_public_attribution_violations(
            user_input=grounded_user,
            draft=grounded_draft,
            core_answer_contract=None,
            conversation=[],
        )
        == []
    )

    # If authorship is Oliver's explicit factual question, allow the factual
    # lane to answer it from its normal knowledge/epistemic path.
    explicit_attribution_draft = (
        "Vagabond was written by Takehiko Inoue."
    )

    assert (
        find_incidental_public_attribution_violations(
            user_input="Who wrote Vagabond?",
            draft=explicit_attribution_draft,
            core_answer_contract=None,
            conversation=[],
        )
        == []
    )

    # --------------------------------------------------
    # 3. Provider applies the guard universally, before lane-specific
    #    semantic/factual verifiers.
    # --------------------------------------------------
    provider_text = (
        PROJECT_ROOT
        / "src"
        / "ai"
        / "ollama_provider.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "find_incidental_public_attribution_violations"
        in provider_text
    )

    call_position = provider_text.find(
        "find_incidental_public_attribution_violations("
    )

    core_verify_position = provider_text.find(
        "if core_grounding_required:",
        call_position,
    )

    assert call_position != -1
    assert core_verify_position != -1
    assert call_position < core_verify_position

    # The fast factual cap stays exactly where it was; the fix is routing,
    # not globally making factual questions slower/longer.
    tree = ast.parse(
        provider_text
    )

    generation_node = next(
        node
        for node in tree.body
        if isinstance(
            node,
            ast.FunctionDef,
        )
        and node.name == "build_direct_generation_options"
    )

    namespace = {}

    exec(
        compile(
            ast.Module(
                body=[generation_node],
                type_ignores=[],
            ),
            "ollama_provider.py",
            "exec",
        ),
        namespace,
    )

    assert namespace[
        "build_direct_generation_options"
    ](
        "factual_question"
    ) == {
        "temperature": 0.2,
        "num_predict": 96,
    }

    # Acceptance cleanup 3 intentionally gives lightweight opinion /
    # preference turns a bounded fast-generation profile. Cleanup 1 owns
    # routing and attribution behaviour, so this historical regression should
    # verify the current supported profile rather than freezing the old
    # "no options" implementation detail.
    assert namespace[
        "build_direct_generation_options"
    ](
        "share_opinion"
    ) == {
        "temperature": 0.35,
        "num_predict": 112,
    }

    print(
        "Mairon acceptance cleanup 1 routing/attribution tests: PASS"
    )


if __name__ == "__main__":
    run()
