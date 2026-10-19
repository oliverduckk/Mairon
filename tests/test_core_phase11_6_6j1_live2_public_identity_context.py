"""Same-source nominal identity and surviving purpose context stay bounded.

These fixed neutral packets exercise the existing typed aggregators directly.
Neither aliases nor surviving candidate context supply semantic evidence.
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research.public_claim_obligations import (
    build_public_claim_obligations, public_claim_failures,
    public_identity_date_failures, public_identity_date_obligations,
)
from research.public_explanation_targets import (
    explanation_target_failures, explanation_target_obligations,
)

USER = "Why does OTP need exchange Myra?"
DEFINITION = "Orven Transport Protocol (OTP) is documented."
QUOTE = "Orven Transport Protocol uses exchange Myra to establish shared state before transfer."
BODY = DEFINITION + " " + QUOTE
ANSWER = "OTP uses exchange Myra to establish shared state before transfer."


def packet(body=BODY, **changes):
    source = {"source_id": "S1", "title": "Transport reference",
              "url": "https://docs.vendor.example/transport", "read_success": True,
              "accepted_as_evidence": True, "relevance_status": "accepted",
              "content_excerpt": body}
    source.update(changes)
    return {"sources": [source]}


def target_assessment(answer=ANSWER, quote=QUOTE, **changes):
    item = {"index": 1, "outcome": "factual_explanation", "mechanism_bound": True,
            "effect_bound": True, "relationship_answered": True,
            "mechanism_quote": "OTP", "effect_quote": "exchange Myra",
            "answer_quote": answer, "source_id": "S1", "source_quote": quote}
    item.update(changes)
    return [item]


def target_result(answer=ANSWER, quote=QUOTE, *, body=BODY, user=USER, evidence=None,
                  sentences=None, changes=None, raw=None):
    return explanation_target_failures(
        explanation_target_obligations(user),
        target_assessment(answer, quote, **(changes or {})) if raw is None else raw,
        list(sentences) if sentences is not None else [answer], evidence or packet(body),
    )


def claim_result(answer=ANSWER, quote=QUOTE, *, body=BODY, user=USER, evidence=None,
                 sentences=None, changes=None, raw=None, return_items=False):
    evidence = evidence or packet(body)
    units = list(sentences) if sentences is not None else [answer]
    targets = explanation_target_obligations(user) if user else ()
    items = build_public_claim_obligations(units, targets, evidence)
    assessments = [{"index": item["index"], "supported": True,
                    "source_id": "S1", "source_quote": quote} for item in items]
    for item in assessments:
        item.update(changes or {})
    result = public_claim_failures(items, assessments if raw is None else raw,
                                   evidence, annotation_present=True)
    return (items, result) if return_items else result


class SourceLocalIdentityTests(unittest.TestCase):
    def test_literal_name_is_not_lost_when_larger_alias_is_normalized(self):
        answer = "Stepped input produces acoustic motion because the contact briefly opens."
        body = "The supply change is also called stepped input. " + answer
        items, result = claim_result(answer, answer, body=body, user=None, return_items=True)
        self.assertTrue(items)
        self.assertFalse(result)

    def test_acronym_definition_outside_literal_relationship_quote_binds_target(self):
        self.assertEqual(target_result(), [])

    def test_acronym_definition_outside_literal_relationship_quote_binds_claim(self):
        items, result = claim_result(return_items=True)
        self.assertTrue(items)
        self.assertTrue(items[0].get("explanation_targets"))
        self.assertFalse(result)

    def test_full_name_candidate_can_use_acronym_body_with_local_definition(self):
        quote = "OTP uses exchange Myra to establish shared state before transfer."
        answer = "Orven Transport Protocol uses exchange Myra to establish shared state before transfer."
        kwargs = {"body": DEFINITION + " " + quote,
                  "changes": {"mechanism_quote": "Orven Transport Protocol"}}
        self.assertEqual(target_result(answer, quote, **kwargs), [])
        self.assertFalse(claim_result(answer, quote, body=kwargs["body"]))

    def test_reverse_parenthetical_body_definition_binds_same_source(self):
        body = "OTP (Orven Transport Protocol) is documented. " + QUOTE
        self.assertEqual(target_result(body=body), [])
        self.assertFalse(claim_result(body=body))

    def test_explicit_called_alias_stays_source_local(self):
        body = "Orven Transport Protocol is also called OTP. " + QUOTE
        self.assertEqual(target_result(body=body), [])
        self.assertFalse(claim_result(body=body))

    def test_unestablished_acronym_cannot_expand_from_initials_alone(self):
        self.assertTrue(target_result(body=QUOTE))
        self.assertTrue(claim_result(body=QUOTE))

    def test_candidate_definition_does_not_supply_body_alias(self):
        answer = "OTP (Orven Transport Protocol) needs exchange Myra because it establishes shared state before transfer."
        self.assertTrue(target_result(answer, body=QUOTE))
        self.assertTrue(claim_result(answer, body=QUOTE))

    def test_title_definition_does_not_supply_body_alias(self):
        evidence = packet(QUOTE, title=DEFINITION)
        self.assertTrue(target_result(evidence=evidence))
        self.assertTrue(claim_result(evidence=evidence))

    def test_other_source_alias_cannot_bind_selected_source(self):
        evidence = packet(QUOTE)
        other = packet(DEFINITION)["sources"][0]
        other["source_id"] = "S2"
        evidence["sources"].append(other)
        self.assertTrue(target_result(evidence=evidence))
        self.assertTrue(claim_result(evidence=evidence))

    def test_conflicting_same_source_expansions_cannot_identify_acronym_role(self):
        user = "Why does Orven Transport Protocol need exchange Myra?"
        answer = "Orven Transport Protocol uses exchange Myra to establish shared state before transfer."
        quote = "OTP uses exchange Myra to establish shared state before transfer."
        body = DEFINITION + " Ordal Timing Protocol (OTP) is also documented. " + quote
        self.assertTrue(target_result(answer, quote, body=body, user=user,
                                      changes={"mechanism_quote": "Orven Transport Protocol"}))
        self.assertTrue(claim_result(answer, quote, body=body, user=user))

    def test_ambiguous_abbreviation_does_not_erase_direct_literal_identity(self):
        user = "Why does Orven Transport Protocol need exchange Myra?"
        body = DEFINITION + " Ordal Timing Protocol (OTP) is also documented. " + QUOTE
        self.assertEqual(target_result(QUOTE, QUOTE, body=body, user=user,
                                       changes={"mechanism_quote": "Orven Transport Protocol"}), [])
        self.assertFalse(claim_result(QUOTE, QUOTE, body=body, user=user))

    def test_rejected_source_alias_cannot_bind_selected_source(self):
        evidence = packet(QUOTE)
        other = packet(DEFINITION, accepted_as_evidence=False)["sources"][0]
        other["source_id"] = "S2"
        evidence["sources"].append(other)
        self.assertTrue(target_result(evidence=evidence))
        self.assertTrue(claim_result(evidence=evidence))

    def test_unreadable_source_with_definition_cannot_supply_relationship(self):
        evidence = packet(read_success=False)
        self.assertTrue(target_result(evidence=evidence))
        self.assertTrue(claim_result(evidence=evidence))

    def test_paraphrased_nonliteral_source_quote_is_not_reconstructed(self):
        quote = "The Orven protocol establishes state through the exchange."
        self.assertTrue(target_result(quote=quote))
        self.assertTrue(claim_result(quote=quote))

    def test_alias_body_without_explanatory_relationship_remains_insufficient(self):
        quote = "Orven Transport Protocol and exchange Myra are listed in the catalogue."
        body = DEFINITION + " " + quote
        self.assertTrue(target_result(quote=quote, body=body))
        self.assertTrue(claim_result(quote=quote, body=body))

    def test_selected_source_role_direction_cannot_be_reversed(self):
        quote = "Orven Transport Protocol allows exchange Myra to establish shared state before transfer."
        self.assertTrue(target_result(quote=quote, body=DEFINITION + " " + quote))
        self.assertTrue(claim_result(quote=quote, body=DEFINITION + " " + quote))

    def test_positive_function_cannot_borrow_negative_body_function(self):
        quote = "Orven Transport Protocol does not use exchange Myra to establish shared state before transfer."
        self.assertTrue(target_result(quote=quote, body=DEFINITION + " " + quote))
        self.assertTrue(claim_result(quote=quote, body=DEFINITION + " " + quote))

    def test_explicit_standalone_abbreviation_binds_independent_content_claim(self):
        answer = "The REG packet confirms the shared state because both endpoints acknowledge it."
        quote = "The registration packet confirms the shared state because both endpoints acknowledge it."
        body = "registration (REG) is the setup signal. " + quote
        items, result = claim_result(answer, quote, body=body, user=None, return_items=True)
        self.assertEqual(len(items), 1)
        self.assertFalse(result)

    def test_standalone_abbreviation_without_definition_is_not_guessed(self):
        answer = "The REG packet confirms the shared state because both endpoints acknowledge it."
        quote = "The registration packet confirms the shared state because both endpoints acknowledge it."
        self.assertTrue(claim_result(answer, quote, body=quote, user=None))

    def test_standalone_abbreviation_cannot_bridge_a_different_fact(self):
        answer = "The REG packet confirms the shared state because both endpoints acknowledge it."
        quote = "The registration packet encrypts the payload because a key is required."
        body = "registration (REG) is the setup signal. " + quote
        self.assertTrue(claim_result(answer, quote, body=body, user=None))

    def test_full_named_identity_does_not_authorize_two_title_participants(self):
        sentence = 'The item is titled "Avery and Morgan".'
        evidence = packet("The item is titled \"Avery Morgan\".", title="Avery Morgan")
        items = public_identity_date_obligations([sentence])
        self.assertTrue(items)
        self.assertTrue(public_identity_date_failures(items, evidence))

    def test_full_named_identity_does_not_authorize_invented_entity_relation(self):
        answer = "Avery and Morgan disagreed because the schedule changed."
        quote = "Avery Morgan appeared because the schedule changed."
        items = build_public_claim_obligations([answer])
        raw = [{"index": item["index"], "supported": True,
                "source_id": "S1", "source_quote": quote} for item in items]
        self.assertTrue(items)
        self.assertTrue(public_claim_failures(items, raw, packet(quote)))


class TechnicalNominalContextTests(unittest.TestCase):
    def test_technical_nominal_head_order_keeps_subject_requirement_direction(self):
        user = "Why does Orven protocol need the Myra exchange?"
        answer = "Protocol Orven uses exchange Myra to establish shared state before transfer."
        quote = "Exchange Myra allows protocol Orven to establish shared state before transfer."
        self.assertEqual(target_result(answer, quote, body=quote, user=user,
                                       changes={"mechanism_quote": "Protocol Orven"}), [])
        self.assertFalse(claim_result(answer, quote, body=quote, user=user))

    def test_article_and_discourse_prefix_are_not_extra_named_subjects(self):
        answer = "First, the OTP uses exchange Myra to establish shared state before transfer."
        self.assertEqual(target_result(answer), [])
        self.assertFalse(claim_result(answer))

    def test_faithful_technical_refinement_is_grounded_in_same_body(self):
        quote = "OTP uses a three-step exchange Myra to establish shared state before transfer."
        answer = "Orven Transport Protocol needs a three-step exchange Myra because it establishes shared state before transfer."
        body = DEFINITION + " " + quote
        self.assertEqual(target_result(answer, quote, body=body,
                                       changes={"mechanism_quote": "Orven Transport Protocol"}), [])
        self.assertFalse(claim_result(answer, quote, body=body))

    def test_unestablished_technical_refinement_cannot_be_invented(self):
        answer = "OTP needs a secure exchange Myra because it establishes shared state before transfer."
        self.assertTrue(target_result(answer))
        self.assertTrue(claim_result(answer))

    def test_unrelated_named_subject_remains_a_content_mismatch(self):
        answer = "OTP uses exchange Myra because Ruvan establishes shared state before transfer."
        self.assertTrue(claim_result(answer))

    def test_different_required_exchange_cannot_borrow_same_protocol_alias(self):
        answer = "OTP uses exchange Velin to establish shared state before transfer."
        self.assertTrue(target_result(answer, changes={"effect_quote": "exchange Velin"}))


class AdjacentPurposeContextTests(unittest.TestCase):
    user = "Why does protocol Orven need exchange Myra?"
    usage = "Protocol Orven uses exchange Myra."
    function = "Exchange Myra establishes shared state before transfer."

    def run_target(self, units, *, body=None, quote=None, raw=None, **changes):
        answer = " ".join(units)
        quote = quote or self.usage + " " + self.function
        return target_result(answer, quote, body=body or quote, user=self.user,
                             sentences=units, raw=raw,
                             changes={"mechanism_quote": "Protocol Orven",
                                      "effect_quote": "exchange Myra", **changes})

    def test_adjacent_usage_and_function_are_one_surviving_purpose_answer(self):
        self.assertEqual(self.run_target([self.usage, self.function]), [])

    def test_second_sentence_keeps_independent_content_assessment(self):
        quote = self.usage + " " + self.function
        items, result = claim_result(quote, quote, body=quote, user=self.user,
                                    sentences=[self.usage, self.function], return_items=True)
        self.assertTrue(items)
        self.assertIn(2, {item["sentence_index"] for item in items})
        self.assertFalse(result)

    def test_removed_usage_antecedent_cannot_complete_salvage(self):
        self.assertTrue(self.run_target([self.function], mechanism_quote="exchange Myra"))

    def test_advice_only_subset_cannot_complete_purpose(self):
        advice = "Try selecting a different option."
        self.assertTrue(self.run_target([advice], mechanism_quote="option", effect_quote="different"))

    def test_unrelated_intervening_sentence_cannot_supply_immediate_context(self):
        answer = [self.usage, "The catalogue was revised.", self.function]
        # Select only the function as the claimed answer to prove that a
        # deleted/distant usage sentence does not silently supply its actor.
        self.assertTrue(self.run_target(answer, answer_quote=self.function))

    def test_full_three_sentence_quote_does_not_erase_adjacency_requirement(self):
        answer = [self.usage, "The catalogue was revised.", self.function]
        self.assertTrue(self.run_target(answer))

    def test_negative_usage_cannot_supply_positive_beneficiary_context(self):
        usage = "Protocol Orven does not use exchange Myra."
        self.assertTrue(self.run_target([usage, self.function], body=usage + " " + self.function,
                                        quote=usage + " " + self.function))

    def test_swapped_usage_roles_cannot_supply_same_purpose(self):
        usage = "Exchange Myra uses protocol Orven."
        self.assertTrue(self.run_target([usage, self.function], body=usage + " " + self.function,
                                        quote=usage + " " + self.function))

    def test_missing_source_usage_context_remains_incomplete(self):
        self.assertTrue(self.run_target([self.usage, self.function], body=self.function,
                                        quote=self.function))

    def test_reversed_source_usage_cannot_borrow_candidate_antecedent(self):
        quote = "Exchange Myra uses protocol Orven. " + self.function
        self.assertTrue(self.run_target([self.usage, self.function], body=quote, quote=quote))

    def test_adjacent_british_synchronisation_function_binds_to_usage(self):
        units = ["OTP uses exchange Myra.", "Exchange Myra synchronises shared state before transfer."]
        quote = " ".join(units)
        body = DEFINITION + " " + quote
        self.assertEqual(target_result(quote, quote, body=body, sentences=units), [])
        items, result = claim_result(quote, quote, body=body, sentences=units, return_items=True)
        self.assertTrue(items)
        self.assertIn(2, {item["sentence_index"] for item in items})
        self.assertFalse(result)

    def test_adjacent_american_synchronization_function_binds_to_usage(self):
        units = ["OTP uses exchange Myra.", "Exchange Myra synchronizes shared state before transfer."]
        quote = " ".join(units)
        body = DEFINITION + " " + quote
        self.assertEqual(target_result(quote, quote, body=body, sentences=units), [])
        items, result = claim_result(quote, quote, body=body, sentences=units, return_items=True)
        self.assertTrue(items)
        self.assertIn(2, {item["sentence_index"] for item in items})
        self.assertFalse(result)

    def test_synchronisation_function_without_source_usage_context_is_not_enough(self):
        units = ["OTP uses exchange Myra.", "Exchange Myra synchronises shared state before transfer."]
        quote = units[1]
        self.assertTrue(target_result(" ".join(units), quote, body=DEFINITION + " " + quote,
                                      sentences=units))

    def test_synchronisation_pair_cannot_borrow_an_unrelated_source_alias(self):
        units = ["OTP uses exchange Myra.", "Exchange Myra synchronises shared state before transfer."]
        quote = " ".join(units)
        body = "Ordal Timing Protocol (OTP) is documented. " + quote
        self.assertTrue(target_result(quote, quote, body=body, sentences=units,
                                      user="Why does Orven Transport Protocol need exchange Myra?"))


class StrictAssessmentPreservationTests(unittest.TestCase):
    def test_false_relationship_assessment_remains_unfulfilled(self):
        self.assertIn("explanation_target_unfulfilled",
                      target_result(changes={"relationship_answered": False}))

    def test_false_role_binding_cannot_be_overridden_by_literal_body(self):
        self.assertIn("explanation_target_unfulfilled",
                      target_result(changes={"mechanism_bound": False}))

    def test_missing_target_assessment_fails_closed(self):
        self.assertTrue(target_result(raw=[]))

    def test_malformed_target_assessment_fails_closed(self):
        raw = target_assessment()
        del raw[0]["effect_bound"]
        self.assertIn("invalid_explanation_target_assessments", target_result(raw=raw))

    def test_false_claim_support_remains_rejected(self):
        self.assertTrue(claim_result(changes={"supported": False}))

    def test_missing_claim_assessment_fails_closed(self):
        self.assertTrue(claim_result(raw=[]))

    def test_malformed_claim_assessment_fails_closed(self):
        items = build_public_claim_obligations([ANSWER], explanation_target_obligations(USER), packet())
        raw = [{"index": item["index"], "supported": True, "source_id": "S1"} for item in items]
        self.assertTrue(public_claim_failures(items, raw, packet()))

    def test_positive_flag_cannot_override_missing_literal_source(self):
        missing = "Orven Transport Protocol uses exchange Myra to encrypt payloads."
        self.assertTrue(target_result(quote=missing))
        self.assertTrue(claim_result(quote=missing))

    def test_identity_transport_does_not_mutate_evidence_or_assessments(self):
        evidence = packet()
        raw = target_assessment()
        snapshot = copy.deepcopy((evidence, raw))
        self.assertEqual(target_result(evidence=evidence, raw=raw), [])
        self.assertEqual((evidence, raw), snapshot)


if __name__ == "__main__":
    unittest.main(verbosity=2)
