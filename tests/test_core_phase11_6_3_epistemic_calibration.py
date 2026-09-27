"""Phase 11.6.3: epistemic calibration and no-public-search private-state checks.

Run at Mairon repository root:
    python tests/test_core_phase11_6_3_epistemic_calibration.py
"""

import ast
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.epistemic_calibration import (
    classify_private_user_question,
    contains_unjustified_lexical_denial,
    extract_lexical_query_term,
    is_inaccessible_private_state_question,
    repair_unjustified_lexical_denial,
)
from core.epistemic_router import (
    classify_factual_authority,
    factual_question_requires_live_data,
    route_epistemic_authority,
)
from core.intent_router import classify_turn
from core.orchestrator import MaironCore


class _PriorUserOnly:
    active_intent = None
    active_entities = {}

    def __init__(self, previous_user_text=None):
        self.previous_user_text = previous_user_text

    def latest_user_turn(self):
        if self.previous_user_text is None:
            return None
        return {"text": self.previous_user_text}


def _turn(text, previous_user_text=None):
    return classify_turn(text, _PriorUserOnly(previous_user_text))


def run():
    # Integration smoke: every import of the shared module in this exact
    # checkout must resolve BEFORE we spend time on the full suite.
    import core.epistemic_calibration as calibration
    for root in (SRC_ROOT / "core", SRC_ROOT / "ai"):
        if not root.is_dir():
            continue
        for source_file in root.rglob("*.py"):
            parsed = ast.parse(source_file.read_text(encoding="utf-8"))
            for node in ast.walk(parsed):
                if isinstance(node, ast.ImportFrom) and node.module == "core.epistemic_calibration":
                    for imported in node.names:
                        assert hasattr(calibration, imported.name), (
                            str(source_file), imported.name
                        )

    # A. The guard is generic; it neither hardcodes the benchmark's invented
    # word nor invents a dictionary to decide which tokens are legitimate.
    for prompt, expected_term in (
        ("What does quorblax mean?", "quorblax"),
        ("What does 'gremlify' mean?", "gremlify"),
        ("Define photomimesis.", "photomimesis"),
        ("Is oobleflarp a real word?", "oobleflarp"),
        ("What's the meaning of quibble?", "quibble"),
    ):
        assert extract_lexical_query_term(prompt) == expected_term, prompt

    for user_prompt, invalid_draft in (
        ("What does quorblax mean?", "Quorblax isn't a real word, Oliver. It's nonsense."),
        ("Define gremlify.", "Gremlify is not an actual term."),
        ("What does oobleflarp mean?", "There is no such word."),
        ("Is photomimesis a word?", "It's gibberish."),
        ("What does flinderage mean?", "Flinderage doesn't exist."),
    ):
        assert contains_unjustified_lexical_denial(user_prompt, invalid_draft)
        fixed, changed = repair_unjustified_lexical_denial(user_prompt, invalid_draft)
        assert changed and "not familiar" in fixed.lower(), (user_prompt, fixed)
        assert not contains_unjustified_lexical_denial(user_prompt, fixed), fixed
        assert "isn't a real word" not in fixed.lower(), fixed

    for prompt, permissible_draft in (
        ("What does quorblax mean?", "I don't recognise it as a standard term."),
        ("Define cryptography.", "Cryptography is the study of secure communication."),
        ("What does flinderage mean?", "I'm unsure; it might be a coined word."),
        ("What is a lexicon?", "It's not a real word in that fictional book."),
    ):
        fixed, changed = repair_unjustified_lexical_denial(prompt, permissible_draft)
        assert not changed and fixed == permissible_draft, prompt

    assert extract_lexical_query_term("What does a Python list comprehension do?") is None
    assert extract_lexical_query_term("What's the weather today?") is None

    # B. Questions about concealed/unreported user-specific state cannot be
    # answered or verified via PUBLIC web research, even when "today" appears.
    private_requests = (
        "I have a coin in my closed fist. Which side is facing up?",
        "What colour shirt am I wearing right now?",
        "What color shoes am I wearing?",
        "What did I eat for breakfast today?",
        "What did I have for lunch yesterday?",
        "What am I thinking of right now?",
        "What's in my pocket?",
    )
    expected_kinds = {
        private_requests[0]: "concealed_object",
        private_requests[1]: "current_appearance",
        private_requests[2]: "current_appearance",
        private_requests[3]: "undisclosed_meal",
        private_requests[4]: "undisclosed_meal",
        private_requests[5]: "private_thought",
        private_requests[6]: "concealed_object",
    }
    for user_input in private_requests:
        assert classify_private_user_question(user_input) == expected_kinds[user_input]
        assert is_inaccessible_private_state_question(user_input), user_input
        assert classify_factual_authority(user_input) == "private_state_uncertain", user_input
        assert not factual_question_requires_live_data(user_input), user_input
        turn = _turn(user_input)
        assert turn.intent == "factual_question", (user_input, turn.intent)
        route = route_epistemic_authority(turn)
        assert route.authority == "live_conversation", (user_input, route)
        assert route.mode == "private_state_uncertain", (user_input, route)
        assert route.private_data_required and not route.live_data_required
        assert not route.verification_required and not route.allow_model_memory
        decision = MaironCore().prepare_turn(user_input)
        assert decision.epistemic_route.mode == "private_state_uncertain", user_input
        assert decision.answer_contract.epistemic_mode == "private_state_uncertain"
        assert decision.direct_response, user_input
        assert "don't know" in decision.direct_response.lower(), user_input
        if expected_kinds[user_input] == "undisclosed_meal":
            assert "wear" not in decision.direct_response.lower(), user_input
            assert "ate" in decision.direct_response.lower(), user_input
        if expected_kinds[user_input] == "current_appearance":
            assert "wear" in decision.direct_response.lower(), user_input

    # C. Guard against swallowing REAL public queries or private tool flows.
    assert classify_private_user_question("What's the weather in Sydney today?") is None
    for public_request in (
        "What's the weather in Sydney today?",
        "Who is the prime minister of Australia right now?",
        "What colour shirts are fashionable this year?",
        "What time does the museum close today?",
        "Where did Einstein live in 1905?",
    ):
        assert not is_inaccessible_private_state_question(public_request), public_request
        assert classify_factual_authority(public_request) == "public_source_verified", public_request
        assert route_epistemic_authority(_turn(public_request)).authority == "public_web", public_request

    assert route_epistemic_authority(
        _turn("What did I just tell you about my breakfast?")
    ).mode == "conversation_recall"
    assert route_epistemic_authority(
        _turn("Put a dentist appointment on my calendar for Friday from 3pm to 4pm.")
    ).authority == "calendar"
    assert classify_factual_authority("What's the default port for HTTPS?") == "stable_model_knowledge"

    # D. The local intent router may have newer user-grounded follow-up logic.
    # Private-state questions must bypass that helper, but ordinary questions
    # must still be eligible for it. Patching the helper keeps this test
    # independent of any particular heuristic in followup_task.py.
    grounded = [{"text": "I'm configuring my router.", "intent": "share_context"}]
    with (
        patch("core.intent_router.bounded_recent_user_turns", return_value=grounded),
        patch("core.intent_router.classify_user_grounded_followup", return_value=grounded) as followup,
    ):
        private_turn = classify_turn("What colour shirt am I wearing right now?")
        assert private_turn.intent == "factual_question"
        assert private_turn.factuality == "requires_epistemic_routing"
        followup.assert_not_called()

        normal_turn = classify_turn("How do I configure that?")
        assert normal_turn.intent == "factual_question"
        assert normal_turn.factuality == "user_premise_continuation"
        assert normal_turn.entities.get("_user_grounded_followup") == "true"
        followup.assert_called_once()

    print("PASS: Phase 11.6.3 calibration + router + orchestrator compatibility")


if __name__ == "__main__":
    run()
