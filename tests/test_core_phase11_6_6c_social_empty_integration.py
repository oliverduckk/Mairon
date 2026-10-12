"""Execute real provider functions offline; empty social replies stay non-action.

Core contract transport, action recognition, approval construction, generation
loops and publication branches are real. Unrelated services are inert and every
external execution interface raises, so these tests cannot contact accounts.
"""
from __future__ import annotations

import ast
import builtins
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime
import io
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import unittest
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.answer_contract import AnswerContract, build_answer_contract
from core.answer_contract_runtime import (
    CORE_ANSWER_CONTRACT_MARKER, coerce_answer_contract_runtime, contract_field_value,
    render_answer_contract, runtime_from_answer_contract,
)
from core.calendar_proposal_guard import CalendarProposalError, build_calendar_approval_from_user_request
from core.critical_response_safety import explicit_calendar_write_request, should_expose_model_cloud
from core.epistemic_router import EpistemicRoute
from core.social_acknowledgement import build_empty_social_acknowledgement
from core.turn_state import TurnState
from personality.personality_engine import should_use_direct_conversation
from test_core_phase11_6_6_trust_integration import run, social, valid_core, ScriptedClient


def social_contract():
    return runtime_from_answer_contract(build_answer_contract(
        TurnState(raw_text="A declarative share.", intent="share_context", speech_act="declarative_share"),
        EpistemicRoute(authority="user_turn", mode="user_provided", verification_required=False,
                       allow_model_memory=False, reason="USER-authored declarative share"),
    ))


def forbidden(*args, **kwargs):
    raise AssertionError("External action or account access is forbidden in this offline test")


class EmptyClient:
    def __init__(self, values=None):
        self.values = iter(values or ["", "", ""])
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(message=SimpleNamespace(
            role="assistant", content=next(self.values), tool_calls=[], thinking="private hidden thought"),
            done_reason="stop")


def tool_provider(*, force_tool_loop=False):
    """Compile the complete production ingress and its unchanged text helpers."""
    path = ROOT / "src/ai/ollama_provider.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {"_get_response_impl", "split_static_and_turn_instructions",
             "strip_ephemeral_core_contracts", "_strip_internal_reasoning_markup"}
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    calls = {node.func.id for function in functions for node in ast.walk(function)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    namespace = {}
    for name in calls:
        if hasattr(builtins, name) or name in names:
            continue
        if name.startswith(("should_", "is_", "looks_like_", "explicitly_requires_")):
            namespace[name] = lambda *args, **kwargs: False
        else:
            namespace[name] = lambda *args, **kwargs: None
    namespace.update({
        "json": json, "os": os, "re": re,
        "CORE_ANSWER_CONTRACT_MARKER": CORE_ANSWER_CONTRACT_MARKER,
        "coerce_answer_contract_runtime": coerce_answer_contract_runtime,
        "_core_contract_value": contract_field_value,
        "render_answer_contract": render_answer_contract,
        "explicit_calendar_write_request": explicit_calendar_write_request,
        "should_expose_model_cloud": should_expose_model_cloud,
        "should_use_direct_conversation": ((lambda value: False) if force_tool_loop
                                           else should_use_direct_conversation),
        "get_runtime_context": lambda: "offline Core runtime",
        "get_local_model_name": lambda: "replaceable-model",
        "OLLAMA_ACTION_TOOLS": [], "CALENDAR_EVENT_REQUEST_TOOL": {},
        "CLOUD_ESCALATION_TOOL": {}, "MAX_TOOL_ROUNDS": 6,
        "build_empty_social_acknowledgement": build_empty_social_acknowledgement,
        "CalendarProposalError": CalendarProposalError,
        "build_calendar_approval_from_user_request": build_calendar_approval_from_user_request,
        "execute_tool": forbidden,
        "handle_direct_conversation": lambda **kwargs: run(
            kwargs["client"], kwargs["user_input"], kwargs["core_answer_contract"],
            kwargs["conversation"], {"build_empty_social_acknowledgement": build_empty_social_acknowledgement}),
    })
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), namespace)
    return namespace["_get_response_impl"], namespace


def entry(text, client=None, current=None, *, force_tool_loop=False, overrides=None):
    invoke, namespace = tool_provider(force_tool_loop=force_tool_loop)
    if overrides:
        namespace.update(overrides)
    client = client or EmptyClient()
    current = current or social_contract()
    # A fault-injection replace() must also update the rendered legacy ingress
    # transport. Runtime.model_instruction deliberately snapshots its old turn.
    instruction = AnswerContract(
        task=current.task, speech_act=current.speech_act, intent=current.intent,
        subject=current.subject, authority=current.authority,
        epistemic_mode=current.epistemic_mode,
        required_claims=list(current.required_claims),
        allow_recommendations=current.allow_recommendations,
        allow_new_factual_claims=current.allow_new_factual_claims,
        allow_follow_up_question=current.allow_follow_up_question,
    ).to_model_instruction()
    with redirect_stdout(io.StringIO()):
        returned = invoke(client, text, "offline identity\n" + instruction, conversation=[])
    return returned, client


class EmptySocialProductionTests(unittest.TestCase):
    def assert_nonaction(self, returned):
        self.assertTrue(returned[0].strip())
        self.assertEqual(returned[2:], (None, None))
        self.assertEqual(returned[1][-1], {"role": "assistant", "content": returned[0]})
        self.assertNotRegex(returned[0].casefold(), r"empty|retry|verifier|provider|model|usable answer")
        self.assertNotRegex(returned[0].casefold(), r"saved|stored|scheduled|created|remember|remind")

    def test_real_deferred_calendar_mention_survives_general_loop_empty_exhaustion(self):
        text = "I might add a study block to my calendar, not asking you to do it yet."
        self.assertFalse(should_use_direct_conversation(text))
        returned, client = entry(text)
        self.assert_nonaction(returned)
        self.assertEqual(returned[0], "Got it — no action for now.")
        self.assertEqual(len(client.calls), 3)

    def test_email_thought_does_not_trigger_action_or_approval(self):
        returned, client = entry("Perhaps later I will send an email.")
        self.assert_nonaction(returned)
        self.assertEqual(len(client.calls), 3)

    def test_file_thought_does_not_claim_a_change(self):
        returned, _ = entry("I might reorganise my files, not now.")
        self.assert_nonaction(returned)

    def test_device_control_thought_does_not_claim_control(self):
        returned, _ = entry("Maybe later I will dim the lights.")
        self.assert_nonaction(returned)

    def test_application_launch_thought_does_not_claim_launch(self):
        returned, _ = entry("I might launch the viewer, not yet.")
        self.assert_nonaction(returned)

    def test_action_mention_without_request_is_minimal(self):
        returned, _ = entry("I am thinking about an email draft.")
        self.assert_nonaction(returned)
        self.assertEqual(returned[0], "Got it.")

    def test_arbitrary_capability_remains_nonaction_without_domain_rules(self):
        returned, _ = entry("Maybe later I will activate a zorbulator.")
        self.assert_nonaction(returned)

    def test_direct_no_visible_exhaustion_uses_core_ack_without_verifier_loop(self):
        client = EmptyClient()
        returned = run(client, "I might try it another time.", social("share_context"), overrides={
            "build_empty_social_acknowledgement": build_empty_social_acknowledgement})
        self.assert_nonaction(returned)
        self.assertEqual(len(client.calls), 3)
        self.assertTrue(all("format" not in call for call in client.calls))

    def test_direct_thinking_only_content_is_not_visible_generation(self):
        invoke, namespace = tool_provider()
        strip = namespace["_strip_internal_reasoning_markup"]
        client = EmptyClient(["<think>private thought</think>"] * 3)
        returned = run(client, "Maybe later I will try it.", social("share_context"), overrides={
            "build_empty_social_acknowledgement": build_empty_social_acknowledgement,
            "_strip_internal_reasoning_markup": strip})
        self.assert_nonaction(returned)
        self.assertEqual(len(client.calls), 3)

    def test_general_thinking_only_content_does_not_leak_implementation(self):
        returned, client = entry("I might add a sketch session to my calendar, not now.",
                                 EmptyClient(["<think>private thought</think>"] * 3))
        self.assert_nonaction(returned)
        self.assertEqual(len(client.calls), 3)

    def test_valid_generated_social_personality_is_preserved_byte_for_byte(self):
        text = "That is an impressively dramatic parcel announcement."
        returned, client = entry("The parcel arrived!", ScriptedClient([text], core=[valid_core()]))
        self.assertEqual(returned[0], text)
        self.assertEqual(returned[1][-1]["content"], text)
        self.assertEqual(returned[2:], (None, None))

    def test_valid_general_loop_answer_is_preserved(self):
        text = "Fair enough — that can remain a thought for now."
        returned, client = entry("Maybe later I'll add something to my calendar.", EmptyClient([text]))
        self.assertEqual(returned[0], text)
        self.assertEqual(len(client.calls), 1)

    def test_explicit_action_retains_existing_deterministic_approval_path(self):
        text = "Add a design review to my calendar tomorrow from 2pm to 3pm."
        current = replace(social_contract(), task="calendar_event_creation_request",
                          speech_act="request_action", intent="calendar_event_creation_request",
                          authority="tool", epistemic_mode="tool_result")
        fixed = datetime(2026, 10, 12, 10, tzinfo=ZoneInfo("Australia/Sydney"))
        returned, client = entry(text, EmptyClient([]), current, overrides={
            "build_calendar_approval_from_user_request": lambda **kwargs:
                build_calendar_approval_from_user_request(**kwargs, now=fixed)})
        self.assertIsNone(returned[0])
        self.assertIsNone(returned[2])
        self.assertEqual(returned[3]["type"], "create_calendar_event")
        self.assertEqual(returned[3]["summary"], "design review")
        self.assertEqual(client.calls, [])

    def test_factual_empty_exhaustion_is_not_claimed_complete_as_social(self):
        current = replace(social_contract(), task="factual_question", speech_act="question",
                          intent="factual_question", authority="public_web",
                          epistemic_mode="public_source_verified")
        returned, _ = entry("What is the current release?", current=current, force_tool_loop=True)
        self.assertNotEqual(returned[0], "Got it.")
        self.assertNotEqual(returned[0], "Got it — no action for now.")

    def test_rejected_visible_candidate_does_not_use_empty_only_branch(self):
        client = ScriptedClient(["I can see you dancing beside the desk."] * 3,
                                core=[valid_core() | {"supported": False}] * 3)
        calls = []
        returned = run(client, "I am bored.", social(), overrides={
            "build_empty_social_acknowledgement": lambda **kwargs: calls.append(kwargs) or "WRONG EMPTY BRANCH"})
        self.assertEqual(calls, [])
        self.assertNotEqual(returned[0], "WRONG EMPTY BRANCH")

    def test_empty_social_fallback_adds_no_pending_background_marker(self):
        returned, _ = entry("Maybe later I will send an email.")
        self.assert_nonaction(returned)
        history = "\n".join(message["content"] for message in returned[1] if isinstance(message, dict))
        self.assertNotIn("PENDING_RESEARCH", history)
        self.assertNotIn("PENDING_ACTION", history)

    def test_prior_tool_only_attempt_cannot_masquerade_as_pure_empty_social(self):
        class ToolAttemptThenEmpty(EmptyClient):
            def chat(self, **kwargs):
                response = super().chat(**kwargs)
                if len(self.calls) == 1:
                    response.message.tool_calls = [SimpleNamespace(function=SimpleNamespace(
                        name="request_cloud_escalation", arguments={}))]
                return response

        called = []
        returned, client = entry(
            "Maybe later I will add a review to my calendar.",
            ToolAttemptThenEmpty(["", "", "", ""]), overrides={
                "build_empty_social_acknowledgement": lambda **kwargs: called.append(kwargs) or "WRONG EMPTY BRANCH"})
        self.assertEqual(called, [])
        self.assertNotEqual(returned[0], "WRONG EMPTY BRANCH")
        self.assertEqual(returned[2:], (None, None))
        self.assertEqual(len(client.calls), 4)


if __name__ == "__main__":
    unittest.main()
