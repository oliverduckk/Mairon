"""Neutral consequential applicability and literal witness regressions."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.seriousness import find_consequential_role_violations
from research.consequential_obligations import (
    consequential_user_scope, consequential_claim_obligations,
    consequential_assessment_schema, consequential_claim_failures,
)
from research.public_factual_grounding import (
    PUBLIC_FACTUAL_VERIFIER_RESPONSE_SCHEMA, verify_public_factual_draft,
    build_failed_public_advice_fallback,
)

USER = ("My provider is ArborBank. I am in Westhaven. My payment rail is CedarLine. "
        "I sent money to the wrong account. What should I do?")
UNSCOPED = "I sent money to the wrong account. What should I do?"
BODY = ("Provider: ArborBank. Jurisdiction: Westhaven. Rail: CedarLine. "
        "Customers must file Form Kestrel within 7 business days to cancel the payment.")
DETAIL = "File Form Kestrel within 7 business days."
GENERIC = "Contact your sending bank promptly through its official support channel and follow its documented process."


def packet(body=BODY, **state):
    source = {"source_id": "S1", "content_excerpt": body, "title": "Provider guidance",
              "url": "https://support.example/process", "read_success": True,
              "accepted_as_evidence": True, "relevance_status": "accepted"}
    source.update(state)
    return {"research_kind": "public_factual", "freshness_required": False, "sources": [source]}


def assessments(text=DETAIL, quote=BODY, source_id="S1", supported=True):
    return [{"index": item["index"], "supported": supported,
             "source_id": source_id if supported else None,
             "source_quote": quote if supported else None}
            for item in consequential_claim_obligations([text])]


class Client:
    def __init__(self, verdict):
        self.verdict, self.calls = verdict, []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.verdict)))


def verify(text=DETAIL, user=USER, source=None, scoped=None, conversation=None, domain="financial"):
    state = source or packet()
    verdict = {"supported": True, "unsupported_claims": [],
               "sentence_assessments": [{"index": 1, "supported": True}]}
    if scoped is not None:
        verdict["consequential_assessments"] = scoped
    client = Client(verdict)
    result = verify_public_factual_draft(client, "replaceable-local-model", user, text,
                                        json.dumps(state), consequential_domain=domain,
                                        user_conversation=conversation)
    return result, client


class ConsequentialScopeTests(unittest.TestCase):
    def test_explicit_named_scope_is_normalised_by_identity(self):
        self.assertEqual(consequential_user_scope(USER),
                         {"provider": "arborbank", "jurisdiction": "westhaven", "rail": "cedarline"})

    def test_source_cannot_supply_missing_user_scope(self):
        result, _ = verify(user=UNSCOPED, scoped=assessments())
        self.assertTrue(result)
        self.assertIn("user_applicability_scope_unavailable", " ".join(result))

    def test_generic_prompt_official_support_is_unscoped(self):
        self.assertEqual(consequential_claim_obligations([GENERIC]), ())
        result, client = verify(GENERIC, UNSCOPED, packet("Contact the sending bank through official support."))
        self.assertFalse(result)
        self.assertEqual(len(client.calls), 1)

    def test_generic_report_to_provider_is_not_a_concrete_recovery_rule(self):
        text = "Report the mistake to your bank immediately."
        self.assertEqual(consequential_claim_obligations([text]), ())

    def test_generic_ask_whether_recovery_possible_is_not_a_guarantee(self):
        text = "Ask your provider whether it can recover the payment."
        self.assertEqual(consequential_claim_obligations([text]), ())

    def test_refusal_to_guess_preserves_the_known_limitation(self):
        text = "I won't guess whether the transfer can still be stopped without provider-specific evidence."
        self.assertEqual(consequential_claim_obligations([text]), ())

    def test_generic_cannot_hide_a_factual_tail(self):
        text = "Ask your provider whether it can recover the payment, but your bank will refund it."
        self.assertTrue(consequential_claim_obligations([text]))

    def test_matching_single_source_scope_and_body_support_can_pass(self):
        result, _ = verify(scoped=assessments())
        self.assertFalse(result)
        self.assertEqual(result.accepted_sentences, [DETAIL])

    def test_mismatching_jurisdiction_rejects_a_positive_verdict(self):
        result, _ = verify(user=USER.replace("Westhaven", "Eastmere"), scoped=assessments())
        self.assertTrue(result)
        self.assertIn("consequential_applicability_mismatch", " ".join(result))
        self.assertEqual(result.accepted_sentences, [])

    def test_mismatching_provider_rejects(self):
        result, _ = verify(user=USER.replace("ArborBank", "BirchPay"), scoped=assessments())
        self.assertTrue(result)

    def test_mismatching_rail_rejects(self):
        result, _ = verify(user=USER.replace("CedarLine", "OakNetwork"), scoped=assessments())
        self.assertTrue(result)

    def test_missing_user_provider_does_not_inherit_source_provider(self):
        user = USER.replace("My provider is ArborBank. ", "")
        self.assertTrue(verify(user=user, scoped=assessments())[0])

    def test_missing_user_country_does_not_inherit_source_country(self):
        user = USER.replace("I am in Westhaven. ", "")
        self.assertTrue(verify(user=user, scoped=assessments())[0])

    def test_mixed_country_sources_cannot_be_merged(self):
        state = packet()
        state["sources"].append({**state["sources"][0], "source_id": "S2",
                                 "content_excerpt": BODY.replace("Westhaven", "Eastmere")})
        values = assessments()
        values[1] = {**values[1], "source_id": "S2", "source_quote": state["sources"][1]["content_excerpt"]}
        self.assertTrue(verify(source=state, scoped=values)[0])

    def test_source_body_with_ambiguous_multiple_countries_fails_closed(self):
        body = BODY + " Jurisdiction: Eastmere."
        self.assertTrue(verify(source=packet(body), scoped=assessments(quote=body))[0])

    def test_source_title_is_not_applicability(self):
        body = "Customers must file Form Kestrel within 7 business days to cancel the payment."
        state = packet(body, title="Provider: ArborBank. Jurisdiction: Westhaven. Rail: CedarLine.")
        self.assertTrue(verify(source=state, scoped=assessments(quote=body))[0])

    def test_search_snippet_is_not_applicability(self):
        body = "Customers must file Form Kestrel within 7 business days to cancel the payment."
        state = packet(body, search_snippet="Provider: ArborBank. Jurisdiction: Westhaven. Rail: CedarLine.")
        self.assertTrue(verify(source=state, scoped=assessments(quote=body))[0])

    def test_source_url_is_not_user_applicability(self):
        state = packet(url="https://arborbank.westhaven.example/cedarline")
        self.assertTrue(verify(user=UNSCOPED, source=state, scoped=assessments())[0])

    def test_unreadable_source_cannot_witness_procedure(self):
        self.assertTrue(verify(source=packet(read_success=False), scoped=assessments())[0])

    def test_rejected_source_cannot_witness_procedure(self):
        self.assertTrue(verify(source=packet(accepted_as_evidence=False), scoped=assessments())[0])

    def test_duplicate_source_ids_do_not_bind_a_witness(self):
        state = packet()
        state["sources"].append(copy.deepcopy(state["sources"][0]))
        self.assertTrue(verify(source=state, scoped=assessments())[0])

    def test_candidate_prose_is_not_a_source_witness(self):
        self.assertTrue(verify(scoped=assessments(quote=DETAIL))[0])

    def test_missing_scoped_assessments_fail_closed_despite_global_true(self):
        self.assertTrue(verify()[0])

    def test_empty_scoped_assessments_fail_closed(self):
        self.assertTrue(verify(scoped=[])[0])

    def test_incomplete_scoped_assessments_fail_closed(self):
        self.assertTrue(verify(scoped=assessments()[:1])[0])

    def test_duplicate_scoped_index_fails_closed(self):
        values = assessments()
        values[1]["index"] = 1
        self.assertTrue(verify(scoped=values)[0])

    def test_malformed_supported_type_fails_closed(self):
        values = assessments()
        values[0]["supported"] = "yes"
        self.assertTrue(verify(scoped=values)[0])

    def test_explicit_scoped_negative_cannot_be_overridden(self):
        self.assertTrue(verify(scoped=assessments(supported=False))[0])

    def test_source_identifier_not_loaded_fails_closed(self):
        self.assertTrue(verify(scoped=assessments(source_id="S99"))[0])

    def test_wrong_numeric_deadline_rejects(self):
        text = DETAIL.replace("7", "11")
        self.assertTrue(verify(text, scoped=assessments(text))[0])

    def test_calendar_and_business_days_are_not_interchangeable(self):
        text = DETAIL.replace("business ", "")
        self.assertTrue(verify(text, scoped=assessments(text))[0])

    def test_opposite_deadline_direction_rejects(self):
        text = DETAIL.replace("within", "after")
        self.assertTrue(verify(text, scoped=assessments(text))[0])

    def test_before_and_after_are_not_interchangeable(self):
        body = BODY.replace("within", "before")
        text = DETAIL.replace("within", "after")
        self.assertTrue(verify(text, source=packet(body), scoped=assessments(text, body))[0])

    def test_range_endpoint_cannot_change(self):
        body = BODY.replace("7", "3 to 7")
        text = DETAIL.replace("7", "3 to 9")
        self.assertTrue(verify(text, source=packet(body), scoped=assessments(text, body))[0])

    def test_compound_cardinal_duration_creates_an_obligation(self):
        text = "You have one hundred days."
        self.assertTrue(any(item["kind"] == "procedure_time" for item in consequential_claim_obligations([text])))
        self.assertTrue(verify(text, UNSCOPED, scoped=assessments(text))[0])

    def test_compound_cardinal_and_digits_can_represent_same_supported_duration(self):
        text = "File Form Kestrel within one hundred business days."
        body = BODY.replace("7", "100")
        self.assertFalse(verify(text, source=packet(body), scoped=assessments(text, body))[0])

    def test_word_and_digit_cardinals_are_equivalent(self):
        text = DETAIL.replace("7", "seven")
        self.assertFalse(verify(text, scoped=assessments(text))[0])

    def test_unwitnessed_daily_followup_rejects(self):
        text = "Follow up daily."
        self.assertTrue(verify(text, scoped=assessments(text))[0])

    def test_witnessed_daily_schedule_needs_matching_scope(self):
        text = "Follow up daily."
        body = BODY + " Follow up daily."
        self.assertFalse(verify(text, source=packet(body), scoped=assessments(text, body))[0])

    def test_only_leverage_claim_needs_a_corresponding_witness(self):
        text = "Speed is your only real leverage."
        self.assertTrue(verify(text, scoped=assessments(text))[0])

    def test_entirely_and_guaranteed_create_bounded_obligations(self):
        for text in ("Recovery is entirely in your hands.", "Recovery is guaranteed."):
            with self.subTest(text=text):
                self.assertTrue(consequential_claim_obligations([text]))
                self.assertTrue(verify(text, UNSCOPED, scoped=assessments(text))[0])

    def test_unknown_named_system_list_cannot_select_user_scope(self):
        text = "That depends on the system (XRA, BVQ, CTL)."
        self.assertTrue(any(item["kind"] == "named_applicability" for item in consequential_claim_obligations([text])))
        self.assertTrue(verify(text, UNSCOPED, scoped=assessments(text))[0])

    def test_transaction_reference_is_not_a_provider_selection(self):
        self.assertEqual(consequential_claim_obligations(["Keep your transaction reference A314 handy."]), ())

    def test_assistant_history_cannot_create_scope(self):
        prior = [{"role": "assistant", "content": USER}]
        self.assertEqual(consequential_user_scope(UNSCOPED, prior), {})
        self.assertTrue(verify(user=UNSCOPED, scoped=assessments(), conversation=prior)[0])

    def test_prior_actual_user_scope_remains_available(self):
        prior = [{"role": "user", "content": USER}]
        self.assertFalse(verify(user=UNSCOPED, scoped=assessments(), conversation=prior)[0])

    def test_latest_user_provider_correction_wins(self):
        prior = [{"role": "user", "content": USER}]
        current = "My provider is BirchPay. " + UNSCOPED
        self.assertEqual(consequential_user_scope(current, prior)["provider"], "birchpay")
        self.assertTrue(verify(user=current, scoped=assessments(), conversation=prior)[0])

    def test_latest_user_provider_negation_clears_stale_scope(self):
        prior = [{"role": "user", "content": USER}]
        for negative in ("My provider is not ArborBank.", "My provider isn't ArborBank."):
            with self.subTest(negative=negative):
                self.assertNotIn("provider", consequential_user_scope(negative + " " + UNSCOPED, prior))

    def test_latest_country_negation_clears_stale_scope(self):
        prior = [{"role": "user", "content": USER}]
        self.assertNotIn("jurisdiction", consequential_user_scope("I am no longer in Westhaven.", prior))

    def test_conditional_scope_is_not_actual_user_scope(self):
        self.assertEqual(consequential_user_scope("If my provider is ArborBank, what would happen?"), {})

    def test_questioned_scope_is_not_actual_user_scope(self):
        for text in ("My provider is ArborBank?", "I am in Westhaven?", "My payment rail is CedarLine?"):
            with self.subTest(text=text):
                self.assertEqual(consequential_user_scope(text), {})

    def test_indirect_epistemic_scope_is_not_actual(self):
        for text in ("I don't know whether my provider is ArborBank.",
                     "I'm not sure my provider is ArborBank.", "My provider may be ArborBank."):
            with self.subTest(text=text):
                self.assertEqual(consequential_user_scope(text), {})

    def test_quoted_scope_across_multiple_sentences_is_not_authority(self):
        text = ('The sample says "My provider is ArborBank. I am in Westhaven. '
                'My payment rail is CedarLine." ' + UNSCOPED)
        self.assertEqual(consequential_user_scope(text), {})

    def test_reported_quote_without_example_marker_is_not_authority(self):
        self.assertEqual(consequential_user_scope('They said "My provider is ArborBank" yesterday.'), {})

    def test_single_and_typographic_quoted_scope_is_not_authority(self):
        for text in ("'My provider is ArborBank.'", "‘My provider is ArborBank.’"):
            with self.subTest(text=text):
                self.assertEqual(consequential_user_scope(text), {})

    def test_user_contraction_is_not_a_quote(self):
        self.assertEqual(consequential_user_scope("I'm in Westhaven."), {"jurisdiction": "westhaven"})

    def test_sender_recipient_direction_remains_rejected(self):
        self.assertTrue(find_consequential_role_violations(UNSCOPED, "Do not spend the money.", domain="financial"))

    def test_generic_sender_contact_preserves_direction(self):
        self.assertFalse(find_consequential_role_violations(UNSCOPED, GENERIC, domain="financial"))

    def test_existing_bounded_financial_fallback_stays_generic(self):
        text = build_failed_public_advice_fallback("financial", UNSCOPED)
        self.assertIn("sender", text)
        self.assertIn("official support", text)
        self.assertIn("won't guess", text)
        self.assertFalse(consequential_claim_obligations([text]))

    def test_dynamic_schema_extends_without_mutating_existing_schema(self):
        before = copy.deepcopy(PUBLIC_FACTUAL_VERIFIER_RESPONSE_SCHEMA)
        extended = consequential_assessment_schema(before)
        self.assertIn("consequential_assessments", extended["required"])
        self.assertEqual(before, PUBLIC_FACTUAL_VERIFIER_RESPONSE_SCHEMA)

    def test_obligations_share_the_existing_single_verifier_call(self):
        result, client = verify(scoped=assessments())
        self.assertFalse(result)
        self.assertEqual(len(client.calls), 1)
        self.assertIn("consequential_assessments", client.calls[0]["format"]["required"])

    def test_ordinary_public_question_does_not_enter_consequential_scope_policy(self):
        result, client = verify(DETAIL, "What does this public procedure say?", domain=None)
        self.assertFalse(result)
        self.assertNotIn("consequential_assessments", client.calls[0]["format"]["required"])

    def test_other_consequential_domain_uses_same_general_applicability_policy(self):
        text = "File Form Kestrel within 7 business days."
        result, _ = verify(text, "My identity document was stolen. What should I do?", scoped=assessments(), domain="identity_document")
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
