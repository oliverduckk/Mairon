"""Core literal catalogs remove transcription work without granting authority."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from research.public_explanation_targets import (
    explanation_target_obligations, explanation_target_failures, explanation_target_schema,
    public_role_bridge, purpose_candidate_bound, purpose_claim_witness_issue,
    public_witness_catalog, public_witness_schema, public_witness_instruction,
    resolve_public_witness_refs,
)


USER = "Why does protocol Orion need exchange Relay?"
BODY = "Exchange Relay allows protocol Orion to establish shared state before normal transfer."
GOOD = "Exchange Relay lets protocol Orion establish shared state before normal transfer."


def packet(body=BODY, **changes):
    source = {"source_id": "S1", "title": "Operation overview",
              "read_success": True, "accepted_as_evidence": True,
              "content_excerpt": body}
    source.update(changes)
    return {"sources": [source]}


def assessment(text=GOOD, body=BODY, **changes):
    item = {"index": 1, "outcome": "factual_explanation", "mechanism_bound": True,
            "effect_bound": True, "relationship_answered": True,
            "mechanism_quote": "protocol Orion", "effect_quote": "Exchange Relay",
            "answer_quote": text, "source_id": "S1", "source_quote": body}
    item.update(changes)
    return item


def chosen(catalog, field, literal=None, index=1):
    choices = catalog["targets"][index][field]
    return next(key for key, text in choices.items() if literal is None or literal == text)


def body_ref(catalog, literal=BODY, source_id="S1"):
    return next(key for key, item in catalog["body"].items()
                if item["source_id"] == source_id and item["literal"] == literal)


def referenced(catalog, **changes):
    item = assessment(
        mechanism_quote=chosen(catalog, "mechanism_quote", "protocol Orion"),
        effect_quote=chosen(catalog, "effect_quote", "Exchange Relay"),
        answer_quote=chosen(catalog, "answer_quote", GOOD),
        source_quote=body_ref(catalog),
    )
    item.update(changes)
    return {"explanation_target_assessments": [item], "supported": True}


class LiteralWitnessTransportTests(unittest.TestCase):
    def setUp(self):
        self.targets = explanation_target_obligations(USER)
        self.evidence = packet()
        self.catalog = public_witness_catalog(self.targets, [GOOD], self.evidence)

    def failures(self, payload):
        resolved = resolve_public_witness_refs(payload, self.catalog)
        return explanation_target_failures(self.targets, resolved["explanation_target_assessments"],
                                           [GOOD], self.evidence)

    def test_valid_catalog_refs_materialize_literal_witnesses(self):
        resolved = resolve_public_witness_refs(referenced(self.catalog), self.catalog)
        self.assertEqual(resolved["explanation_target_assessments"][0], assessment())
        self.assertEqual(self.failures(referenced(self.catalog)), [])

    def test_candidate_catalog_is_not_source_evidence(self):
        other = public_witness_catalog(self.targets, [GOOD], packet("The archive contains a schedule."))
        payload = referenced(self.catalog)
        payload["explanation_target_assessments"][0]["source_quote"] = body_ref(other, "The archive contains a schedule.")
        resolved = resolve_public_witness_refs(payload, other)
        self.assertTrue(explanation_target_failures(self.targets, resolved["explanation_target_assessments"],
                                                   [GOOD], packet("The archive contains a schedule.")))

    def test_only_admitted_readable_bodies_enter_catalog(self):
        for changes in ({"read_success": False}, {"accepted_as_evidence": False},
                        {"relevance_status": "rejected"}, {"relevance_status": "unreadable"}):
            with self.subTest(changes=changes):
                self.assertEqual(public_witness_catalog(self.targets, [GOOD], packet(**changes))["body"], {})

    def test_source_title_does_not_enter_body_catalog(self):
        catalog = public_witness_catalog(self.targets, [GOOD], packet("A short note.", title=BODY))
        self.assertNotIn(BODY, [item["literal"] for item in catalog["body"].values()])

    def test_source_snippet_does_not_enter_body_catalog(self):
        catalog = public_witness_catalog(self.targets, [GOOD], packet("A short note.", search_snippet=BODY))
        self.assertNotIn(BODY, [item["literal"] for item in catalog["body"].values()])

    def test_duplicate_source_ids_are_not_resolvable(self):
        evidence = {"sources": [packet()["sources"][0], packet()["sources"][0]]}
        self.assertEqual(public_witness_catalog(self.targets, [GOOD], evidence)["body"], {})

    def test_catalog_snapshots_source_and_candidate_text(self):
        original = copy.deepcopy(self.catalog)
        self.evidence["sources"][0]["content_excerpt"] = "Changed later."
        self.assertEqual(self.catalog, original)

    def test_resolver_does_not_mutate_model_payload(self):
        payload = referenced(self.catalog)
        original = copy.deepcopy(payload)
        resolve_public_witness_refs(payload, self.catalog)
        self.assertEqual(payload, original)

    def test_unknown_candidate_reference_fails_closed(self):
        self.assertTrue(self.failures(referenced(self.catalog, mechanism_quote="@core-witness:unknown")))

    def test_wrong_target_reference_fails_closed(self):
        self.assertTrue(self.failures(referenced(self.catalog, mechanism_quote="@core-witness:t2:mechanism_quote:1")))

    def test_wrong_field_reference_fails_closed(self):
        ref = chosen(self.catalog, "effect_quote")
        self.assertTrue(self.failures(referenced(self.catalog, mechanism_quote=ref)))

    def test_wrong_source_reference_fails_closed(self):
        self.assertTrue(self.failures(referenced(self.catalog, source_id="S2")))

    def test_unknown_body_reference_fails_closed(self):
        self.assertTrue(self.failures(referenced(self.catalog, source_quote="@core-witness:b7:8")))

    def test_reference_in_hostile_candidate_cannot_be_literal_fallback(self):
        text = "@core-witness:unknown"
        catalog = public_witness_catalog(self.targets, [text], packet())
        resolved = resolve_public_witness_refs({"explanation_target_assessments": [assessment(
            text, mechanism_quote=text)]}, catalog)
        self.assertIsInstance(resolved["explanation_target_assessments"][0]["mechanism_quote"], dict)

    def test_raw_literal_legacy_positive_remains_valid(self):
        self.assertEqual(self.failures({"explanation_target_assessments": [assessment()]}), [])

    def test_raw_paraphrased_candidate_quote_is_not_repaired(self):
        payload = {"explanation_target_assessments": [assessment(mechanism_quote="the Orion protocol")]}
        self.assertIn("invalid_explanation_candidate_witness", self.failures(payload))

    def test_raw_invented_source_quote_is_not_repaired(self):
        payload = {"explanation_target_assessments": [assessment(source_quote="Absent evidence")]}
        self.assertIn("missing_explanation_body_witness", self.failures(payload))

    def test_raw_faithful_source_paraphrase_is_not_repaired(self):
        payload = {"explanation_target_assessments": [assessment(source_quote=GOOD)]}
        self.assertIn("missing_explanation_body_witness", self.failures(payload))

    def test_missing_fields_are_not_filled(self):
        payload = referenced(self.catalog)
        del payload["explanation_target_assessments"][0]["effect_quote"]
        self.assertIn("invalid_explanation_target_assessments", self.failures(payload))

    def test_negative_scoped_verdict_is_not_upgraded(self):
        payload = referenced(self.catalog, relationship_answered=False)
        self.assertIn("explanation_target_unfulfilled", self.failures(payload))

    def test_incomplete_outcome_is_not_upgraded(self):
        self.assertIn("explanation_target_unfulfilled", self.failures(referenced(self.catalog, outcome="incomplete")))

    def test_missing_array_stays_missing(self):
        self.assertEqual(resolve_public_witness_refs({"supported": True}, self.catalog), {"supported": True})

    def test_malformed_array_stays_malformed(self):
        payload = {"explanation_target_assessments": {"index": 1}}
        self.assertEqual(resolve_public_witness_refs(payload, self.catalog), payload)

    def test_schema_constrains_only_quote_transport_fields(self):
        base = explanation_target_schema({"properties": {}, "required": []})
        original = copy.deepcopy(base)
        schema = public_witness_schema(base, self.catalog)
        fields = schema["properties"]["explanation_target_assessments"]["items"]["properties"]
        self.assertEqual(base, original)
        self.assertEqual(fields["relationship_answered"], {"type": "boolean"})
        self.assertIn(chosen(self.catalog, "mechanism_quote"), fields["mechanism_quote"]["enum"])
        self.assertNotIn("protocol Orion", fields["mechanism_quote"]["enum"])

    def test_schema_preserves_strict_assessment_field_set(self):
        base = explanation_target_schema({"properties": {}, "required": []})
        schema = public_witness_schema(base, self.catalog)
        item = schema["properties"]["explanation_target_assessments"]["items"]
        self.assertEqual(set(item["required"]), set(assessment()))
        self.assertFalse(item["additionalProperties"])

    def test_schema_composes_independent_claim_witness_catalog(self):
        base = explanation_target_schema({"properties": {"claim_assessments": {"items": {"properties": {
            "source_quote": {"type": ["string", "null"]}, "supported": {"type": "boolean"}}}}}, "required": []})
        schema = public_witness_schema(base, self.catalog)
        fields = schema["properties"]["claim_assessments"]["items"]["properties"]
        self.assertEqual(fields["supported"], {"type": "boolean"})
        self.assertIn(body_ref(self.catalog), fields["source_quote"]["enum"])

    def test_schema_source_identity_choices_come_from_catalog_body_only(self):
        base = explanation_target_schema({"properties": {"claim_assessments": {"items": {"properties": {
            "source_quote": {"type": ["string", "null"]}, "source_id": {"type": ["string", "null"]}}}}}, "required": []})
        schema = public_witness_schema(base, self.catalog)
        for array in ("claim_assessments", "explanation_target_assessments"):
            fields = schema["properties"][array]["items"]["properties"]
            self.assertEqual(fields["source_id"]["enum"], [None, "S1"])

    def test_claim_ref_requires_its_selected_source(self):
        payload = {"claim_assessments": [{"index": 1, "supported": True,
                                           "source_id": "S2", "source_quote": body_ref(self.catalog)}]}
        resolved = resolve_public_witness_refs(payload, self.catalog)
        self.assertIsInstance(resolved["claim_assessments"][0]["source_quote"], dict)

    def test_claim_negative_flag_and_index_are_preserved(self):
        payload = {"claim_assessments": [{"index": 4, "supported": False,
                                           "source_id": "S1", "source_quote": body_ref(self.catalog)}]}
        item = resolve_public_witness_refs(payload, self.catalog)["claim_assessments"][0]
        self.assertEqual((item["index"], item["supported"], item["source_quote"]), (4, False, BODY))

    def test_instruction_distinguishes_candidate_from_authority(self):
        text = public_witness_instruction(self.catalog)
        self.assertIn("Candidate catalog text is proposed prose, NEVER evidence", text)
        self.assertIn("changes serialization only", text)
        self.assertIn("@core-witness:", text)

    def test_oversized_body_unit_is_not_truncated_into_evidence(self):
        body = "Long " * 200 + "."
        catalog = public_witness_catalog(self.targets, [GOOD], packet(body))
        self.assertEqual(catalog["body"], {})
        self.assertTrue(catalog["truncated"])

    def test_catalog_body_count_and_character_bounds(self):
        body = " ".join(f"Record {i} contains an independent entry." for i in range(200))
        catalog = public_witness_catalog(self.targets, [GOOD], packet(body))
        self.assertLessEqual(len(catalog["body"]), 64)
        self.assertLessEqual(sum(len(item["literal"]) for item in catalog["body"].values()), 10000)
        self.assertTrue(catalog["truncated"])

    def test_many_targets_obey_aggregate_json_budget_without_cutting_units(self):
        targets = tuple(dict(self.targets[0], index=index) for index in range(1, 17))
        texts = [GOOD[:-1] + " with " + (word + " ") * 60 + "." for word in ("careful", "stable")]
        catalog = public_witness_catalog(targets, texts, self.evidence)
        self.assertLessEqual(len(json.dumps(catalog, ensure_ascii=False)), 18000)
        self.assertTrue(catalog["truncated"])
        for target in catalog["targets"].values():
            self.assertTrue(all(text in texts for text in target["answer_quote"].values()))
            self.assertTrue(all(any(text in sentence for sentence in texts)
                                for field in ("mechanism_quote", "effect_quote")
                                for text in target[field].values()))

    def test_many_body_units_obey_aggregate_budget_with_whole_literal_units(self):
        body_units = [f"Record {index} contains " + "bounded " * 18 + "evidence." for index in range(80)]
        evidence = packet(" ".join(body_units))
        targets = tuple(dict(self.targets[0], index=index) for index in range(1, 5))
        texts = [GOOD[:-1] + " with " + (f"state{index} ") * 28 + "." for index in range(12)]
        catalog = public_witness_catalog(targets, texts, evidence)
        self.assertLessEqual(len(json.dumps(catalog, ensure_ascii=False)), 18000)
        self.assertTrue(catalog["truncated"])
        self.assertTrue(all(item["literal"] in body_units for item in catalog["body"].values()))
        self.assertTrue(all(text in texts for target in catalog["targets"].values()
                            for text in target["answer_quote"].values()))

    def test_empty_or_untyped_candidate_units_produce_no_catalog_authority(self):
        self.assertEqual(public_witness_catalog(self.targets, None, self.evidence)["body"], {})
        self.assertEqual(public_witness_catalog(self.targets, [None], self.evidence)["targets"], {})


class LiteralAliasAndPurposeTests(unittest.TestCase):
    def issues(self, user, text, body, mechanism, effect="exchange Relay"):
        targets = explanation_target_obligations(user)
        item = assessment(text, body, mechanism_quote=mechanism, effect_quote=effect)
        return explanation_target_failures(targets, [item], [text], packet(body))

    def test_parenthetic_full_name_can_answer_acronym_request(self):
        body = "Orion Transmission Protocol (OTP) uses exchange Relay to establish shared state before transfer."
        text = "Orion Transmission Protocol uses exchange Relay to establish shared state before transfer."
        self.assertEqual(self.issues("Why does OTP need exchange Relay?", text, body, "Orion Transmission Protocol"), [])

    def test_parenthetic_acronym_can_answer_full_name_request(self):
        body = "Orion Transmission Protocol (OTP) uses exchange Relay to establish shared state before transfer."
        text = "OTP uses exchange Relay to establish shared state before transfer."
        self.assertEqual(self.issues("Why does Orion Transmission Protocol need exchange Relay?", text, body, "OTP"), [])

    def test_reverse_parenthetic_alias_is_explicit_body_authority(self):
        body = "OTP (Orion Transmission Protocol) uses exchange Relay to establish shared state before transfer."
        text = "OTP uses exchange Relay to establish shared state before transfer."
        self.assertEqual(self.issues("Why does Orion Transmission Protocol need exchange Relay?", text, body, "OTP"), [])

    def test_lowercase_written_full_name_can_bind_explicit_acronym(self):
        body = "orion transmission protocol (OTP) uses exchange Relay to establish shared state before transfer."
        text = "orion transmission protocol uses exchange Relay to establish shared state before transfer."
        self.assertEqual(self.issues("Why does OTP need exchange Relay?", text, body, "orion transmission protocol"), [])

    def test_lowercase_written_full_name_can_bind_reverse_acronym(self):
        body = "OTP (orion transmission protocol) uses exchange Relay to establish shared state before transfer."
        text = "OTP uses exchange Relay to establish shared state before transfer."
        self.assertEqual(self.issues("Why does orion transmission protocol need exchange Relay?", text, body, "OTP"), [])

    def test_parenthetic_initials_are_not_guessed_without_explicit_body_pair(self):
        self.assertFalse(public_role_bridge("OTP", "Orion Transmission Protocol", "Orion Transmission Protocol uses a stage."))

    def test_unrelated_parenthetical_label_does_not_create_alias(self):
        self.assertFalse(public_role_bridge("ABC", "Orion Transmission Protocol", "Orion Transmission Protocol (ABC) operates."))

    def test_candidate_parenthetic_alias_cannot_create_authority(self):
        text = "Orion Transmission Protocol (OTP) uses exchange Relay to establish shared state before transfer."
        body = "Orion Transmission Protocol uses exchange Relay to establish shared state before transfer."
        self.assertTrue(self.issues("Why does OTP need exchange Relay?", text, body, "OTP"))

    def test_alias_in_title_alone_is_not_body_authority(self):
        body = "Exchange Relay allows OTP to establish shared state before transfer."
        text = "Orion Transmission Protocol uses exchange Relay to establish shared state before transfer."
        targets = explanation_target_obligations("Why does OTP need exchange Relay?")
        evidence = packet(body, title="Orion Transmission Protocol (OTP)")
        item = assessment(text, body, mechanism_quote="Orion Transmission Protocol", effect_quote="exchange Relay")
        self.assertTrue(explanation_target_failures(targets, [item], [text], evidence))

    def test_local_alias_and_function_units_can_be_selected_together(self):
        body = "Orion Transmission Protocol (OTP) is the protocol name. Exchange Relay allows OTP to establish shared state before transfer."
        text = "Orion Transmission Protocol uses exchange Relay to establish shared state before transfer."
        targets = explanation_target_obligations("Why does OTP need exchange Relay?")
        catalog = public_witness_catalog(targets, [text], packet(body))
        ref = body_ref(catalog, body)
        item = assessment(text, body, mechanism_quote=chosen(catalog, "mechanism_quote", "Orion Transmission Protocol"),
                          effect_quote=chosen(catalog, "effect_quote", "exchange Relay"),
                          answer_quote=chosen(catalog, "answer_quote", text), source_quote=ref)
        resolved = resolve_public_witness_refs({"explanation_target_assessments": [item]}, catalog)
        self.assertEqual(explanation_target_failures(targets, resolved["explanation_target_assessments"], [text], packet(body)), [])

    def test_body_determiners_do_not_change_core_role_identity(self):
        self.assertTrue(public_role_bridge("the Orion protocol", "Orion protocol", ""))

    def test_different_named_subject_remains_unbound(self):
        self.assertFalse(public_role_bridge("protocol Orion", "protocol Cedar", BODY))

    def test_helps_with_explicit_function_is_supported_purpose(self):
        text = "Exchange Relay helps protocol Orion establish shared state before normal transfer."
        self.assertEqual(self.issues(USER, text, text, "protocol Orion", "Exchange Relay"), [])

    def test_helps_to_with_explicit_function_is_supported_purpose(self):
        text = "Exchange Relay helps protocol Orion to establish shared state before normal transfer."
        self.assertEqual(self.issues(USER, text, text, "protocol Orion", "Exchange Relay"), [])

    def test_depends_on_to_retains_subject_requirement_and_function(self):
        text = "Protocol Orion depends on exchange Relay to establish shared state before normal transfer."
        self.assertEqual(self.issues(USER, text, text, "Protocol Orion"), [])

    def test_depends_on_without_function_is_incomplete(self):
        text = "Protocol Orion depends on exchange Relay."
        self.assertTrue(self.issues(USER, text, text, "Protocol Orion"))

    def test_helps_reversed_beneficiary_does_not_answer_request(self):
        text = "Protocol Orion helps exchange Relay establish shared state before normal transfer."
        self.assertTrue(self.issues(USER, text, text, "Protocol Orion", "exchange Relay"))

    def test_help_body_cannot_support_different_function(self):
        body = "Exchange Relay helps protocol Orion erase old state before normal transfer."
        text = "Exchange Relay helps protocol Orion establish shared state before normal transfer."
        self.assertTrue(self.issues(USER, text, body, "protocol Orion", "Exchange Relay"))

    def test_help_relation_negation_cannot_be_erased(self):
        body = "Exchange Relay does not help protocol Orion establish shared state before normal transfer."
        text = "Exchange Relay helps protocol Orion establish shared state before normal transfer."
        self.assertTrue(self.issues(USER, text, body, "protocol Orion", "Exchange Relay"))

    def test_help_function_negation_cannot_be_erased(self):
        body = "Exchange Relay helps protocol Orion not establish shared state before normal transfer."
        text = "Exchange Relay helps protocol Orion establish shared state before normal transfer."
        self.assertTrue(self.issues(USER, text, body, "protocol Orion", "Exchange Relay"))

    def test_source_mentioning_both_roles_does_not_establish_purpose(self):
        text = "Exchange Relay helps protocol Orion establish shared state before normal transfer."
        self.assertTrue(self.issues(USER, text, "Exchange Relay and protocol Orion are documented.", "protocol Orion", "Exchange Relay"))

    def test_optional_body_alias_shape_projection_grants_no_truth(self):
        target = explanation_target_obligations("Why does OTP need exchange Relay?")[0]
        text = "Orion Transmission Protocol uses exchange Relay to establish shared state before transfer."
        body = "Orion Transmission Protocol (OTP) is documented."
        self.assertFalse(purpose_candidate_bound(target, text))
        self.assertTrue(purpose_candidate_bound(target, text, body))
        self.assertIsNotNone(purpose_claim_witness_issue(target, text, body))


if __name__ == "__main__":
    unittest.main()
