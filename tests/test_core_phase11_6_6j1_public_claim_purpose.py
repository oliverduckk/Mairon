"""Independent strict content witnesses for Core-requested purpose relations.

Neutral fixed packets; no model, network, routing or publication is used.
Purpose syntax never becomes evidence and never removes a content obligation.
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research.public_claim_obligations import (
    build_public_claim_obligations, public_claim_assessment_schema,
    public_claim_failures,
)
from research.public_explanation_targets import explanation_target_obligations


USER = "Why does protocol Meridian need exchange Latch?"
BODY = "Exchange Latch allows protocol Meridian to establish shared state before normal transfer."
ANSWER = "Protocol Meridian needs exchange Latch because it establishes shared state before normal transfer."
PARAPHRASE = "Exchange Latch lets protocol Meridian establish shared state before normal transfer."


def packet(body=BODY, **state):
    source = {"source_id": "S1", "title": "Setup reference",
              "url": "https://docs.vendor.example/setup", "read_success": True,
              "accepted_as_evidence": True, "relevance_status": "accepted",
              "content_excerpt": body}
    source.update(state)
    return {"sources": [source]}


def obligations(answer=ANSWER, user=USER):
    return build_public_claim_obligations((answer,), explanation_target_obligations(user))


def assessments(items, quote=BODY, **changes):
    result = [{"index": item["index"], "supported": True,
               "source_id": "S1", "source_quote": quote} for item in items]
    for item in result:
        item.update(changes)
    return result


def failures(answer=ANSWER, body=BODY, *, user=USER, source=None, raw=None):
    items = obligations(answer, user)
    return public_claim_failures(items, assessments(items, body) if raw is None else raw,
                                 source or packet(body), annotation_present=True)


class PublicPurposeClaimTests(unittest.TestCase):
    def test_because_purpose_claim_keeps_strict_content_obligation(self):
        items = obligations()
        self.assertEqual([item["kind"] for item in items], ["explanation"])
        self.assertEqual(items[0]["explanation_targets"][0]["relation_type"], "purpose_or_necessity")

    def test_because_need_answer_can_use_functional_body_witness(self):
        self.assertFalse(failures())

    def test_functional_paraphrase_without_need_has_independent_claim_obligation(self):
        self.assertEqual([item["kind"] for item in obligations(PARAPHRASE)], ["explanation"])
        self.assertFalse(failures(PARAPHRASE))

    def test_uses_to_purpose_answer_keeps_independent_claim_obligation(self):
        answer = "Protocol Meridian uses exchange Latch to establish shared state before normal transfer."
        self.assertEqual(len(obligations(answer)), 1)
        self.assertFalse(failures(answer))

    def test_required_so_that_purpose_answer_can_use_body_function(self):
        answer = "Exchange Latch is required so that protocol Meridian can establish shared state before normal transfer."
        self.assertTrue(obligations(answer))
        self.assertFalse(failures(answer))

    def test_source_ensures_function_can_support_same_purpose(self):
        body = "Exchange Latch ensures protocol Meridian establishes shared state before normal transfer."
        self.assertFalse(failures(PARAPHRASE, body))

    def test_source_exists_but_does_not_establish_purpose_fails(self):
        body = "Protocol Meridian uses exchange Latch. Exchange Latch exists."
        self.assertTrue(failures(body=body))

    def test_source_mentions_both_but_has_unrelated_cause_fails(self):
        body = "Protocol Meridian and exchange Latch are listed because the catalogue was updated."
        self.assertTrue(failures(body=body))

    def test_reversed_beneficiary_and_requirement_fails(self):
        body = "Protocol Meridian allows exchange Latch to establish shared state before normal transfer."
        self.assertTrue(failures(body=body))

    def test_different_beneficiary_fails(self):
        body = "Exchange Latch allows protocol Solace to establish shared state before normal transfer."
        self.assertTrue(failures(body=body))

    def test_different_requirement_fails(self):
        body = "Exchange Beacon allows protocol Meridian to establish shared state before normal transfer."
        self.assertTrue(failures(body=body))

    def test_different_function_fails(self):
        body = "Exchange Latch allows protocol Meridian to encrypt the payload before normal transfer."
        self.assertTrue(failures(body=body))

    def test_body_negative_purpose_cannot_support_positive(self):
        body = "Exchange Latch does not allow protocol Meridian to establish shared state before normal transfer."
        self.assertTrue(failures(body=body))

    def test_conditional_body_does_not_establish_actual_purpose(self):
        body = "If exchange Latch allows protocol Meridian to establish shared state before normal transfer, the trial may proceed."
        self.assertTrue(failures(body=body))

    def test_quoted_body_does_not_establish_actual_purpose(self):
        self.assertTrue(failures(body='"' + BODY + '"'))

    def test_question_body_is_not_purpose_authority(self):
        self.assertTrue(failures(body=BODY.rstrip('.') + '?'))

    def test_title_only_function_does_not_replace_readable_body(self):
        state = packet("Protocol Meridian and exchange Latch are named.", title=BODY)
        self.assertTrue(failures(source=state))

    def test_snippet_only_function_does_not_replace_readable_body(self):
        state = packet("Protocol Meridian and exchange Latch are named.", search_snippet=BODY)
        self.assertTrue(failures(source=state))

    def test_unreadable_source_does_not_supply_purpose_witness(self):
        self.assertTrue(failures(source=packet(read_success=False)))

    def test_rejected_source_does_not_supply_purpose_witness(self):
        self.assertTrue(failures(source=packet(accepted_as_evidence=False)))

    def test_unavailable_source_does_not_supply_purpose_witness(self):
        self.assertTrue(failures(source=packet(relevance_status="unavailable")))

    def test_model_positive_flag_cannot_remove_missing_body_witness(self):
        items = obligations()
        self.assertTrue(public_claim_failures(items, assessments(items), packet("A catalogue exists.")))

    def test_model_negative_claim_remains_negative_with_valid_purpose_body(self):
        items = obligations()
        self.assertTrue(public_claim_failures(items, assessments(items, supported=False), packet()))

    def test_present_empty_claim_assessments_fail_closed(self):
        self.assertIn("invalid_claim_assessments", failures(raw=[])[1])

    def test_present_none_claim_assessments_fail_closed(self):
        result = public_claim_failures(obligations(), None, packet(), annotation_present=True)
        self.assertIn("invalid_claim_assessments", result[1])

    def test_composed_purpose_missing_claim_protocol_cannot_use_literal_fallback(self):
        items = obligations(BODY)
        self.assertTrue(items)
        result = public_claim_failures(items, None, packet(), annotation_present=False)
        self.assertIn("missing_claim_assessments", result[1])

    def test_present_non_list_claim_assessments_fail_closed(self):
        self.assertIn("invalid_claim_assessments", failures(raw={})[1])

    def test_claim_protocol_extra_field_is_not_ignored(self):
        raw = assessments(obligations())
        raw[0]["relationship_answered"] = True
        self.assertIn("invalid_claim_assessments", failures(raw=raw)[1])

    def test_target_protocol_fields_cannot_replace_claim_protocol(self):
        raw = [{"index": 1, "outcome": "factual_explanation", "mechanism_bound": True}]
        self.assertIn("invalid_claim_assessments", failures(raw=raw)[1])

    def test_duplicate_claim_assessment_is_not_ignored(self):
        raw = assessments(obligations())
        self.assertIn("invalid_claim_assessments", failures(raw=raw + raw)[1])

    def test_boolean_claim_index_is_malformed(self):
        raw = assessments(obligations(), index=True)
        self.assertIn("invalid_claim_assessments", failures(raw=raw)[1])

    def test_integer_supported_value_is_malformed(self):
        raw = assessments(obligations(), supported=1)
        self.assertIn("invalid_claim_assessments", failures(raw=raw)[1])

    def test_missing_source_identifier_fails_closed(self):
        self.assertTrue(failures(raw=assessments(obligations(), source_id=None)))

    def test_unknown_source_identifier_fails_closed(self):
        self.assertTrue(failures(raw=assessments(obligations(), source_id="S2")))

    def test_invented_quote_fails_closed(self):
        self.assertTrue(failures(raw=assessments(obligations(), quote=BODY + " It also guarantees success.")))

    def test_partial_body_marker_does_not_supply_function(self):
        self.assertTrue(failures(raw=assessments(obligations(), quote="Exchange Latch allows protocol Meridian")))

    def test_request_targets_snapshot_does_not_share_mutable_mapping(self):
        targets = [dict(item) for item in explanation_target_obligations(USER)]
        items = build_public_claim_obligations((ANSWER,), targets)
        targets[0]["mechanism"] = "different subject"
        self.assertEqual(items[0]["explanation_targets"][0]["mechanism"], "protocol Meridian")

    def test_no_core_purpose_target_does_not_weaken_old_reason_requirement(self):
        items = build_public_claim_obligations((ANSWER,))
        result = public_claim_failures(items, assessments(items), packet())
        self.assertIn("explanation_witness_missing", result[1])

    def test_wrong_request_target_does_not_create_purpose_exception(self):
        items = obligations(user="Why does protocol Solace need exchange Beacon?")
        self.assertNotIn("explanation_targets", items[0])
        self.assertTrue(public_claim_failures(items, assessments(items), packet()))

    def test_ordinary_optional_advice_reason_keeps_old_content_checks(self):
        answer = "Try rebooting the controller because it clears temporary state."
        body = "Rebooting the controller clears temporary state."
        items = obligations(answer)
        self.assertNotIn("explanation_targets", items[0])
        self.assertTrue(public_claim_failures(items, assessments(items, body), packet(body)))

    def test_nested_purpose_does_not_supply_independent_outer_cause(self):
        answer = "The outage happened because exchange Latch allows protocol Meridian to establish shared state before normal transfer."
        items = obligations(answer)
        self.assertNotIn("explanation_targets", items[0])
        self.assertIn("explanation_witness_missing", failures(answer)[1])

    def test_due_to_outer_reason_does_not_acquire_purpose_exception(self):
        answer = "The outage happened due to the fact that exchange Latch allows protocol Meridian to establish shared state before normal transfer."
        items = obligations(answer)
        self.assertNotIn("explanation_targets", items[0])
        self.assertTrue(failures(answer))

    def test_named_outer_reason_does_not_acquire_purpose_exception(self):
        answer = "The reason for the outage is that exchange Latch allows protocol Meridian to establish shared state before normal transfer."
        items = obligations(answer)
        self.assertNotIn("explanation_targets", items[0])
        self.assertTrue(failures(answer))

    def test_outer_cause_needs_its_own_corresponding_body_relation(self):
        answer = "The outage happened because exchange Latch allows protocol Meridian to establish shared state before normal transfer."
        self.assertFalse(failures(answer, body=answer))

    def test_purpose_before_extra_reason_keeps_ordinary_reason_obligation(self):
        answer = "Exchange Latch allows protocol Meridian to establish shared state before normal transfer because the outage was permanent."
        items = obligations(answer)
        self.assertNotIn("explanation_targets", items[0])
        self.assertTrue(failures(answer))

    def test_multiple_reason_clauses_cannot_share_one_purpose_witness(self):
        answer = "Protocol Meridian needs exchange Latch because it establishes shared state before normal transfer because the outage was permanent."
        items = obligations(answer)
        self.assertNotIn("explanation_targets", items[0])
        self.assertTrue(failures(answer))

    def test_direct_uses_because_still_expresses_requested_purpose(self):
        answer = "Protocol Meridian uses exchange Latch because it establishes shared state before normal transfer."
        items = obligations(answer)
        self.assertIn("explanation_targets", items[0])
        self.assertFalse(failures(answer))

    def test_direct_need_because_preserves_determiners_and_modal(self):
        answer = "The protocol Meridian may need the exchange Latch because it establishes shared state before normal transfer."
        items = obligations(answer)
        self.assertIn("explanation_targets", items[0])
        self.assertFalse(failures(answer))

    def test_ordinary_matching_reason_remains_valid(self):
        answer = "People discussed Aster because the archive opened."
        items = build_public_claim_obligations((answer,))
        self.assertFalse(public_claim_failures(items, assessments(items, answer), packet(answer)))

    def test_reception_obligation_is_not_deleted_by_purpose_transport(self):
        answer = "People love exchange Latch because it lets protocol Meridian establish shared state before normal transfer."
        items = obligations(answer)
        self.assertIn("reception", [item["kind"] for item in items])
        self.assertTrue(public_claim_failures(items, assessments(items), packet()))

    def test_conditional_candidate_does_not_convert_hypothesis_into_fact(self):
        answer = "If protocol Meridian needs exchange Latch because it establishes shared state, a trial could proceed."
        self.assertTrue(failures(answer))

    def test_purpose_source_must_be_selected_by_unambiguous_identifier(self):
        state = packet()
        state["sources"].append(dict(state["sources"][0]))
        self.assertTrue(failures(source=state))

    def test_missing_one_of_two_claim_assessments_fails_closed(self):
        answers = (ANSWER, "People loved the preview because the archive opened.")
        items = build_public_claim_obligations(answers, explanation_target_obligations(USER))
        self.assertGreater(len(items), 1)
        raw = assessments(items[:1])
        result = public_claim_failures(items, raw, packet(), annotation_present=True)
        self.assertEqual(set(result), {1, 2})

    def test_claim_schema_remains_exact_and_independently_required(self):
        base = {"type": "object", "properties": {"supported": {"type": "boolean"}}, "required": ["supported"]}
        original = copy.deepcopy(base)
        schema = public_claim_assessment_schema(base)
        self.assertEqual(base, original)
        self.assertIn("claim_assessments", schema["required"])
        item = schema["properties"]["claim_assessments"]["items"]
        self.assertEqual(set(item["required"]), {"index", "supported", "source_id", "source_quote"})
        self.assertFalse(item["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
