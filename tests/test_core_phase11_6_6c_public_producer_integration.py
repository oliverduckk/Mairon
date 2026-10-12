"""Offline execution of the real bounded public generation/retry/salvage path."""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_core_milestone3b3a_public_shadow_integration import provider, research, contract
from test_core_phase11_6_6c_public_content_authority import witnesses
from research.public_factual_grounding import (
    build_public_factual_generation_instruction, build_failed_public_factual_fallback,
    build_supported_current_lookup_fallback, requires_public_factual_salvage_completion,
    verify_public_factual_salvage_completion,
)
from research.public_factual_research import actual_read_url, build_public_factual_authority_context


IDENTITY = "The preview is called Avery Morgan."
BODY = "A preview called Avery Morgan exists."
BAD_RELATION = "Avery and Morgan had a disagreement."
BAD_REASON = "People discussed Avery Morgan because the reveal was a fan-favourite moment."
LIMITATION = "I cannot verify why people discussed that preview."


def completion(fulfilled=False, outcome="incomplete"):
    return {"completed": fulfilled, "outcome": outcome, "request_fulfilled": fulfilled,
            "required_claim_assessments": [], "violations": [] if fulfilled else ["incomplete_request"]}


class PublicClient:
    def __init__(self, drafts, verifications, completions=()):
        self.drafts, self.verifications, self.completions = map(iter, (drafts, verifications, completions))
        self.generations, self.completion_calls, self.calls = 0, 0, []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        system = "\n".join(message["content"] for message in kwargs["messages"] if message["role"] == "system")
        if "INTERNAL supported-subset answer-completion verifier" in system:
            self.completion_calls += 1
            content = json.dumps(next(self.completions))
        elif "INTERNAL public-factual evidence verifier" in system:
            content = json.dumps(next(self.verifications))
        else:
            self.generations += 1
            content = next(self.drafts)
        return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=[]), done_reason="stop")


def assessment(statuses, claims=None):
    value = {"supported": all(statuses), "unsupported_claims": [] if all(statuses) else ["Unsupported relation"],
             "sentence_assessments": [{"index": index, "supported": supported}
                                      for index, supported in enumerate(statuses, 1)]}
    if claims is not None:
        value["claim_assessments"] = claims
    return value


def run(client, current="What was that preview people were talking about?", body=BODY):
    retained = copy.deepcopy(research())
    retained["query"] = retained["original_query"] = "preview identity"
    retained["sources"][0]["title"] = "Avery Morgan Preview"
    retained["sources"][0]["read_result"]["content"] = body
    fn, namespace = provider(retained=retained)
    observations = []
    namespace.update({
        "build_public_factual_authority_context": build_public_factual_authority_context,
        "build_public_factual_generation_instruction": build_public_factual_generation_instruction,
        "actual_read_url": actual_read_url,
        "should_verify_public_factual_salvage_completion": requires_public_factual_salvage_completion,
        "verify_public_factual_salvage_completion": verify_public_factual_salvage_completion,
        "build_supported_current_lookup_fallback": build_supported_current_lookup_fallback,
        "build_failed_public_factual_fallback": build_failed_public_factual_fallback,
        "observe_public_factual_response": lambda **kwargs: observations.append(kwargs),
    })
    log = io.StringIO()
    with redirect_stdout(log):
        result = fn(client, current, [], core_answer_contract=contract())
    return result, observations, log.getvalue()


class PublicProducerIntegrationTests(unittest.TestCase):
    def test_retry_global_success_cannot_publish_full_name_split_after_first_rejection(self):
        good = IDENTITY + " " + LIMITATION
        client = PublicClient([BAD_RELATION, good], [
            assessment([True], witnesses(BAD_RELATION, BODY)), assessment([True, True]),
        ])
        result, observations, log = run(client)
        self.assertEqual(result[0], good)
        self.assertEqual(result[1][-1]["content"], good)
        self.assertEqual(client.generations, 2)
        self.assertNotIn(BAD_RELATION, [item["content"] for item in result[1]])
        self.assertIn("entity_span_split", log)
        self.assertEqual(len(observations), 1)

    def test_earlier_negative_legacy_verdict_does_not_let_second_positive_retry_rescue_relation(self):
        client = PublicClient([BAD_RELATION, BAD_RELATION], [
            assessment([False], witnesses(BAD_RELATION, None, supported=False)),
            assessment([True], witnesses(BAD_RELATION, BODY)),
        ])
        result, observations, _ = run(client)
        self.assertEqual(result[0], build_failed_public_factual_fallback())
        self.assertEqual(client.generations, 2)
        self.assertFalse(observations)
        self.assertNotIn(BAD_RELATION, [item["content"] for item in result[1]])

    def test_supported_identity_only_subset_cannot_silently_replace_requested_reason(self):
        bad = IDENTITY + " " + BAD_REASON
        good = IDENTITY + " " + LIMITATION
        client = PublicClient([bad, good], [
            assessment([True, True], witnesses(BAD_REASON, BODY)), assessment([True, True]),
        ], [completion()])
        result, observations, log = run(client, "Why did people discuss that preview?")
        self.assertEqual(result[0], good)
        self.assertEqual(client.generations, 2)
        self.assertEqual(client.completion_calls, 1)
        self.assertNotIn(IDENTITY, [item["content"] for item in result[1]])
        self.assertIn("did not fulfill the required answer", log)
        self.assertEqual(len(observations), 1)

    def test_identity_and_truthful_missing_reason_subset_can_be_salvaged(self):
        safe = IDENTITY + " " + LIMITATION
        bad = safe + " " + BAD_REASON
        client = PublicClient([bad], [assessment([True, True, True], witnesses(BAD_REASON, BODY))],
                              [completion(True, "bounded_limitation")])
        result, observations, _ = run(client, "Why did people discuss that preview?")
        self.assertEqual(result[0], safe)
        self.assertEqual(result[1][-1]["content"], safe)
        self.assertEqual(client.generations, 1)
        self.assertEqual(client.completion_calls, 1)
        self.assertFalse(observations, "sentence salvage remains outside common generated-public shadow lane")

    def test_reason_subsets_exhausting_bounded_retry_use_existing_public_fallback(self):
        bad = IDENTITY + " " + BAD_REASON
        client = PublicClient([bad, bad], [
            assessment([True, True], witnesses(BAD_REASON, BODY)),
            assessment([True, True], witnesses(BAD_REASON, BODY)),
        ], [completion(), completion()])
        result, observations, _ = run(client, "Why did people discuss that preview?")
        self.assertEqual(result[0], build_failed_public_factual_fallback())
        self.assertEqual(client.generations, 2)
        self.assertEqual(client.completion_calls, 2)
        self.assertFalse(observations)

    def test_body_supported_relation_and_reason_publish_unchanged(self):
        good = "People discussed Cora because Cora criticised Dax."
        client = PublicClient([good], [assessment([True], witnesses(good, good))])
        result, observations, _ = run(client, "Why did people discuss Cora?", body=good)
        self.assertEqual(result[0], good)
        self.assertEqual(client.generations, 1)
        self.assertEqual(client.completion_calls, 0)
        self.assertEqual(len(observations), 1)

    def test_ordinary_identity_answer_keeps_existing_generation_verifier_budget(self):
        client = PublicClient([IDENTITY], [assessment([True])])
        result, observations, _ = run(client, "What was that preview called?")
        self.assertEqual(result[0], IDENTITY)
        self.assertEqual(client.generations, 1)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(len(observations), 1)

    def test_new_content_obligation_diagnostics_do_not_emit_candidate_or_source_text(self):
        good = IDENTITY + " " + LIMITATION
        client = PublicClient([BAD_RELATION, good], [
            assessment([True], witnesses(BAD_RELATION, BODY)), assessment([True, True]),
        ])
        _, _, log = run(client)
        self.assertIn("sentence=1", log)
        self.assertNotIn(BAD_RELATION, log)
        self.assertNotIn(BODY, log)


if __name__ == "__main__":
    unittest.main()
