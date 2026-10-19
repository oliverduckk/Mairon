"""Classify official-source failures without guessing an unseen live packet.

These offline fixtures execute current search selection/read admission and the
existing early public-evidence publication branch. No routing repair is assumed.
"""
from __future__ import annotations

from contextlib import redirect_stdout
import copy
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
from test_core_milestone3b3a_public_shadow_integration import contract, provider
from research import public_factual_research as research
from research.public_factual_grounding import build_failed_public_factual_fallback

USER = "Check the official Orven compartment documentation and give the actual source URL."
URL = "https://docs.orven.example/reference/compartments"
ACTUAL = "https://docs.orven.example/reference/compartments.html"
BODY = "Orven compartments isolate base paths by default. Shared base paths require an explicit option."
SOURCE = {"title": "Orven compartment reference", "url": URL, "content": BODY}
THIRD = {"title": "Orven compartment guide", "url": "https://reference.example/orven", "content": BODY}


def gather(results=(SOURCE,), *, current=USER, search_ok=True, read_ok=True, actual=ACTUAL):
    calls = []
    def tool(name, arguments):
        calls.append((name, dict(arguments)))
        if name == "web_search":
            return {"success": search_ok, "results": copy.deepcopy(list(results)), "message": "Search unavailable"}
        if name == "web_read":
            return {"success": read_ok, "url": actual if arguments["url"] == URL else arguments["url"],
                    "content": BODY if read_ok else ""}
        raise AssertionError("Unexpected tool")
    with patch.object(research, "execute_tool", tool):
        data = research.gather_public_factual_research(current, max_reads=2,
            require_query_resolution=True, require_quality_evidence=True)
    return data, calls


class OfficialRetrievalClassificationTests(unittest.TestCase):
    def test_official_identity_is_read_before_third_party_result(self):
        data, calls = gather([THIRD, SOURCE])
        self.assertTrue(data["success"], data)
        self.assertEqual([args["url"] for name, args in calls if name == "web_read"][0], URL)
        self.assertEqual(data["sources"][0]["authority_tier"], "primary_official")

    def test_official_identity_after_several_search_hits_is_still_preferred(self):
        others = [dict(THIRD, url=f"https://reference{index}.example/orven") for index in range(4)]
        data, calls = gather(others + [SOURCE])
        self.assertTrue(data["success"])
        self.assertEqual(next(args["url"] for name, args in calls if name == "web_read"), URL)
        self.assertEqual(sum(name == "web_search" for name, _ in calls), 1)

    def test_actual_read_identity_is_retained_without_guessed_equivalence(self):
        data, _ = gather()
        source = data["sources"][0]
        self.assertEqual(source["url"], URL)
        self.assertEqual(research.actual_read_url(source), ACTUAL)

    def test_successful_authority_snapshot_preserves_explicit_obligations(self):
        data, _ = gather()
        context = research.build_public_factual_authority_context(data, USER)
        self.assertTrue(context["requirements"]["official_source_required"])
        self.assertEqual(context["sources"][0]["read_url"], ACTUAL)
        self.assertEqual(context["sources"][0]["authority_tier"], "primary_official")

    def test_read_failure_never_turns_discovery_into_admitted_evidence(self):
        data, calls = gather(read_ok=False)
        self.assertFalse(data["success"])
        self.assertEqual(data["raw_readable_source_count"], 0)
        self.assertEqual(data["accepted_source_count"], 0)
        self.assertIsNone(research.actual_read_url(data["sources"][0]))
        self.assertEqual([name for name, _ in calls], ["web_search", "web_read"])

    def test_search_failure_is_observable_separately_from_read_admission(self):
        data, calls = gather([], search_ok=False)
        self.assertFalse(data["success"])
        self.assertEqual(data["read_attempt_count"], 0)
        self.assertEqual([name for name, _ in calls], ["web_search"])
        self.assertEqual(data["failure_reason"], "Search unavailable")

    def test_empty_search_is_not_a_generation_or_verifier_failure(self):
        data, calls = gather([])
        self.assertFalse(data["success"])
        self.assertEqual(data["search_result_count"], 0)
        self.assertEqual(data["read_attempt_count"], 0)
        self.assertEqual(len(calls), 1)

    def test_readable_third_party_source_cannot_satisfy_official_request(self):
        data, _ = gather([THIRD])
        self.assertFalse(data["success"])
        self.assertEqual(data["raw_readable_source_count"], 1)
        self.assertEqual(data["accepted_source_count"], 0)
        self.assertIn("explicit_official_documentation_required", data["sources"][0]["relevance_reasons"])

    def test_official_label_in_search_title_does_not_create_authority(self):
        data, _ = gather([dict(THIRD, title="Official Orven compartment documentation")])
        self.assertFalse(data["success"])
        self.assertNotEqual(data["sources"][0]["authority_tier"], "primary_official")

    def test_unrequested_official_authority_does_not_reject_ordinary_evidence(self):
        data, _ = gather([THIRD], current="Describe Orven compartments.")
        self.assertTrue(data["success"], data)
        self.assertFalse(data["official_documentation_required"])

    def test_followup_success_does_not_retroactively_change_first_turn_failure(self):
        first, first_calls = gather(read_ok=False)
        saved = copy.deepcopy(first)
        second, second_calls = gather()
        self.assertEqual(first, saved)
        self.assertFalse(first["success"])
        self.assertTrue(second["success"])
        self.assertEqual(research.actual_read_url(second["sources"][0]), ACTUAL)
        self.assertEqual(sum(name == "web_search" for name, _ in first_calls + second_calls), 2)

    def test_page_read_may_fail_even_when_official_identity_was_selected(self):
        data, calls = gather([THIRD, SOURCE], read_ok=False)
        self.assertEqual(next(args["url"] for name, args in calls if name == "web_read"), URL)
        self.assertFalse(data["success"])
        self.assertTrue(data["official_documentation_required"])

    def test_readable_count_is_admitted_count_not_raw_read_count(self):
        data, _ = gather([THIRD, SOURCE])
        self.assertEqual(data["raw_readable_source_count"], 2)
        self.assertEqual(data["readable_source_count"], 1)
        self.assertEqual(data["accepted_source_count"], 1)

    def test_early_evidence_failure_publishes_existing_bounded_path_without_generation(self):
        data, _ = gather(read_ok=False)
        function, namespace = provider(retained=data)
        publications, observations = [], []
        text = build_failed_public_factual_fallback()
        namespace.update({
            "build_stable_model_knowledge_fallback": lambda **kw: None,
            "build_failed_public_factual_fallback": lambda: text,
            "publish_limitation_response": lambda **kw: publications.append(kw) or SimpleNamespace(text=text),
            "observe_public_factual_response": lambda **kw: observations.append(kw),
        })
        class NoGeneration:
            def chat(self, **kwargs):
                raise AssertionError("No model call allowed before sufficient evidence")
        with redirect_stdout(io.StringIO()):
            result = function(NoGeneration(), USER, [], core_answer_contract=contract())
        self.assertEqual(result[0], text)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": text})
        self.assertEqual([item["path"] for item in publications], ["direct_public_evidence_unavailable"])
        self.assertFalse(observations)


if __name__ == "__main__":
    unittest.main()
