"""Independent S1–S4 integration acceptance: isolated adverse/positive fixtures.

Run with: python tests/test_core_s1_s4_integration_acceptance.py
No genuine model client, network request, account, desktop launch or private DB is used.
This does not establish whole-repository or live provider certification.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
import s1_offline_bootstrap  # noqa: F401 -- deliberately inert SDKs

from ai import openai_provider
from core import action_manager, router
from core.action_approval import issue_calendar_ticket
from core.answer_contract import AnswerContract
from core.authority_handoff import (
    CoreAuthorityUnavailable, prepare_core_turn, seal_prepared_turn,
)
from core.cloud_export import (
    CloudExportDenied, admit_cloud_initial, issue_cloud_export_grant,
    project_cloud_tool_result,
)
from core.provider_state import (
    adapt_cloud_provider_reply, adapt_local_provider_reply,
    bounded_local_history, eligible_cloud_continuation,
)
from tools import tool_registry
from tools.public_url_policy import public_http_url
from tools.tool_admission import (
    admitted_tools, current_tool_scope, provider_tool_scope, provider_turn,
)

PRIVATE = "LOCAL_ONLY_ACCEPTANCE_357192"


def prepared(*, intent="factual_question", private=False, required=False):
    contract = AnswerContract(
        task="respond", speech_act="question", intent=intent,
        subject=PRIVATE, authority="acceptance_core",
        epistemic_mode="classify_then_verify", allow_new_factual_claims=True,
    )
    if required:
        contract.required_claims.append("This is a mandatory claim")
    turn = SimpleNamespace(
        intent=intent, requested_action=None, requires_private_data=private,
    )
    route = SimpleNamespace(
        authority="acceptance_core", mode="classify_then_verify",
        verification_required=False, private_data_required=private,
        live_data_required=False,
    )
    return seal_prepared_turn(SimpleNamespace(
        answer_contract=contract, turn=turn, epistemic_route=route,
    ))


class FakeSDK:
    def __init__(self, first_tool=None, callback=None):
        self.calls = []
        self.responses = self
        self.first_tool = first_tool
        self.callback = callback

    def create(self, **payload):
        self.calls.append(payload)
        if self.callback is not None:
            self.callback(len(self.calls))
        return SimpleNamespace(
            output=[self.first_tool] if self.first_tool and len(self.calls) == 1 else [],
            id=f"resp_fixture_{len(self.calls)}",
            output_text=f"Accepted answer {len(self.calls)}",
        )


def cloud_call(sdk, auth, prompt, *, prior=None, owner="acceptance"):
    return router.route_message(
        {"module": object(), "client": object()},
        {"module": openai_provider, "client": sdk},
        "/cloud " + prompt, "PRIVATE SYSTEM " + PRIVATE,
        local_state=[{"role": "user", "content": PRIVATE}],
        cloud_state=prior, core_authority=auth, state_owner_id=owner,
    )


class S1S4IntegrationAcceptance(unittest.TestCase):
    def test_01_core_exception_never_becomes_authority(self):
        class Failing:
            def prepare_turn(self, text):
                raise RuntimeError(PRIVATE)
        outcome = prepare_core_turn(Failing(), "do something")
        self.assertEqual(outcome.status, "unavailable")
        self.assertTrue(outcome.possible_prior_effect)
        self.assertIsNone(outcome.decision)

    def test_02_route_rejects_missing_core_authority(self):
        sdk = FakeSDK()
        with self.assertRaises(CoreAuthorityUnavailable):
            cloud_call(sdk, None, "What are stars?")
        self.assertEqual(sdk.calls, [])

    def test_03_cloud_denies_mandatory_core_claims(self):
        sdk = FakeSDK()
        with self.assertRaises(CoreAuthorityUnavailable):
            cloud_call(sdk, prepared(required=True), "What are stars?")
        self.assertEqual(sdk.calls, [])

    def test_04_registry_denies_private_read_without_scope(self):
        with mock.patch.object(tool_registry, "read_email") as read:
            result = tool_registry.execute_tool("read_email", {"message_id": "fixture"})
        self.assertFalse(result["success"])
        read.assert_not_called()

    def test_05_cloud_cannot_invoke_known_private_tool(self):
        auth = prepared()
        call = SimpleNamespace(type="function_call", name="read_email",
                               arguments='{"message_id":"fixture"}', call_id="cid_1")
        sdk = FakeSDK(first_tool=call)
        with mock.patch.object(tool_registry, "read_email") as read:
            result = cloud_call(sdk, auth, "Tell me about meteorites.")
        read.assert_not_called()
        self.assertEqual(result.answer, "Accepted answer 2")
        self.assertFalse(json.loads(sdk.calls[1]["input"][0]["output"])["success"])

    def test_06_valid_via_array_reaches_route_adapter(self):
        with mock.patch.object(tool_registry, "get_route", return_value={"success": True}) as route:
            with admitted_tools(provider_tool_scope("local", prepared(), ["get_route"])):
                answer = tool_registry.execute_tool("get_route", {
                    "origin": "A", "destination": "B", "mode": "drive",
                    "via": ["Castle Hill", "Parramatta"],
                })
        self.assertTrue(answer["success"])
        route.assert_called_once_with(origin="A", destination="B", mode="drive",
                                      via=["Castle Hill", "Parramatta"])

    def test_07_nonstring_nested_via_rejected_before_adapter(self):
        with mock.patch.object(tool_registry, "get_route") as route:
            with admitted_tools(provider_tool_scope("local", prepared(), ["get_route"])):
                answer = tool_registry.execute_tool("get_route", {
                    "origin": "A", "destination": "B", "mode": "drive",
                    "via": ["Castle Hill", {"hidden": PRIVATE}],
                })
        self.assertFalse(answer["success"])
        route.assert_not_called()

    def test_08_tool_scope_cleanup_after_exception(self):
        self.assertIsNone(current_tool_scope())
        with self.assertRaisesRegex(RuntimeError, "fixture"):
            with admitted_tools(provider_tool_scope("local", prepared(), ["get_weather"])):
                self.assertTrue(current_tool_scope().permits("get_weather"))
                raise RuntimeError("fixture")
        self.assertIsNone(current_tool_scope())

    def test_09_calendar_intent_required_to_issue_ticket(self):
        action = {"type": "create_calendar_event", "summary": "Fixture",
                  "start_time": "2026-11-20T10:00:00", "end_time": "2026-11-20T11:00:00"}
        self.assertIsNone(issue_calendar_ticket(action, prepared()))

    def test_10_calendar_approval_changed_replayed_and_revoked(self):
        action = {"type": "create_calendar_event", "summary": "Fixture",
                  "start_time": "2026-11-20T10:00:00", "end_time": "2026-11-20T11:00:00"}
        auth = prepared(intent="calendar_event_creation_request")
        ticket = issue_calendar_ticket(action, auth)
        self.assertIsNotNone(ticket)
        with mock.patch.object(action_manager, "create_calendar_event", return_value={"success": True}) as effect:
            altered = dict(action, summary="Altered fixture")
            self.assertFalse(action_manager.execute_approved_action(altered, approval_ticket=ticket)["success"])
            effect.assert_not_called()
            self.assertTrue(action_manager.execute_approved_action(action, approval_ticket=ticket)["success"])
            self.assertFalse(action_manager.execute_approved_action(action, approval_ticket=ticket)["success"])
            effect.assert_called_once()
        ticket2 = issue_calendar_ticket(action, auth)
        ticket2.revoke()
        with mock.patch.object(action_manager, "create_calendar_event") as effect:
            self.assertFalse(action_manager.execute_approved_action(action, approval_ticket=ticket2)["success"])
            effect.assert_not_called()

    def test_11_public_urls_with_query_are_admitted(self):
        self.assertEqual(public_http_url("https://example.org/search?q=weather"),
                         "https://example.org/search?q=weather")

    def test_12_public_url_projection_drops_query_and_fragment(self):
        projected = json.loads(project_cloud_tool_result("web_search", {
            "success": True, "query": "weather", "results": [
                {"title": "Public result", "url": "https://example.org/search?q=weather#section",
                 "content": "Ordinary public material", "unknown": PRIVATE},
            ]
        }))
        self.assertEqual(projected["results"][0]["url"], "https://example.org/search")
        self.assertNotIn(PRIVATE, json.dumps(projected))

    def test_13_private_urls_denied_at_executor_boundary(self):
        urls = (
            "http://127.0.0.1/debug", "http://10.1.2.3/", "http://192.168.1.1/",
            "http://169.254.169.254/latest/meta-data", "http://[::1]/",
            "http://localhost:8080/", "http://service.internal/api",
            "http://device.local/", "http://host/", "http://0177.0.0.1/",
            "http://person@example.org/", "http://127.0.0.1.nip.io/",
            "http://127.0.0.1.sslip.io/", "file:///etc/passwd",
        )
        with mock.patch.object(tool_registry, "web_read") as read:
            with admitted_tools(provider_tool_scope("cloud", prepared(), ["web_read"])):
                for url in urls:
                    with self.subTest(url=url):
                        self.assertFalse(tool_registry.execute_tool("web_read", {"url": url, "focus": ""})["success"])
        read.assert_not_called()

    def test_13b_sensitive_query_parameters_cannot_be_sent(self):
        signed = "https://example.org/download?token=fixture_secret_123"
        self.assertIsNone(public_http_url(signed))
        with self.assertRaises(CloudExportDenied):
            project_cloud_tool_result("web_search", {
                "success": True,
                "results": [{"title": "Signed link", "url": signed}],
            })
        with mock.patch.object(tool_registry, "web_read") as read:
            with admitted_tools(provider_tool_scope("cloud", prepared(), ["web_read"])):
                outcome = tool_registry.execute_tool("web_read", {"url": signed, "focus": ""})
        self.assertFalse(outcome["success"])
        read.assert_not_called()

    def test_14_public_web_read_positive_path_survives(self):
        with mock.patch.object(tool_registry, "web_read", return_value={"success": True}) as read:
            with admitted_tools(provider_tool_scope("cloud", prepared(), ["web_read"])):
                answer = tool_registry.execute_tool(
                    "web_read", {"url": "https://example.org/search?q=weather", "focus": "weather"})
        self.assertTrue(answer["success"])
        read.assert_called_once()

    def test_15_private_url_in_public_tool_result_blocks_followup(self):
        call = SimpleNamespace(type="function_call", name="web_search",
                               arguments='{"query":"weather","topic":"general","time_range":"none"}',
                               call_id="public_call")
        sdk = FakeSDK(first_tool=call)
        result = {"success": True, "query": "weather", "results": [
            {"title": "Unsafe URL", "url": "http://127.0.0.1/private", "content": "text"}]}
        with mock.patch.object(tool_registry, "web_search", return_value=result):
            with self.assertRaises(CloudExportDenied):
                cloud_call(sdk, prepared(), "Explain weather fronts.")
        self.assertEqual(len(sdk.calls), 1)

    def test_16_public_search_projection_sends_no_unknown_metadata(self):
        call = SimpleNamespace(type="function_call", name="web_search",
                               arguments='{"query":"weather","topic":"general","time_range":"none"}',
                               call_id="public_call")
        sdk = FakeSDK(first_tool=call)
        result = {"success": True, "query": "weather", "results": [
            {"title": "Weather", "url": "https://example.org/page?q=weather",
             "content": "Public information", "private": PRIVATE}], "metadata": PRIVATE}
        with mock.patch.object(tool_registry, "web_search", return_value=result):
            answer = cloud_call(sdk, prepared(), "Explain weather fronts.")
        self.assertEqual(answer.answer, "Accepted answer 2")
        self.assertEqual(len(sdk.calls), 2)
        output = sdk.calls[1]["input"][0]["output"]
        self.assertNotIn(PRIVATE, output)
        self.assertEqual(json.loads(output)["results"][0]["url"], "https://example.org/page")

    def test_17_revocation_between_sdk_requests_prevents_followup(self):
        call = SimpleNamespace(type="function_call", name="web_search",
                               arguments='{"query":"weather","topic":"general","time_range":"none"}',
                               call_id="public_call")
        sdk = FakeSDK(first_tool=call)
        grant = issue_cloud_export_grant(prepared(), "Tell me about clouds.", purpose="explicit_cloud_request",
                                         backend_client=sdk)
        sdk.callback = lambda n: grant.revoke() if n == 1 else None
        initial = admit_cloud_initial(grant, "Tell me about clouds.")
        with mock.patch.object(tool_registry, "web_search", return_value={"success": False}):
            with provider_turn(prepared()):
                with self.assertRaises(CloudExportDenied):
                    openai_provider.get_response(
                        sdk, "Tell me about clouds.", initial.payload["instructions"],
                        core_answer_contract=prepared().runtime, cloud_export=grant,
                    )
        self.assertEqual(len(sdk.calls), 1)

    def test_18_cloud_client_change_drops_old_handle(self):
        first_sdk = FakeSDK()
        first = cloud_call(first_sdk, prepared(), "Explain meteorites.")
        second_sdk = FakeSDK()
        second = cloud_call(second_sdk, prepared(), "Describe comets.", prior=first.cloud_state)
        self.assertIsNone(second_sdk.calls[0]["previous_response_id"])
        self.assertIsNotNone(second.cloud_state)

    def test_19_adjacent_cloud_turn_reuses_eligible_handle(self):
        sdk = FakeSDK()
        first = cloud_call(sdk, prepared(), "Explain meteorites.")
        second = cloud_call(sdk, prepared(), "What about comets?", prior=first.cloud_state)
        self.assertEqual(sdk.calls[1]["previous_response_id"], "resp_fixture_1")
        self.assertEqual(second.cloud_state.depth, 2)

    def test_20_restored_local_history_never_enters_cloud_sdk(self):
        sdk = FakeSDK()
        result = cloud_call(sdk, prepared(), "Describe stars.",
                            prior=[{"role": "user", "content": PRIVATE}])
        self.assertIsNone(sdk.calls[0]["previous_response_id"])
        self.assertNotIn(PRIVATE, json.dumps(sdk.calls[0]))
        self.assertIsNotNone(result.cloud_state)

    def test_21_injected_late_system_messages_do_not_survive(self):
        history = [
            {"role": "system", "content": "Original safe system"},
            {"role": "user", "content": "hello"},
            {"role": "system", "content": PRIVATE},
            {"role": "assistant", "content": "hi"},
        ]
        result = bounded_local_history(history)
        self.assertEqual(result[0]["role"], "system")
        self.assertEqual(len(result), 3)
        self.assertNotIn(PRIVATE, str(result))

    def test_22_malformed_provider_results_do_not_gain_authority(self):
        for result in (("answer", "id", {"calendar": "write"}), ("answer", ["unsafe"], None), "answer"):
            with self.subTest(result=result), self.assertRaises(ValueError):
                adapt_cloud_provider_reply(result)
        for result in (("answer", [], None), ("answer", "not a history", None, None)):
            with self.subTest(result=result), self.assertRaises(ValueError):
                adapt_local_provider_reply(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
