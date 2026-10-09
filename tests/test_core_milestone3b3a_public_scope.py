"""Generated public observation cannot take over other publication lanes."""

from __future__ import annotations

import ast
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from test_core_milestone3b3a_public_shadow_integration import (
    Client, TEXT, contract, provider,
)
from core import acceptance_publication as publication
from core.acceptance_shadow import acceptance_shadow_events
from core.answer_candidate import AcceptanceStatus
from core.orchestrator import MaironCore
from core.workflows.arithmetic import calculate_arithmetic
from research.public_factual_grounding import build_failed_public_factual_fallback


class _RejectedClient(Client):
    def chat(self, **kwargs):
        if "format" not in kwargs:
            return super().chat(**kwargs)
        self.calls.append(kwargs)
        self.verifications += 1
        return SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "supported": False, "unsupported_claims": ["Unsupported assertion"],
            "sentence_assessments": [{"index": 1, "supported": False}],
        }), tool_calls=[]), done_reason="stop")


class _SalvageClient(Client):
    def chat(self, **kwargs):
        self.calls.append(kwargs)
        if "format" in kwargs:
            self.verifications += 1
            content = json.dumps({
                "supported": False, "unsupported_claims": ["Unsupported guarantee"],
                "sentence_assessments": [
                    {"index": 1, "supported": True}, {"index": 2, "supported": False},
                ],
            })
        else:
            content = TEXT + " The service guarantees instant delivery."
        return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=[]), done_reason="stop")


class PublicShadowScopeTests(unittest.TestCase):
    def run_public(self, *, retained=None, client=None, overrides=None):
        observed, publications, events = [], [], []

        def observer(**kwargs):
            observed.append(kwargs)
            raise AssertionError("An excluded publication lane reached public shadow")

        run, namespace = provider(retained=retained, observer=observer)

        def publish(**kwargs):
            result = publication.publish_limitation_response(**kwargs)
            publications.append(result)
            return result

        namespace.update({
            "publish_limitation_response": publish,
            "build_failed_public_factual_fallback": build_failed_public_factual_fallback,
        })
        if overrides:
            namespace.update(overrides)
        active_client = client or Client()
        with redirect_stdout(io.StringIO()), acceptance_shadow_events(events.append):
            result = run(active_client, "Which export capability does the service document?", [],
                         core_answer_contract=contract())
        return result, active_client, observed, publications, events

    def test_failed_public_retrieval_keeps_its_actual_enforced_publication(self):
        failed = {"success": False, "sources": [], "discovered_sources": [],
                  "failure_reason": "No admitted readable evidence"}
        result, client, observed, publications, events = self.run_public(retained=failed)
        self.assertEqual(result[0], build_failed_public_factual_fallback())
        self.assertEqual(result[1][-1], {"role": "assistant", "content": result[0]})
        self.assertEqual(client.calls, [])
        self.assertEqual(observed, [])
        self.assertEqual(len(publications), 1)
        record = publications[0].record
        self.assertEqual(record.path, "direct_public_evidence_unavailable")
        self.assertEqual(record.decision.status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(record.outcome, "accepted")
        self.assertFalse(record.replacement_used)
        self.assertTrue(any("Acceptance enforced:" in event for event in events))
        self.assertFalse(any("Acceptance shadow:" in event for event in events))

    def test_failed_public_retrieval_still_withholds_fabricated_legacy_fallback(self):
        failed = {"success": False, "sources": [], "failure_reason": "No admitted readable evidence"}
        result, client, observed, publications, events = self.run_public(
            retained=failed,
            overrides={"build_failed_public_factual_fallback": lambda: TEXT},
        )
        self.assertNotEqual(result[0], TEXT)
        self.assertTrue(result[0])
        self.assertEqual(client.calls, [])
        self.assertEqual(observed, [])
        self.assertEqual(len(publications), 1)
        record = publications[0].record
        self.assertNotEqual(record.decision.status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(record.outcome, "replaced")
        self.assertTrue(record.replacement_used)
        self.assertEqual(record.replacement_decision.status, AcceptanceStatus.ACCEPTED)
        self.assertFalse(any("Acceptance shadow:" in event for event in events))

    def test_post_generation_grounding_fallback_is_not_new_public_shadow(self):
        result, client, observed, publications, events = self.run_public(client=_RejectedClient())
        self.assertEqual(result[0], build_failed_public_factual_fallback())
        self.assertEqual(client.verifications, 2)
        self.assertEqual(observed, [])
        self.assertEqual(publications, [])
        self.assertEqual(events, [])

    def test_current_lookup_extractive_bypass_is_not_new_public_shadow(self):
        extractive = "The record identifies the service's export capability."
        result, client, observed, publications, events = self.run_public(overrides={
            "build_supported_current_lookup_fallback": lambda *args: extractive,
        })
        self.assertEqual(result[0], extractive)
        self.assertEqual(client.calls, [])
        self.assertEqual(observed, [])
        self.assertEqual(publications, [])
        self.assertEqual(events, [])

    def test_existing_public_sentence_salvage_does_not_rebind_original_full_verdict(self):
        result, client, observed, publications, events = self.run_public(client=_SalvageClient())
        self.assertEqual(result[0], TEXT)
        self.assertEqual(client.verifications, 1)
        self.assertEqual(observed, [])
        self.assertEqual(publications, [])
        self.assertEqual(events, [])

    def test_verified_core_arithmetic_keeps_authoritative_acceptance(self):
        with patch("core.acceptance_shadow.observe_public_factual_response") as observe:
            decision = MaironCore().prepare_turn("multiply 17 by 6")
        observe.assert_not_called()
        self.assertEqual(decision.direct_response, "The result is 102.")
        self.assertIsNone(decision.acceptance_shadow)
        self.assertEqual(decision.acceptance_publication.decision.status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(decision.acceptance_publication.outcome, "accepted")
        self.assertFalse(decision.acceptance_publication.replacement_used)

    def test_corrupted_core_arithmetic_is_still_replaced_from_verified_result(self):
        workflow = calculate_arithmetic(expression="17 * 6", operation="multiply",
                                        operands="17|6", display_expression="17 * 6")
        workflow.answer_fact = "The result is 204."
        with patch("core.orchestrator.calculate_arithmetic", return_value=workflow), \
                patch("core.acceptance_shadow.observe_public_factual_response") as observe:
            decision = MaironCore().prepare_turn("multiply 17 by 6")
        observe.assert_not_called()
        self.assertEqual(decision.direct_response, "The result is 102.")
        self.assertNotEqual(decision.acceptance_publication.decision.status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(decision.acceptance_publication.outcome, "replaced")
        self.assertTrue(decision.acceptance_publication.replacement_used)
        self.assertEqual(decision.acceptance_publication.replacement_decision.status, AcceptanceStatus.ACCEPTED)

    def test_provider_observation_return_is_discarded_before_history_write(self):
        run, _ = provider(observer=lambda **kwargs: SimpleNamespace(text="Suppressed replacement"))
        with redirect_stdout(io.StringIO()):
            result = run(Client(), "Which export capability does the service document?", [],
                         core_answer_contract=contract())
        self.assertEqual(result[0], TEXT)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": TEXT})

    def test_enforced_entry_points_are_the_same_bounded_core_families(self):
        expected = {
            "src/ai/ollama_provider.py": {
                "direct_verification_declined", "direct_public_evidence_unavailable",
                "direct_missing_input_fallback", "direct_verification_declined_fallback",
                "provider_ingress_verification_declined",
            },
            "src/core/orchestrator.py": {"arithmetic", "time_budget", "private_state"},
        }
        for relative, paths in expected.items():
            with self.subTest(file=relative):
                tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
                calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                         and isinstance(node.func, ast.Name)
                         and node.func.id in {"publish_core_result", "publish_time_budget",
                                              "publish_limitation_response"}]
                observed = []
                for call in calls:
                    value = next(keyword.value for keyword in call.keywords if keyword.arg == "path")
                    self.assertIsInstance(value, ast.Constant)
                    observed.append(value.value)
                self.assertEqual(set(observed), paths)
                self.assertEqual(len(observed), len(paths))


if __name__ == "__main__":
    unittest.main(verbosity=2)
