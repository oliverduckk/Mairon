"""Neutral production-path regressions; no live model, accounts or web access."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_core_milestone3b3a_public_shadow_integration import provider
from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    build_core_grounding_fallback, find_acknowledgement_direction_violations,
    should_verify_acknowledgement_grounding, should_verify_core_grounding,
    should_verify_factual_focus_fidelity, verify_core_grounded_draft,
    verify_factual_focus_fidelity, find_explicit_user_constraint_violations,
)
from core.reasoning_trust import build_reasoning_trust_frame, render_reasoning_trust_instruction
from core.debate_state import (
    build_pairwise_semantic_instruction, find_pairwise_opinion_integrity_violations,
    build_pairwise_opinion_fallback, looks_like_debate_continuation,
)


class ScriptedClient:
    def __init__(self, drafts, core=None, fidelity=None):
        self.drafts = iter(drafts)
        self.core = iter(core or [])
        self.fidelity = iter(fidelity or [])
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        system = "\n".join(m["content"] for m in kwargs["messages"] if m["role"] == "system")
        if "INTERNAL claim-grounding verifier" in system:
            value = json.dumps(next(self.core))
        elif "INTERNAL factual-answer source-fidelity verifier" in system:
            value = json.dumps(next(self.fidelity))
        else:
            value = next(self.drafts)
        return SimpleNamespace(message=SimpleNamespace(content=value, tool_calls=[]), done_reason="stop")


def valid_core():
    return {"supported": True, "relevant": True, "source_faithful": True, "unsupported_claims": []}


def run(client, current, contract, conversation=(), overrides=None):
    fn, ns = provider()
    ns.update({
        "build_reasoning_trust_frame": build_reasoning_trust_frame,
        "render_reasoning_trust_instruction": render_reasoning_trust_instruction,
        "find_acknowledgement_direction_violations": find_acknowledgement_direction_violations,
        "should_verify_acknowledgement_grounding": should_verify_acknowledgement_grounding,
        "should_verify_core_grounding": should_verify_core_grounding,
        "should_verify_factual_focus_fidelity": should_verify_factual_focus_fidelity,
        "verify_core_grounded_draft": verify_core_grounded_draft,
        "verify_factual_focus_fidelity": verify_factual_focus_fidelity,
        "find_explicit_user_constraint_violations": find_explicit_user_constraint_violations,
        "repair_factual_personal_history_tail": lambda **kwargs: (kwargs["draft"], None),
        "build_core_grounding_fallback": build_core_grounding_fallback,
        "looks_like_debate_continuation": looks_like_debate_continuation,
        "build_pairwise_semantic_instruction": build_pairwise_semantic_instruction,
        "find_pairwise_opinion_integrity_violations": find_pairwise_opinion_integrity_violations,
        "build_pairwise_opinion_fallback": build_pairwise_opinion_fallback,
    })
    if overrides:
        ns.update(overrides)
    with redirect_stdout(io.StringIO()):
        result = fn(client, current, list(conversation), core_answer_contract=contract)
    return result


def social(intent="casual_conversation"):
    return AnswerContractRuntime(intent=intent, authority="live_conversation", epistemic_mode="conversation",
                                 allow_new_factual_claims=False)


class TrustProductionTests(unittest.TestCase):
    def test_positive_global_cannot_publish_negative_concrete_social_premise(self):
        bad = "The guild leader sabotaged the ballot and will escape punishment again."
        good = "That decision clearly annoyed you. I'm not going to invent what happened."
        contradiction = valid_core() | {"unsupported_claims": ["unseen event and recurring consequence"]}
        c = ScriptedClient([bad, good], core=[contradiction, valid_core()])
        result = run(c, "The guild leader's handling of the ballot annoyed me.", social())
        self.assertEqual(result[0], good)
        self.assertEqual(result[1][-1]["content"], good)
        self.assertNotIn(bad, [m["content"] for m in result[1]])

    def test_truthful_emotional_acknowledgement_keeps_natural_rendering(self):
        text = "Yeah, you're clearly fed up with that decision."
        result = run(ScriptedClient([text], core=[valid_core()]),
                     "The guild leader's decision is irritating me.", social())
        self.assertEqual(result[0], text)

    def test_plain_thanks_preserves_direction_without_an_extra_model_call(self):
        c = ScriptedClient(["You're welcome."])
        result = run(c, "thanks", social("acknowledge"))
        self.assertEqual(result[0], "You're welcome.")
        self.assertEqual(len(c.calls), 1)

    def test_reversed_thanks_is_withheld(self):
        c = ScriptedClient(["Thanks for that.", "You're welcome."])
        result = run(c, "thanks", social("acknowledge"))
        self.assertEqual(result[0], "You're welcome.")

    def test_thanks_with_fabricated_history_does_not_skip_grounding(self):
        bad = "You're welcome. Nobody else ever listens to you."
        c = ScriptedClient([bad, "You're welcome."], core=[
            valid_core() | {"supported": False, "unsupported_claims": ["invented human relationship history"]}])
        result = run(c, "thanks", social("acknowledge"))
        self.assertEqual(result[0], "You're welcome.")
        self.assertTrue(any("INTERNAL claim-grounding verifier" in m["content"]
                            for call in c.calls for m in call["messages"]))

    def test_complaint_does_not_create_a_recurring_relationship_premise(self):
        c = ScriptedClient(["You're teaching me again.", "Fair criticism. I should check instead of bluffing."],
                           core=[valid_core() | {"source_faithful": False}, valid_core()])
        result = run(c, "You should verify it yourself instead of asking me to explain it.", social())
        self.assertEqual(result[0], "Fair criticism. I should check instead of bluffing.")

    def test_physical_observation_cannot_hide_inside_a_joke(self):
        bad = "I'm watching you pace like a wind-up toy."
        good = "Your boredom has impressive stamina."
        # Core rejects the first draft before any semantic-verifier call.
        c = ScriptedClient([bad, good], core=[valid_core()])
        result = run(c, "I'm bored.", social())
        self.assertEqual(result[0], good)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": good})
        self.assertNotIn(bad, [message["content"] for message in result[1]])

        call_kinds = [
            "semantic" if any(
                message["role"] == "system"
                and "INTERNAL claim-grounding verifier" in message["content"]
                for message in call["messages"]
            ) else "generation"
            for call in c.calls
        ]
        self.assertEqual(call_kinds.count("generation"), 2)
        self.assertEqual(call_kinds.count("semantic"), 1)
        self.assertEqual(call_kinds, ["generation", "generation", "semantic"])
        self.assertEqual(c.calls[-1]["messages"][-1], {
            "role": "user", "content": "PROPOSED MAIRON DRAFT:\n" + good,
        })

    def test_diagnostic_negative_inference_overrides_positive_fidelity(self):
        c = ScriptedClient(["The vibration proves a damaged shaft.",
                            "That reading narrows the search; alignment and mounting remain possibilities."],
                           fidelity=[{"faithful": True, "inference_faithful": False, "violations": []},
                                     {"faithful": True, "inference_faithful": True, "violations": []}])
        ct = AnswerContractRuntime(intent="factual_question", authority="stable_model_knowledge",
                                   epistemic_mode="stable_model_knowledge", allow_new_factual_claims=True)
        result = run(c, "The motor vibrates under load but not while idle. What does that establish?", ct)
        self.assertEqual(result[0], "That reading narrows the search; alignment and mounting remain possibilities.")

    def test_prior_user_constraint_reaches_followup_generation_and_verification(self):
        ct = AnswerContractRuntime(intent="factual_question", authority="stable_model_knowledge",
                                   epistemic_mode="user_context_reasoning", allow_new_factual_claims=True)
        history = [{"role": "user", "content": "Compare two setups without assuming my budget."},
                   {"role": "assistant", "content": "Your budget is tiny."}]
        good = "I'll compare the technical trade-offs without assigning you a budget."
        c = ScriptedClient([good], fidelity=[{"faithful": True, "violations": []}])
        self.assertEqual(run(c, "And what would that change?", ct, history)[0], good)
        packets = "\n".join(m["content"] for call in c.calls for m in call["messages"] if m["role"] == "system")
        self.assertIn("without assuming my budget", packets)
        self.assertNotIn("Your budget is tiny.", packets)

    def test_unestablished_take_cannot_be_manufactured_on_defense(self):
        subject = {"kind": "pairwise_comparison", "left": "Lumen", "right": "Vale", "key": "lumen_vs_vale"}
        history = [{"role": "user", "content": "Lumen clears Vale."},
                   {"role": "assistant", "content": "I don't know enough about either to choose a side."}]
        ct = AnswerContractRuntime(intent="share_opinion", authority="conversation", epistemic_mode="conversation",
                                   subject="Lumen vs Vale", metadata={"debate_continuation": "true"})
        c = ScriptedClient(["Lumen over Vale for me."] * 3, core=[valid_core()] * 3)
        result = run(c, "Defend your take.", ct, history,
                     {"classify_opinion_subject": lambda **kwargs: subject})
        self.assertNotEqual(result[0], "Lumen over Vale for me.")
        self.assertIn("didn't", result[0])
        generation = c.calls[0]["messages"]
        mode = next(m["content"] for m in generation if m["content"].startswith("OPINION-LANE RESPONSE MODE:"))
        self.assertIn("no informed side was established", mode)
        self.assertNotIn("defend/explain its own active take", mode)

    def test_permission_offer_remains_a_separate_early_return(self):
        ct = social("share_opinion")
        c = ScriptedClient([])
        offer = "I need a better basis. Would you like me to research it properly?"
        result = run(c, "Compare Lumen and Vale.", ct, overrides={
            "build_pairwise_background_research_opportunity": lambda **kwargs: {"topic": "Lumen and Vale"},
            "build_background_research_offer_text": lambda _: offer,
            "_build_research_marker_result": lambda **kwargs: (kwargs["answer"], [], None, None),
            "uuid": SimpleNamespace(uuid4=lambda: "neutral-request"),
            "PENDING_RESEARCH_PROPOSAL_PREFIX": "pending",
        })
        self.assertEqual(result[0], offer)
        self.assertEqual(c.calls, [])


if __name__ == "__main__":
    unittest.main()
