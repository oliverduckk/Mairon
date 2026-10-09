"""Bounded citation and self-knowledge calibration uses neutral source state.

The existing public sentence/global verifier remains an independent input.
An identity-only sentence does not assert source contents, while its URL,
authority and read provenance must still come from retained Core evidence.
"""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.acceptance_public import (
    INSUFFICIENT_CURRENTNESS_SUPPORT, OFFICIAL_SOURCE_SUPPORT,
    PUBLIC_GLOBAL_SUPPORT, PUBLIC_SENTENCE_SUPPORT, PUBLIC_VERIFIER_CONSISTENCY,
    SOURCE_IDENTITY, SOURCE_READ_PROVENANCE,
)
from core.answer_candidate import AcceptanceStatus, CandidateOrigin
from core.public_answer_evidence import build_public_answer_candidate
from test_core_milestone3b3a_public_evidence import FACT, URL, contract, inputs
from test_core_milestone3b3a1_public_calibration import annotations, evaluate, make


def identity_candidate(text, *, runtime=None, data=None, user_input="", provenance="citation"):
    data = data or inputs(text)
    binding = annotations(text, data[1])
    for entry in binding["sentences"]:
        entry.update(witnesses=[], provenance_claim=provenance, scope_status="not_applicable")
    return make(text, data=data, binding=binding, runtime=runtime,
                user_input=user_input)


def limitation_candidate(text, *, data=None, runtime=None):
    data = data or inputs(text)
    binding = annotations(text, data[1])
    for entry in binding["sentences"]:
        entry.update(claim_kind="limitation", source_ids=[], witnesses=[],
                     provenance_claim="none", scope_status="not_applicable")
    return make(text, data=data, binding=binding, runtime=runtime)


class PublicSemanticCalibrationTests(unittest.TestCase):
    def assertAccepted(self, candidate):
        outcome = evaluate(candidate)
        self.assertIs(outcome.status, AcceptanceStatus.ACCEPTED,
                      outcome.violated_invariants)
        self.assertEqual(outcome.violated_invariants, ())
        return outcome

    def assertNotAccepted(self, candidate, invariant):
        outcome = evaluate(candidate)
        self.assertIsNot(outcome.status, AcceptanceStatus.ACCEPTED)
        self.assertIn(invariant, outcome.violated_invariants)
        return outcome

    def test_citation_introductions_need_identity_not_content_witness(self):
        for prefix in ("Here is the official source: ", "Here's the official source: ",
                       "Here’s the official source: ", "The official source is ",
                       "Here is the source: ", "Here's the source: ",
                       "The source is ", "Official source: ",
                       "Here is the source URL: ", "The source URL is "):
            with self.subTest(prefix=prefix):
                text = prefix + URL + "."
                runtime = contract(metadata={"official_source_required": True,
                                             "exact_source_required": True})
                self.assertAccepted(identity_candidate(text, runtime=runtime))

    def test_citation_caption_is_not_new_authoritative_evidence(self):
        text = "Here is the official source: " + URL + "."
        candidate = identity_candidate(text)
        self.assertEqual(candidate.evidence.authoritative_claims, (FACT,))
        self.assertNotIn(text, candidate.evidence.authoritative_claims)
        self.assertAccepted(candidate)

    def test_wrong_citation_url_still_fails_source_identity_without_false_content_failure(self):
        text = "Here is the official source: https://support.example/not-loaded."
        outcome = self.assertNotAccepted(identity_candidate(text), SOURCE_IDENTITY)
        self.assertNotIn(PUBLIC_SENTENCE_SUPPORT, outcome.violated_invariants)

    def test_same_host_different_path_does_not_gain_identity(self):
        text = "The source is " + URL + "/unread."
        outcome = self.assertNotAccepted(identity_candidate(text), SOURCE_IDENTITY)
        self.assertNotIn(PUBLIC_SENTENCE_SUPPORT, outcome.violated_invariants)

    def test_citation_query_component_is_not_normalized_away(self):
        text = "The official source is " + URL + "?edition=unloaded."
        self.assertNotAccepted(identity_candidate(text), SOURCE_IDENTITY)

    def test_citation_retained_read_identity_is_eligible(self):
        redirected = "https://docs.vendor.example/readable-field-guide"
        text = "Here is the source: " + redirected + "."
        data = inputs(text)
        data[0]["sources"][0]["read_result"]["url"] = redirected
        self.assertAccepted(identity_candidate(text, data=data))

    def test_guessed_redirect_identity_is_ineligible(self):
        text = "Here is the source: https://docs.vendor.example/readable-field-guide."
        self.assertNotAccepted(identity_candidate(text), SOURCE_IDENTITY)

    def test_official_caption_cannot_override_nonofficial_source_metadata(self):
        text = "Here is the official source: " + URL + "."
        data = inputs(text)
        data[0]["sources"][0]["authority_tier"] = "independent_editorial"
        runtime = contract(metadata={"official_source_required": True})
        outcome = self.assertNotAccepted(identity_candidate(text, data=data, runtime=runtime),
                                         OFFICIAL_SOURCE_SUPPORT)
        self.assertNotIn(PUBLIC_SENTENCE_SUPPORT, outcome.violated_invariants)

    def test_official_caption_requires_real_authority_even_without_request_flag(self):
        text = "The official source is " + URL + "."
        data = inputs(text)
        data[0]["sources"][0]["authority_tier"] = "independent_editorial"
        self.assertNotAccepted(identity_candidate(text, data=data), OFFICIAL_SOURCE_SUPPORT)

    def test_primary_caption_uses_real_primary_metadata(self):
        text = "The primary source is " + URL + "."
        data = inputs(text)
        data[0]["sources"][0]["authority_tier"] = "primary_institutional"
        self.assertAccepted(identity_candidate(text, data=data))
        data[0]["sources"][0]["authority_tier"] = "independent_editorial"
        self.assertNotAccepted(identity_candidate(text, data=data), OFFICIAL_SOURCE_SUPPORT)

    def test_unavailable_bindings_do_not_make_caption_authority_invisible(self):
        for label in ("official", "primary"):
            with self.subTest(label=label):
                text = "The " + label + " source is " + URL + "."
                data = inputs(text)
                data[0]["sources"][0]["authority_tier"] = "independent_editorial"
                value = build_public_answer_candidate(
                    text=text, contract=contract(), research_result=data[0],
                    evidence_packet=data[1], verification_result=data[2])
                outcome = self.assertNotAccepted(value, OFFICIAL_SOURCE_SUPPORT)
                self.assertNotIn(PUBLIC_VERIFIER_CONSISTENCY, outcome.violated_invariants)

    def test_unavailable_bindings_still_allow_verified_caption_authority(self):
        for label, authority in (("official", "primary_official"),
                                 ("primary", "primary_institutional")):
            with self.subTest(label=label, authority=authority):
                text = "The " + label + " source is " + URL + "."
                data = inputs(text)
                data[0]["sources"][0]["authority_tier"] = authority
                value = build_public_answer_candidate(
                    text=text, contract=contract(), research_result=data[0],
                    evidence_packet=data[1], verification_result=data[2])
                self.assertAccepted(value)

    def test_read_identity_still_requires_admitted_loaded_evidence(self):
        text = "Here is the source: " + URL + "."
        data = inputs(text)
        data[0]["sources"][0]["read_success"] = False
        data[0]["sources"][0]["read_result"]["success"] = False
        self.assertNotAccepted(identity_candidate(text, data=data), SOURCE_READ_PROVENANCE)

    def test_current_user_official_identity_and_read_obligations_remain_visible(self):
        text = "Here is the official source: " + URL + "."
        candidate = identity_candidate(
            text, user_input="Check the official source and give the exact source URL.")
        for key in ("official_source_required", "source_read_required", "exact_source_required"):
            self.assertTrue(candidate.contract.metadata[key])
        self.assertAccepted(candidate)

    def test_caption_does_not_complete_missing_exact_requested_identity(self):
        text = "The source is " + URL + "."
        runtime = contract(metadata={"source_read_required": True,
                                     "exact_source_required": True,
                                     "requested_source_urls": (URL + "/other",)})
        self.assertNotAccepted(identity_candidate(text, runtime=runtime), SOURCE_IDENTITY)

    def test_citation_with_factual_tail_requires_content_witness(self):
        for text in ("Here is the source: " + URL + " and the chamber contains nine valves.",
                     "The source is " + URL + "; the chamber contains nine valves.",
                     "The official source is " + URL + ", which confirms nine valves."):
            with self.subTest(text=text):
                self.assertNotAccepted(identity_candidate(text), PUBLIC_SENTENCE_SUPPORT)

    def test_second_unsupported_sentence_is_not_hidden_by_citation(self):
        text = "Here is the source: " + URL + ". The chamber contains nine valves."
        self.assertNotAccepted(identity_candidate(text), PUBLIC_SENTENCE_SUPPORT)

    def test_citation_does_not_override_negative_legacy_sentence_support(self):
        text = "Here is the source: " + URL + "."
        data = inputs(text)
        state = data[2].verification_state
        state.update(global_supported=False, effective_supported=False,
                     unsupported_claim_count=1)
        state["sentence_assessments"][0]["supported"] = False
        state["effective_sentence_assessments"][0]["supported"] = False
        outcome = self.assertNotAccepted(identity_candidate(text, data=data),
                                         PUBLIC_SENTENCE_SUPPORT)
        self.assertIn(PUBLIC_GLOBAL_SUPPORT, outcome.violated_invariants)

    def test_citation_does_not_hide_verifier_digest_mismatch(self):
        text = "Here is the source: " + URL + "."
        data = inputs(text)
        data[2].verification_state["assessed_draft_digest"] = "0" * 64
        self.assertNotAccepted(identity_candidate(text, data=data),
                               PUBLIC_VERIFIER_CONSISTENCY)

    def test_checked_read_anaphora_can_use_exact_retained_target(self):
        for text in ("I actually checked it.", "I checked the page.",
                     "I did check it.", "I have checked it."):
            with self.subTest(text=text):
                runtime = contract(metadata={"source_read_required": True,
                                             "requested_source_urls": (URL,)})
                self.assertAccepted(identity_candidate(text, runtime=runtime,
                                                       provenance="read"))

    def test_checked_anaphora_without_bindings_does_not_gain_read_authority(self):
        text = "I actually checked it."
        data = inputs(text)
        value = build_public_answer_candidate(text=text, contract=contract(),
                                             research_result=data[0], evidence_packet=data[1],
                                             verification_result=data[2])
        self.assertNotAccepted(value, SOURCE_READ_PROVENANCE)

    def test_checked_read_does_not_satisfy_different_requested_url(self):
        text = "I actually checked it."
        runtime = contract(metadata={"source_read_required": True,
                                     "requested_source_urls": (URL + "/different",)})
        self.assertNotAccepted(identity_candidate(text, runtime=runtime,
                                                 provenance="read"), SOURCE_IDENTITY)

    def test_checked_statement_with_external_tail_is_not_identity_only(self):
        text = "I actually checked it and the chamber contains nine valves."
        runtime = contract(metadata={"source_read_required": True,
                                     "requested_source_urls": (URL,)})
        self.assertNotAccepted(identity_candidate(text, runtime=runtime,
                                                 provenance="read"), PUBLIC_SENTENCE_SUPPORT)

    def test_existing_unresolved_anaphoric_read_support_protection_remains(self):
        self.assertNotAccepted(identity_candidate("I did load it.", provenance="read"),
                               PUBLIC_SENTENCE_SUPPORT)

    def test_whole_first_person_unknown_nominal_is_epistemic_limitation(self):
        for text in ("I don't know what a qelric braid is.",
                     "I do not know what the molven lattice is.",
                     "I don’t know what 'brindle cadence' is.",
                     "I don't know what \"qelric braid\" is.",
                     "I don't know what ‘brindle cadence’ is."):
            with self.subTest(text=text):
                self.assertAccepted(limitation_candidate(text))

    def test_quoted_nominal_with_article_remains_bounded(self):
        for text in ("I don't know what a ‘qelric braid’ is.",
                     "I don’t know what a “qelric braid” is.",
                     "I'm not sure what the \"molven lattice\" means."):
            with self.subTest(text=text):
                self.assertAccepted(limitation_candidate(text))

    def test_uncertain_meaning_nominal_is_epistemic_limitation(self):
        for text in ("I'm not sure what qelric means.",
                     "I am not sure what the molven lattice means.",
                     "I’m not sure what 'brindle cadence' means."):
            with self.subTest(text=text):
                self.assertAccepted(limitation_candidate(text))

    def test_first_person_nonrecognition_is_epistemic_limitation(self):
        for text in ("I don't recognise qelric.", "I do not recognise the molven lattice.",
                     "I don’t recognise 'brindle cadence'.", "I don't recognize qelric."):
            with self.subTest(text=text):
                self.assertAccepted(limitation_candidate(text))

    def test_self_knowledge_does_not_create_topic_evidence(self):
        text = "I don't know what qelric means."
        candidate = limitation_candidate(text)
        self.assertEqual(candidate.evidence.authoritative_claims, (FACT,))
        self.assertNotIn("qelric", repr(candidate.evidence.evidence[0].data))
        self.assertAccepted(candidate)

    def test_safe_unknown_statement_does_not_assert_current_external_fact(self):
        text = "I don't know what qelric is."
        data = inputs(text)
        data[0]["freshness_sensitive"] = True
        self.assertAccepted(limitation_candidate(text, data=data))

    def test_unknown_statement_with_factual_clause_remains_unsupported(self):
        for text in ("I don't know what qelric is, but it contains nine valves.",
                     "I'm not sure what qelric means because it costs nine credits.",
                     "I don't recognise qelric and it weighs nine grams.",
                     "I don't know what qelric is; it causes a pressure change.",
                     "I don't recognise qelric -- costs nine credits."):
            with self.subTest(text=text):
                self.assertNotAccepted(limitation_candidate(text), PUBLIC_SENTENCE_SUPPORT)

    def test_nominal_topic_cannot_embed_asserted_world_fact(self):
        for text in ("I don't know what 'qelric contains nine valves' is.",
                     "I don’t know what a “qelric contains nine valves” is.",
                     "I'm not sure what 'qelric causes leaks' means.",
                     "I don't recognise 'qelric is a metal'."):
            with self.subTest(text=text):
                self.assertNotAccepted(limitation_candidate(text), PUBLIC_SENTENCE_SUPPORT)

    def test_nonexistence_claim_is_not_epistemic_self_knowledge(self):
        for text in ("Qelric does not exist.", "There is no qelric braid.",
                     "Nobody knows what qelric is."):
            with self.subTest(text=text):
                self.assertNotAccepted(limitation_candidate(text), PUBLIC_SENTENCE_SUPPORT)

    def test_not_first_person_does_not_assert_candidate_self_knowledge(self):
        for text in ("You don't know what qelric is.", "They don't recognise qelric.",
                     "The field guide does not recognise qelric."):
            with self.subTest(text=text):
                self.assertNotAccepted(limitation_candidate(text), PUBLIC_SENTENCE_SUPPORT)

    def test_unknown_sentence_cannot_hide_later_exact_answer(self):
        text = "I don't know what qelric is. The current value is 672."
        data = inputs(text)
        data[0]["freshness_sensitive"] = True
        outcome = self.assertNotAccepted(limitation_candidate(text, data=data),
                                         PUBLIC_SENTENCE_SUPPORT)
        self.assertIn(INSUFFICIENT_CURRENTNESS_SUPPORT, outcome.violated_invariants)

    def test_epistemic_label_does_not_authorize_followup_offer(self):
        text = "I don't know what qelric is. Would you like me to search?"
        self.assertNotAccepted(limitation_candidate(text), PUBLIC_SENTENCE_SUPPORT)

    def test_new_unknown_forms_do_not_override_negative_legacy_support(self):
        text = "I don't know what qelric is."
        data = inputs(text)
        state = data[2].verification_state
        state.update(global_supported=False, effective_supported=False,
                     unsupported_claim_count=1)
        state["sentence_assessments"][0]["supported"] = False
        state["effective_sentence_assessments"][0]["supported"] = False
        self.assertNotAccepted(limitation_candidate(text, data=data), PUBLIC_GLOBAL_SUPPORT)

    def test_valid_new_forms_have_origin_invariant_decisions(self):
        for candidate in (identity_candidate("Here's the official source: " + URL + "."),
                          limitation_candidate("I don't know what qelric is."),
                          limitation_candidate("I'm not sure what qelric means."),
                          limitation_candidate("I don't recognise qelric.")):
            with self.subTest(text=candidate.text):
                self.assertAccepted(candidate)
                outcomes = [evaluate(candidate.with_origin(origin)) for origin in CandidateOrigin]
                self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))

    def test_invalid_new_forms_have_origin_invariant_decisions(self):
        for candidate in (identity_candidate("The source is https://research.example/unread."),
                          limitation_candidate("I don't recognise qelric and it costs nine credits.")):
            with self.subTest(text=candidate.text):
                outcomes = [evaluate(candidate.with_origin(origin)) for origin in CandidateOrigin]
                self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))
                self.assertIsNot(outcomes[0].status, AcceptanceStatus.ACCEPTED)

    def test_path_metadata_cannot_change_identity_or_limitation_authority(self):
        candidate = identity_candidate("The source is https://research.example/unread.")
        original = evaluate(candidate)
        other = replace(candidate, validation_metadata={"path": "trusted_core", "official": True})
        self.assertEqual(evaluate(other), original)


if __name__ == "__main__":
    unittest.main()
