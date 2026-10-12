"""Real bounded public retry and salvage preserve identity/date obligations."""
from contextlib import redirect_stdout
import copy
import io
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_core_milestone3b3a_public_shadow_integration import provider, research, contract
from test_core_phase11_6_6c_public_producer_integration import PublicClient, assessment, completion
from research.public_factual_grounding import (
    build_failed_public_factual_fallback, build_supported_current_lookup_fallback,
    build_public_factual_generation_instruction, build_public_factual_retry_instruction,
    requires_public_factual_salvage_completion, verify_public_factual_salvage_completion,
)
from research.public_factual_research import actual_read_url, build_public_factual_authority_context
from research.public_claim_obligations import public_identity_date_obligations


GOOD = 'The preview is titled "Avery Morgan".'
BAD = 'The preview is titled "Avery & Morgan".'
BAD_DATE = "The episode aired on April 7, 2028."
BODY = 'The preview is titled "Avery Morgan". A preview exists.'


def run(client, current="What was that preview called?", *, body=BODY, title='[April 7, 2028] "Avery Morgan" Preview'):
    retained = copy.deepcopy(research())
    retained["query"] = retained["original_query"] = "preview identity"
    retained["sources"][0]["title"] = title
    retained["sources"][0]["read_result"]["content"] = body
    fn, namespace = provider(retained=retained)
    observations = []
    namespace.update({
        "build_public_factual_authority_context": build_public_factual_authority_context,
        "build_public_factual_generation_instruction": build_public_factual_generation_instruction,
        "actual_read_url": actual_read_url,
        "build_public_factual_retry_instruction": build_public_factual_retry_instruction,
        "should_verify_public_factual_salvage_completion": requires_public_factual_salvage_completion,
        "verify_public_factual_salvage_completion": verify_public_factual_salvage_completion,
        "build_failed_public_factual_fallback": build_failed_public_factual_fallback,
        "build_supported_current_lookup_fallback": build_supported_current_lookup_fallback,
        "observe_public_factual_response": lambda **kwargs: observations.append(kwargs),
    })
    output = io.StringIO()
    with redirect_stdout(output):
        result = fn(client, current, [], core_answer_contract=contract())
    return result, observations, output.getvalue()


class PublicIdentityIntegrationTests(unittest.TestCase):
    def test_positive_retry_cannot_reauthorize_mutated_title(self):
        client = PublicClient([BAD, GOOD], [assessment([True]), assessment([True])])
        result, observed, output = run(client)
        self.assertEqual(result[0], GOOD)
        self.assertEqual(result[1][-1]["content"], GOOD)
        self.assertEqual(client.generations, 2)
        self.assertEqual(len(observed), 1)
        self.assertIn("literal_identity_witness_missing", output)
        self.assertNotIn(BAD, [message["content"] for message in result[1]])

    def test_original_negative_then_positive_mutated_title_exhausts_same_bound(self):
        client = PublicClient([BAD, BAD], [assessment([False]), assessment([True])])
        result, observed, _ = run(client)
        self.assertEqual(result[0], build_failed_public_factual_fallback())
        self.assertEqual(client.generations, 2)
        self.assertFalse(observed)

    def test_global_positive_wrong_event_date_cannot_publish(self):
        client = PublicClient([BAD_DATE, GOOD], [assessment([True]), assessment([True])])
        result, observed, output = run(client)
        self.assertEqual(result[0], GOOD)
        self.assertEqual(client.generations, 2)
        self.assertIn("event_date_role_witness_missing", output)
        self.assertEqual(len(observed), 1)

    def test_bad_date_can_be_removed_while_requested_identity_survives(self):
        client = PublicClient([GOOD + " " + BAD_DATE], [assessment([True, True])], [completion(True, "factual_answer")])
        result, observed, _ = run(client)
        self.assertEqual(result[0], GOOD)
        self.assertEqual(client.generations, 1)
        self.assertEqual(client.completion_calls, 1)
        self.assertFalse(observed, "salvage remains outside common generated-public shadow lane")

    def test_surviving_existence_fact_does_not_complete_requested_title(self):
        client = PublicClient(["A preview exists. " + BAD, GOOD],
                              [assessment([True, True]), assessment([True])], [completion()])
        result, observed, output = run(client)
        self.assertEqual(result[0], GOOD)
        self.assertEqual(client.generations, 2)
        self.assertEqual(client.completion_calls, 1)
        self.assertIn("did not fulfill the required answer", output)
        self.assertEqual(len(observed), 1)

    def test_identity_plus_truthful_unknown_date_completes_date_request(self):
        safe = GOOD + " I cannot verify when the episode aired."
        client = PublicClient([safe + " " + BAD_DATE], [assessment([True, True, True])],
                              [completion(True, "bounded_limitation")])
        result, observed, _ = run(client, "When did the episode air?")
        self.assertEqual(result[0], safe)
        self.assertEqual(client.generations, 1)
        self.assertEqual(client.completion_calls, 1)
        self.assertFalse(observed)

    def test_wrong_date_subsets_cannot_exhaust_into_irrelevant_identity(self):
        bad = GOOD + " " + BAD_DATE
        client = PublicClient([bad, bad], [assessment([True, True]), assessment([True, True])],
                              [completion(), completion()])
        result, observed, _ = run(client, "When did the episode air?")
        self.assertEqual(result[0], build_failed_public_factual_fallback())
        self.assertEqual(client.generations, 2)
        self.assertEqual(client.completion_calls, 2)
        self.assertFalse(observed)

    def test_valid_body_identity_and_event_date_publish_unchanged(self):
        text = GOOD + " " + BAD_DATE
        client = PublicClient([text], [assessment([True, True])])
        result, observed, _ = run(client, "What is the preview title and air date?", body=text)
        self.assertEqual(result[0], text)
        self.assertEqual(client.generations, 1)
        self.assertEqual(client.completion_calls, 0)
        self.assertEqual(len(observed), 1)

    def test_ordinary_identity_call_budget_is_unchanged_without_deleted_units(self):
        client = PublicClient([GOOD], [assessment([True])])
        result, observed, _ = run(client)
        self.assertEqual(result[0], GOOD)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(len(observed), 1)

    def test_bound_completion_requires_actual_core_identity_obligation(self):
        packet = {"sources": [{"title": "Avery Morgan", "content_excerpt": BODY}], "freshness_required": False}
        self.assertFalse(requires_public_factual_salvage_completion(contract(), packet, user_input="What was the title?"))
        self.assertTrue(requires_public_factual_salvage_completion(contract(), packet, user_input="What was the title?",
                        identity_date_obligations=public_identity_date_obligations([BAD])))

    def test_bound_date_completion_requires_actual_core_date_obligation(self):
        packet = {"sources": [{"title": "Preview", "content_excerpt": BODY}], "freshness_required": False}
        self.assertTrue(requires_public_factual_salvage_completion(contract(), packet, user_input="When did it air?",
                        identity_date_obligations=public_identity_date_obligations([BAD_DATE])))

    def test_identity_date_diagnostics_do_not_expose_title_or_date_prose(self):
        client = PublicClient([BAD, GOOD], [assessment([True]), assessment([True])])
        _, _, output = run(client)
        self.assertIn("sentence=1", output)
        self.assertNotIn(BAD, output)
        self.assertNotIn(BAD_DATE, output)


if __name__ == "__main__":
    unittest.main()
