"""Real consequential public producer must preserve USER applicability.

The existing research packet, public verifier, producer retries and fallback
execute offline. Scripted global/source verdicts cannot select a user's scope.
No common generated-public enforcement, live retrieval or tools are involved.
"""
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

from core.seriousness import (
    assess_consequential_advice, build_consequential_advice_instruction,
    build_consequential_research_query, find_consequential_role_violations,
    find_consequential_tone_violations,
)
from research.consequential_obligations import consequential_claim_obligations
from research.public_factual_grounding import (
    _split_draft_sentences, build_failed_public_advice_fallback,
    verify_public_factual_draft,
)
from test_core_milestone3b3a_public_shadow_integration import provider, research, contract

USER = "I sent money to the wrong account. What should I do?"
SCOPED_USER = ("My provider is AlderPay. I am in Westhaven. My payment rail is CedarLine. " + USER)
PROCEDURE = "File Form Kestrel within 7 days."
BODY_SCOPE = "Provider: AlderPay. Jurisdiction: Westhaven. Rail: CedarLine. "
BODY_PROCEDURE = "Customers must file Form Kestrel within 7 days to cancel the payment."
GOOD = ("Contact your sending bank or payment provider promptly through its official support "
        "channel and follow its documented mistaken-payment process.")


def retained(*bodies):
    value = copy.deepcopy(research())
    original = value["sources"][0]
    value["query"] = value["original_query"] = "mistaken payment support"
    value["sources"] = []
    value["discovered_sources"] = []
    for index, body in enumerate(bodies or (BODY_SCOPE + BODY_PROCEDURE + " " + GOOD,), 1):
        source = copy.deepcopy(original)
        source["title"] = "Provider support procedure " + str(index)
        source["url"] = "https://support" + str(index) + ".example/procedure"
        source["source_host"] = "support" + str(index) + ".example"
        source["read_result"] = {"success": True, "url": source["url"], "content": body}
        value["sources"].append(source)
        value["discovered_sources"].append({"title": source["title"], "url": source["url"]})
    return value


def positive(candidate, *, quote=BODY_PROCEDURE, source_id="S1", scoped=True):
    sentences = _split_draft_sentences(candidate)
    value = {"supported": True, "unsupported_claims": [],
             "sentence_assessments": [{"index": index, "supported": True}
                                      for index in range(1, len(sentences) + 1)]}
    if scoped:
        value["consequential_assessments"] = [
            {"index": item["index"], "supported": True, "source_id": source_id,
             "source_quote": quote} for item in consequential_claim_obligations(sentences)
        ]
    return value


class PublicAdviceClient:
    def __init__(self, drafts, verdicts):
        self.drafts = iter(drafts)
        self.verdicts = iter(verdicts)
        self.calls = []
        self.generations = self.verifications = 0

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        system = "\n".join(item["content"] for item in kwargs["messages"] if item["role"] == "system")
        if "INTERNAL public-factual evidence verifier" in system:
            self.verifications += 1
            content = json.dumps(next(self.verdicts))
        else:
            self.generations += 1
            content = next(self.drafts)
        return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=[]), done_reason="stop")


def run(client, current=USER, *, evidence=None, history=(), domain=None):
    fn, namespace = provider(retained=evidence or retained())
    observations = []
    namespace.update({
        "assess_consequential_advice": (assess_consequential_advice if domain is None else
                                       lambda *_: SimpleNamespace(domain=domain)),
        "build_consequential_advice_instruction": build_consequential_advice_instruction,
        "build_consequential_research_query": build_consequential_research_query,
        "find_consequential_role_violations": find_consequential_role_violations,
        "find_consequential_tone_violations": find_consequential_tone_violations,
        "build_failed_public_advice_fallback": build_failed_public_advice_fallback,
        "verify_public_factual_draft": verify_public_factual_draft,
        "observe_public_factual_response": lambda **kwargs: observations.append(kwargs),
    })
    output = io.StringIO()
    with redirect_stdout(output):
        result = fn(client, current, list(history), core_answer_contract=contract(
            intent="consequential_advice", mode="public_source_verified_advice"))
    return result, observations, output.getvalue()


class ConsequentialApplicabilityProductionTests(unittest.TestCase):
    def assert_published(self, result, expected, *withheld):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": expected})
        self.assertEqual(result[2:], (None, None))
        for text in withheld:
            self.assertNotIn(text, [item["content"] for item in result[1]])

    def assert_retry(self, bad=PROCEDURE, current=USER, *, evidence=None, verdict=None, history=(), domain=None):
        client = PublicAdviceClient([bad, GOOD], [positive(bad) if verdict is None else verdict, positive(GOOD)])
        result, observations, _ = run(client, current, evidence=evidence, history=history, domain=domain)
        self.assert_published(result, GOOD, bad)
        self.assertEqual((client.generations, client.verifications), (2, 2))
        self.assertEqual(len(client.calls), 4, "No additional model loop is introduced")
        self.assertFalse(observations, "Consequential advice is outside common public shadow generation")
        self.assertTrue(all(not call.get("tools") for call in client.calls))
        return client

    def assert_single(self, candidate=GOOD, current=USER, *, evidence=None, verdict=None, history=(), domain=None):
        client = PublicAdviceClient([candidate], [positive(candidate) if verdict is None else verdict])
        result, observations, _ = run(client, current, evidence=evidence, history=history, domain=domain)
        self.assert_published(result, candidate)
        self.assertEqual((client.generations, client.verifications), (1, 1))
        self.assertFalse(observations)
        return client

    def test_unspecified_user_scope_cannot_adopt_a_retrieved_procedure(self):
        self.assert_retry()

    def test_global_positive_without_applicability_assessments_cannot_publish(self):
        self.assert_retry(verdict=positive(PROCEDURE, scoped=False))

    def test_mixed_jurisdictions_cannot_be_merged_into_user_procedure(self):
        other = "Provider: BirchPay. Jurisdiction: Eastmere. Rail: ElmLine. " + BODY_PROCEDURE
        self.assert_retry(evidence=retained(BODY_SCOPE + BODY_PROCEDURE + " " + GOOD, other))

    def test_a_matching_country_does_not_supply_an_unspecified_provider_and_rail(self):
        self.assert_retry(current="I am in Westhaven. " + USER)

    def test_a_matching_provider_does_not_supply_an_unspecified_country_and_rail(self):
        self.assert_retry(current="My provider is AlderPay. " + USER)

    def test_matching_explicit_user_scope_and_body_supported_detail_can_publish(self):
        self.assert_single(PROCEDURE, SCOPED_USER)

    def test_mismatching_user_jurisdiction_cannot_publish_supported_source_detail(self):
        self.assert_retry(current=SCOPED_USER.replace("Westhaven", "Eastmere"))

    def test_mismatching_user_provider_cannot_publish_supported_source_detail(self):
        self.assert_retry(current=SCOPED_USER.replace("AlderPay", "BirchPay"))

    def test_mismatching_user_rail_cannot_publish_supported_source_detail(self):
        self.assert_retry(current=SCOPED_USER.replace("CedarLine", "ElmLine"))

    def test_prior_user_scope_is_available_to_the_real_followup_verifier(self):
        history = [{"role": "user", "content": SCOPED_USER},
                   {"role": "assistant", "content": "Contact your provider."}]
        self.assert_single(PROCEDURE, USER, history=history)

    def test_latest_user_scope_correction_defeats_the_previous_match(self):
        history = [{"role": "user", "content": SCOPED_USER}]
        self.assert_retry(current="My provider is BirchPay. " + USER, history=history)

    def test_assistant_scope_cannot_make_a_procedure_applicable(self):
        history = [{"role": "assistant", "content": SCOPED_USER}]
        self.assert_retry(history=history)

    def test_hypothetical_user_scope_cannot_make_a_procedure_applicable(self):
        current = "If my provider is AlderPay and I am in Westhaven, suppose my payment rail is CedarLine. " + USER
        self.assert_retry(current=current)

    def test_tentative_named_scope_is_not_actual_user_applicability(self):
        current = "My provider might be AlderPay. I am in Westhaven. My payment rail is CedarLine. " + USER
        self.assert_retry(current=current)

    def test_quoted_example_scope_is_not_actual_user_applicability(self):
        current = ('The sample says "My provider is AlderPay. I am in Westhaven. '
                   'My payment rail is CedarLine." ' + USER)
        self.assert_retry(current=current)

    def test_named_system_list_cannot_silently_select_user_applicability(self):
        candidate = "Completion depends on the system (ARX, BVQ)."
        self.assert_retry(candidate)

    def test_title_and_search_metadata_cannot_supply_applicability(self):
        value = retained(BODY_PROCEDURE + " " + GOOD)
        value["sources"][0]["title"] = BODY_SCOPE
        value["sources"][0]["snippet"] = BODY_SCOPE
        self.assert_retry(current=SCOPED_USER, evidence=value)

    def test_rejected_procedural_source_does_not_reenter_through_its_body_or_title(self):
        value = retained(BODY_SCOPE + BODY_PROCEDURE, GOOD)
        value["sources"][0]["accepted_as_evidence"] = False
        value["sources"][0]["relevance_status"] = "rejected"
        self.assert_retry(current=SCOPED_USER, evidence=value)

    def test_discovered_but_unread_procedural_source_is_not_an_applicable_witness(self):
        value = retained(BODY_SCOPE + BODY_PROCEDURE, GOOD)
        value["sources"][0]["read_success"] = False
        value["sources"][0]["read_result"]["success"] = False
        self.assert_retry(current=SCOPED_USER, evidence=value)

    def test_unsupported_numeric_deadline_cannot_publish_even_with_matching_scope(self):
        body = BODY_SCOPE + "Customers must file Form Kestrel to report the payment. " + GOOD
        value = positive(PROCEDURE, quote="Customers must file Form Kestrel to report the payment.")
        self.assert_retry(current=SCOPED_USER, evidence=retained(body), verdict=value)

    def test_changed_numeric_deadline_cannot_borrow_source_support(self):
        candidate = "File Form Kestrel within 11 days."
        self.assert_retry(candidate, SCOPED_USER, verdict=positive(candidate))

    def test_working_day_deadline_cannot_become_calendar_day_deadline(self):
        body = BODY_SCOPE + BODY_PROCEDURE.replace("7 days", "7 business days") + " " + GOOD
        self.assert_retry(current=SCOPED_USER, evidence=retained(body),
                          verdict=positive(PROCEDURE, quote=BODY_PROCEDURE.replace("7 days", "7 business days")))

    def test_exact_numeric_deadline_remains_available_when_supported_and_applicable(self):
        self.assert_single(PROCEDURE, SCOPED_USER)

    def test_unwitnessed_exclusive_outcome_cannot_publish(self):
        candidate = "Prompt contact is your sole leverage."
        self.assert_retry(candidate, SCOPED_USER, verdict=positive(candidate, quote=GOOD))

    def test_unwitnessed_followup_cadence_cannot_publish(self):
        candidate = "Follow up weekly."
        self.assert_retry(candidate, SCOPED_USER, verdict=positive(candidate, quote=GOOD))

    def test_provider_neutral_urgent_first_step_stays_available(self):
        self.assert_single()

    def test_truthful_refusal_to_guess_scope_specific_recovery_stays_available(self):
        candidate = "I cannot establish whether the payment can be cancelled without your provider's documented process."
        self.assert_single(candidate, evidence=retained(GOOD), verdict=positive(candidate, scoped=False))

    def test_sender_is_not_recast_as_holder_of_the_mistaken_funds(self):
        bad = "Do not spend the money in your account."
        client = PublicAdviceClient([bad, GOOD], [positive(bad), positive(GOOD)])
        result, _, _ = run(client)
        self.assert_published(result, GOOD, bad)
        self.assertEqual(client.generations, 2)
        self.assertLessEqual(client.verifications, 2)

    def test_sender_contact_direction_remains_sending_provider_first(self):
        candidate = "Contact the recipient first."
        client = PublicAdviceClient([candidate, GOOD], [positive(candidate), positive(GOOD)])
        result, _, _ = run(client)
        self.assert_published(result, GOOD, candidate)
        self.assertEqual(client.generations, 2)

    def test_every_rejected_procedure_retry_uses_the_existing_two_draft_bound(self):
        client = PublicAdviceClient([PROCEDURE, PROCEDURE], [positive(PROCEDURE)] * 2)
        result, observations, _ = run(client)
        self.assert_published(result, build_failed_public_advice_fallback(domain="financial", user_input=USER), PROCEDURE)
        self.assertEqual((client.generations, client.verifications), (2, 2))
        self.assertEqual(len(client.calls), 4)
        self.assertFalse(observations)

    def test_missing_procedure_assessment_fails_closed_on_both_drafts(self):
        client = PublicAdviceClient([PROCEDURE, PROCEDURE], [positive(PROCEDURE, scoped=False)] * 2)
        result, _, _ = run(client, SCOPED_USER)
        self.assertNotEqual(result[0], PROCEDURE)
        self.assertNotIn(PROCEDURE, [item["content"] for item in result[1]])
        self.assertEqual((client.generations, client.verifications), (2, 2))

    def test_malformed_positive_scoped_result_cannot_publish(self):
        value = positive(PROCEDURE)
        value["consequential_assessments"][0]["supported"] = "yes"
        self.assert_retry(current=SCOPED_USER, verdict=value)

    def test_source_identifier_cannot_name_candidate_or_assistant_as_evidence(self):
        self.assert_retry(current=SCOPED_USER, verdict=positive(PROCEDURE, source_id="candidate", quote=PROCEDURE))

    def test_explicit_scope_guard_generalises_to_an_identity_document_incident(self):
        user = "I lost my identity document. What should I do?"
        self.assert_retry("File Form Kestrel within 7 days.", user, domain="identity_document")

    def test_new_scope_protocol_uses_one_existing_verifier_call_per_draft(self):
        client = self.assert_retry()
        verifier_calls = [call for call in client.calls if "format" in call]
        self.assertEqual(len(verifier_calls), 2)
        self.assertIn("consequential_assessments", verifier_calls[0]["format"]["properties"])
        self.assertEqual(sum("INTERNAL public-factual evidence verifier" in message["content"]
                             for call in client.calls for message in call["messages"]), 2)


if __name__ == "__main__":
    unittest.main()
