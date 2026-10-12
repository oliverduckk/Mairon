"""Real provider retries/ingress preserve USER opinion ownership offline."""
from contextlib import redirect_stdout
import ast
import io
import re
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.answer_contract import build_answer_contract
from core.answer_contract_runtime import AnswerContractRuntime
from core.epistemic_router import route_epistemic_authority
from core.intent_router import classify_turn
from core.stance_ownership import (
    build_stance_ownership_frame, find_stance_ownership_violations,
    is_user_stance_acknowledgement, render_stance_ownership_instruction,
)
from test_core_phase11_6_6_trust_integration import run, ScriptedClient, valid_core
from test_core_phase11_6_6c_social_empty_integration import entry, EmptyClient
import personality.opinion_ledger as ledger


USER = "For this discussion, remember that I reckon amber is harder to shape than basalt."
BAD = "Noted. I reckon amber is harder to shape than basalt."
GOOD = "Noted — you reckon amber is harder to shape than basalt."
SUBJECT = ledger.classify_opinion_subject("Lumen clears Vale.")


def contract(intent="share_opinion", **changes):
    return AnswerContractRuntime(**({"intent": intent, "authority": "conversation",
        "epistemic_mode": "subjective", "allow_new_factual_claims": False} | changes))


def overrides(*, prior=None, recorded=None, extra=None):
    value = {
        "is_user_stance_acknowledgement": is_user_stance_acknowledgement,
        "build_stance_ownership_frame": build_stance_ownership_frame,
        "render_stance_ownership_instruction": render_stance_ownership_instruction,
        "find_stance_ownership_violations": find_stance_ownership_violations,
        "classify_opinion_subject": lambda **kwargs: SUBJECT,
        "get_or_recover_opinion_entry": lambda **kwargs: prior,
        "record_opinion_if_needed": lambda **kwargs: (recorded.append(kwargs) if recorded is not None else None),
    }
    if extra:
        value.update(extra)
    return value


def generation_calls(client):
    return sum(not any("INTERNAL" in message["content"] for message in call["messages"])
               for call in client.calls)


def provider_text_helper(name):
    path = ROOT / "src/ai/ollama_provider.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(item for item in tree.body if isinstance(item, ast.FunctionDef)
                    and item.name == name)
    namespace = {"re": re, "get_message_role": lambda message: message["role"],
                 "get_message_content": lambda message: message["content"]}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[function.name]


class StanceOwnershipProductionTests(unittest.TestCase):
    def assert_published(self, result, expected, *rejected):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": expected})
        self.assertEqual(result[2:], (None, None))
        for bad in rejected:
            self.assertNotIn(bad, [item["content"] for item in result[1]])

    def test_global_positive_cannot_publish_first_person_user_stance_mirror(self):
        client = ScriptedClient([BAD, GOOD], core=[valid_core(), valid_core()])
        self.assert_published(run(client, USER, contract(), overrides=overrides()), GOOD, BAD)
        self.assertEqual(generation_calls(client), 2)

    def test_ownership_is_checked_again_for_each_retry(self):
        second = "My take is amber is harder to shape than basalt."
        client = ScriptedClient([BAD, second, GOOD], core=[valid_core()] * 3)
        self.assert_published(run(client, USER, contract(), overrides=overrides()), GOOD, BAD, second)
        self.assertEqual(generation_calls(client), 3)

    def test_exhaustion_uses_bounded_acknowledgement_not_an_opinion_template(self):
        recorded = []
        client = ScriptedClient([BAD] * 3, core=[valid_core()] * 3)
        result = run(client, USER, contract(), overrides=overrides(recorded=recorded))
        self.assert_published(result, "Got it.", BAD)
        self.assertEqual(generation_calls(client), 3)
        self.assertEqual(recorded, [])

    def test_attributed_valid_acknowledgement_publishes_unchanged(self):
        client = ScriptedClient([GOOD], core=[valid_core()])
        self.assert_published(run(client, USER, contract(), overrides=overrides()), GOOD)
        self.assertEqual(generation_calls(client), 1)

    def test_acknowledgement_never_records_a_new_assistant_side(self):
        recorded = []
        client = ScriptedClient([GOOD], core=[valid_core()])
        run(client, USER, contract(), overrides=overrides(recorded=recorded))
        self.assertEqual(recorded, [])

    def test_existing_accepted_assistant_stance_remains_separately_publishable(self):
        prior = {"stance_text": "I think amber is harder to shape than basalt.", "position": "left"}
        own = "You reckon amber is harder to shape than basalt. I think amber is harder to shape than basalt."
        recorded = []
        client = ScriptedClient([own], core=[valid_core()])
        self.assert_published(run(client, USER, contract(), overrides=overrides(prior=prior, recorded=recorded)), own)
        self.assertEqual(recorded, [])
        self.assertEqual(prior["stance_text"], "I think amber is harder to shape than basalt.")

    def test_assistant_dialogue_alone_cannot_authorize_ownership(self):
        history = [{"role": "assistant", "content": "I think amber is harder to shape than basalt."}]
        client = ScriptedClient([BAD, GOOD], core=[valid_core()] * 2)
        self.assert_published(run(client, USER, contract(), history, overrides()), GOOD, BAD)

    def test_user_correction_changes_user_stance_without_mutating_assistant_stance(self):
        current = "Correction: remember that I now prefer basalt over amber."
        bad = "I prefer basalt over amber now."
        good = "Noted — you now prefer basalt over amber."
        prior = {"stance_text": "I prefer amber over basalt.", "position": "left"}
        history = [{"role": "user", "content": "Remember that I prefer amber over basalt."}]
        recorded = []
        client = ScriptedClient([bad, good], core=[valid_core()] * 2)
        self.assert_published(run(client, current, contract(), history, overrides(prior=prior, recorded=recorded)), good, bad)
        self.assertEqual(recorded, [])
        self.assertEqual(prior["stance_text"], "I prefer amber over basalt.")

    def test_typed_stance_correction_keeps_latest_user_owner_without_repeated_directive(self):
        current = "Actually, I now prefer basalt over amber."
        bad, good = "I now prefer basalt over amber.", "You now prefer basalt over amber."
        record = []
        client = ScriptedClient([bad, good], core=[valid_core()] * 2)
        corrected = contract("self_correction", authority="user_turn_and_live_conversation", epistemic_mode="self_correction")
        self.assert_published(run(client, current, corrected, overrides=overrides(recorded=record)), good, bad)
        self.assertEqual(record, [])

    def test_latest_user_stance_recall_stays_user_attributed(self):
        history = [{"role": "user", "content": "Remember that I prefer amber over basalt."},
                   {"role": "assistant", "content": "Noted."},
                   {"role": "user", "content": "Correction: I now prefer basalt over amber."},
                   {"role": "assistant", "content": "I prefer amber over basalt."}]
        answer = "You told me that you now prefer basalt over amber."
        current = contract("conversation_recall", authority="live_conversation", epistemic_mode="conversation_recall")
        client = ScriptedClient([answer], core=[valid_core()])
        self.assert_published(run(client, "What preference did I tell you?", current, history, overrides(extra={
            "classify_opinion_subject": ledger.classify_opinion_subject,
            "build_live_conversation_recall_context": provider_text_helper("build_live_conversation_recall_context"),
            "repair_live_recall_tail": provider_text_helper("repair_live_recall_tail"),
        })), answer)

    def test_ordinary_opinion_request_keeps_existing_generation_and_recording(self):
        recorded = []
        text = "I prefer Vale over Lumen."
        client = ScriptedClient([text], core=[valid_core()])
        self.assert_published(run(client, "Lumen clears Vale.", contract(), overrides=overrides(recorded=recorded)), text)
        self.assertEqual(len(recorded), 1)

    def test_acknowledgement_does_not_invoke_pairwise_background_offer(self):
        def forbidden(**kwargs):
            raise AssertionError("Acknowledgement must not ask for pairwise research")
        client = ScriptedClient([GOOD], core=[valid_core()])
        self.assert_published(run(client, USER, contract(), overrides=overrides(extra={
            "build_pairwise_background_research_opportunity": forbidden})), GOOD)

    def test_acknowledgement_mode_does_not_prompt_for_assistant_opinion(self):
        client = ScriptedClient([GOOD], core=[valid_core()])
        run(client, USER, contract(), overrides=overrides())
        generation = "\n".join(item["content"] for item in client.calls[0]["messages"])
        self.assertIn("CORE STANCE OWNERSHIP", generation)
        self.assertNotIn("OPINION-LANE RESPONSE MODE", generation)
        self.assertNotIn("CORE PAIRWISE COMPARISON", generation)

    def test_real_ingress_contract_dispatches_tool_free_even_if_surface_heuristic_declines(self):
        turn = classify_turn(USER)
        real_contract = build_answer_contract(turn, route_epistemic_authority(turn))
        client = ScriptedClient([BAD, GOOD], core=[valid_core()] * 2)
        seen = []
        def direct(**kwargs):
            seen.append(kwargs["core_answer_contract"])
            return run(kwargs["client"], kwargs["user_input"], kwargs["core_answer_contract"],
                       kwargs["conversation"], overrides())
        result, _ = entry(USER, client, real_contract, force_tool_loop=True, overrides={
            "is_user_stance_acknowledgement": is_user_stance_acknowledgement,
            "handle_direct_conversation": direct,
        })
        self.assert_published(result, GOOD, BAD)
        self.assertEqual(len(seen), 1)
        self.assertEqual(generation_calls(client), 2)
        self.assertTrue(all(not call.get("tools") for call in client.calls))

    def test_empty_acknowledgement_exhaustion_keeps_no_action_and_no_memory_claim(self):
        client = EmptyClient()
        def direct(**kwargs):
            return run(kwargs["client"], kwargs["user_input"], kwargs["core_answer_contract"],
                       kwargs["conversation"], overrides())
        result, _ = entry(USER, client, contract(), force_tool_loop=True, overrides={
            "is_user_stance_acknowledgement": is_user_stance_acknowledgement,
            "handle_direct_conversation": direct,
        })
        self.assert_published(result, "Got it.")
        self.assertEqual(len(client.calls), 3)
        self.assertNotRegex(result[0].lower(), r"stored|saved|memory|remind|approval")

    def test_quoted_user_opinion_can_be_acknowledged_without_adopting_it(self):
        text = 'You said "I reckon amber is harder to shape than basalt." Noted.'
        client = ScriptedClient([text], core=[valid_core()])
        self.assert_published(run(client, USER, contract(), overrides=overrides()), text)


if __name__ == "__main__":
    unittest.main()
