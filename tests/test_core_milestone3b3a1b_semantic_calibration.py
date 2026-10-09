"""Bounded self-knowledge and retrieval honesty use neutral retained sources.

Source annotation is observational. Neither a limitation label, a terse
answer nor candidate wording creates evidence or bypasses the legacy verifier.
"""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.acceptance_public import (
    PUBLIC_GLOBAL_SUPPORT, PUBLIC_SENTENCE_SUPPORT, PUBLIC_VERIFIER_CONSISTENCY,
    SOURCE_IDENTITY, SOURCE_READ_PROVENANCE, _explicit_provenance_claim,
)
from core.answer_candidate import AcceptanceStatus, CandidateOrigin
from core.public_answer_evidence import build_public_answer_candidate
from test_core_milestone3b3a_public_evidence import FACT, URL, contract, inputs
from test_core_milestone3b3a1_public_calibration import annotations, evaluate, make
from test_core_milestone3b3a1a_semantic_calibration import identity_candidate, limitation_candidate


class PublicSemanticCalibrationTests(unittest.TestCase):
    def assertAccepted(self, value):
        outcome = evaluate(value)
        self.assertIs(outcome.status, AcceptanceStatus.ACCEPTED, outcome.violated_invariants)
        self.assertEqual(outcome.violated_invariants, ())
        return outcome

    def assertNotAccepted(self, value, invariant=PUBLIC_SENTENCE_SUPPORT):
        outcome = evaluate(value)
        self.assertIsNot(outcome.status, AcceptanceStatus.ACCEPTED)
        self.assertIn(invariant, outcome.violated_invariants)
        return outcome

    def test_labelled_quoted_nonrecognition_with_nominal_domain(self):
        for text in (
            'I don\'t recognise the term "voralic conduit" in fluid mechanics.',
            "I do not recognize the word 'solenic thread' in regional notation.",
            "I don’t recognise the concept ‘mervic braid’ in computational geometry.",
            "I don't recognise the phrase 'noral cadence' in signal theory.",
        ):
            with self.subTest(text=text):
                self.assertAccepted(limitation_candidate(text))

    def test_ordinary_nominal_topic_can_have_bounded_context(self):
        for text in (
            "I don't recognise voralic conduit in fluid mechanics.",
            "I do not recognise mervic braid in the context of computational geometry.",
            "I don't recognize the term 'solenic thread' in the context of signal theory.",
        ):
            with self.subTest(text=text):
                self.assertAccepted(limitation_candidate(text))

    def test_first_person_unfamiliarity_preserves_the_same_bounded_context(self):
        for text in (
            "I'm unfamiliar with the concept 'mervic braid' in computational geometry.",
            "I’m not familiar with the word “solenic thread” in signal theory.",
            "I am not sufficiently familiar with voralic conduit in the context of fluid mechanics.",
            "I don't know enough about the term 'noral cadence' in signal theory.",
        ):
            with self.subTest(text=text):
                self.assertAccepted(limitation_candidate(text))

    def test_labelled_topic_also_supports_bounded_meaning_questions(self):
        for text in (
            "I don't know what the term 'narvel lattice' means.",
            'I’m not sure what the word "sorelic" means.',
            "I don't know what the concept 'mervic braid' is.",
        ):
            with self.subTest(text=text):
                self.assertAccepted(limitation_candidate(text))

    def test_casing_typography_and_harmless_whitespace_remain_bounded(self):
        for text in (
            "I DON’T RECOGNISE THE TERM “VORALIC CONDUIT” IN FLUID MECHANICS.",
            "I don't recognise   the term 'noral cadence'   in the context of signal theory.",
        ):
            with self.subTest(text=text):
                self.assertAccepted(limitation_candidate(text))

    def test_self_knowledge_does_not_create_domain_or_topic_evidence(self):
        text = "I don't recognise the term 'mervic braid' in computational geometry."
        value = limitation_candidate(text)
        self.assertEqual(value.evidence.authoritative_claims, (FACT,))
        self.assertNotIn(text, value.evidence.authoritative_claims)
        self.assertFalse(any("mervic" in item.claim for item in value.evidence.evidence))
        self.assertAccepted(value)

    def test_external_factual_tail_cannot_hide_in_context_wrapper(self):
        for text in (
            "I don't recognise the term 'mervic braid' in geometry, but it contains copper.",
            "I don't recognise 'voralic conduit' in fluid mechanics and it costs twelve credits.",
            "I'm unfamiliar with 'solenic thread' in signal theory; it causes interference.",
            "I don't recognise 'noral cadence' in geometry because the device is broken.",
        ):
            with self.subTest(text=text):
                self.assertNotAccepted(limitation_candidate(text))

    def test_topic_wrapper_cannot_embed_an_external_proposition(self):
        for text in (
            "I don't recognise the term 'conduit contains copper' in mechanics.",
            "I don't recognise the concept 'geometry is complete' in notation.",
            "I'm unfamiliar with the phrase 'lattice causes failures' in signal theory.",
            "I don't know what the term 'conduit has valves' means.",
        ):
            with self.subTest(text=text):
                self.assertNotAccepted(limitation_candidate(text))

    def test_domain_context_cannot_smuggle_in_a_proposition(self):
        for text in (
            "I don't recognise 'voralic conduit' in mechanics that has turbines.",
            "I don't recognise 'mervic braid' in the context of geometry is complete.",
            "I'm unfamiliar with 'solenic thread' in the context of radio contains copper.",
            "I don't recognise the term 'noral cadence' in signal theory which causes leaks.",
            "I don't recognise 'noral cadence' in mechanics where valves leak.",
            "I don't recognise 'noral cadence' in mechanics when valves leak.",
        ):
            with self.subTest(text=text):
                self.assertNotAccepted(limitation_candidate(text))

    def test_quoted_number_labels_do_not_hide_exact_claims(self):
        for text in (
            "I don't recognise the term '47 bars' in mechanics.",
            "I don't recognise the term 'Ⅻ bars' in mechanics.",
            "I don't recognise the term '½ volts' in signal theory.",
            "I don't recognise 'voralic 47' in geometry.",
            "I'm unfamiliar with the concept 'version 918' in notation.",
            "I don't know what 'pressure 47' means.",
        ):
            with self.subTest(text=text):
                self.assertNotAccepted(limitation_candidate(text))

    def test_domain_numeric_assertions_are_not_simple_nominal_context(self):
        for text in (
            "I don't recognise 'noral cadence' in region 47.",
            "I'm unfamiliar with 'mervic braid' in the context of pressure 918.",
        ):
            with self.subTest(text=text):
                self.assertNotAccepted(limitation_candidate(text))

    def test_non_first_person_unknown_statement_remains_external(self):
        for text in (
            "You don't recognise 'voralic conduit' in mechanics.",
            "Nobody recognises the term 'mervic braid' in geometry.",
            "The guide is unfamiliar with 'solenic thread' in signal theory.",
        ):
            with self.subTest(text=text):
                self.assertNotAccepted(limitation_candidate(text))

    def test_nonexistence_and_world_state_are_not_self_knowledge(self):
        for text in (
            "There is no 'voralic conduit' in mechanics.",
            "The term 'mervic braid' does not exist in geometry.",
            "The concept 'solenic thread' is unknown in signal theory.",
        ):
            with self.subTest(text=text):
                self.assertNotAccepted(limitation_candidate(text))

    def test_quoted_topic_cannot_contain_code_or_disguised_factual_punctuation(self):
        for text in (
            "I don't recognise the term 'valve: open' in mechanics.",
            "I don't recognise 'geometry; pressure rises' in notation.",
            "I'm unfamiliar with the concept 'x = 47' in signal theory.",
            "I don't recognise 'mervic `execute`' in geometry.",
        ):
            with self.subTest(text=text):
                self.assertNotAccepted(limitation_candidate(text))

    def test_unknown_statement_cannot_hide_a_later_factual_sentence(self):
        text = "I don't recognise 'voralic conduit' in mechanics. The device contains twelve valves."
        self.assertNotAccepted(limitation_candidate(text))

    def test_limitation_annotation_cannot_turn_yes_no_answer_into_nonfactual(self):
        for text in ("No, they don't.", "Yes, it does.", "No.", "Yes."):
            with self.subTest(text=text):
                self.assertNotAccepted(limitation_candidate(text))

    def test_terse_factual_answer_still_consumes_legacy_sentence_support(self):
        for text in ("No, they don't.", "Yes, it does."):
            with self.subTest(text=text):
                self.assertAccepted(make(text))
                data = inputs(text)
                state = data[2].verification_state
                state.update(global_supported=False, effective_supported=False, unsupported_claim_count=1)
                state["sentence_assessments"][0]["supported"] = False
                state["effective_sentence_assessments"][0]["supported"] = False
                result = self.assertNotAccepted(make(text, data=data))
                self.assertIn(PUBLIC_GLOBAL_SUPPORT, result.violated_invariants)

    def test_truthful_limitation_does_not_override_a_negative_legacy_verdict(self):
        text = "I don't recognise 'voralic conduit' in mechanics."
        data = inputs(text)
        state = data[2].verification_state
        state.update(global_supported=False, effective_supported=False, unsupported_claim_count=1)
        state["sentence_assessments"][0]["supported"] = False
        state["effective_sentence_assessments"][0]["supported"] = False
        self.assertNotAccepted(limitation_candidate(text, data=data), PUBLIC_GLOBAL_SUPPORT)

    def test_truthful_limitation_does_not_hide_a_trusted_draft_digest_error(self):
        text = "I don't recognise 'mervic braid' in geometry."
        data = inputs(text)
        data[2].verification_state["assessed_draft_digest"] = "0" * 64
        self.assertNotAccepted(limitation_candidate(text, data=data), PUBLIC_VERIFIER_CONSISTENCY)

    def test_safe_topic_wrappers_are_origin_invariant(self):
        for text in (
            "I don't recognise the term 'mervic braid' in geometry.",
            "I'm unfamiliar with 'solenic thread' in the context of signal theory.",
        ):
            value = limitation_candidate(text)
            baseline = self.assertAccepted(value)
            for origin in CandidateOrigin:
                with self.subTest(text=text, origin=origin):
                    changed = evaluate(replace(value, origin=origin))
                    self.assertEqual(changed, baseline)

    def test_unsafe_topic_wrappers_are_origin_invariant(self):
        value = limitation_candidate("I don't recognise the term 'conduit contains copper' in mechanics.")
        baseline = self.assertNotAccepted(value)
        for origin in CandidateOrigin:
            with self.subTest(origin=origin):
                self.assertEqual(evaluate(replace(value, origin=origin)), baseline)

    def test_fetched_and_pulled_source_claims_require_inspectable_bindings(self):
        for text in (
            "I fetched the page.", "I pulled the text from the live site.",
            "We have fetched the source text.", "I just pulled the page text.",
            "Just pulled the text from the live site.",
        ):
            with self.subTest(text=text):
                data = inputs(text)
                value = build_public_answer_candidate(text=text, contract=contract(),
                    research_result=data[0], evidence_packet=data[1], verification_result=data[2])
                result = self.assertNotAccepted(value, SOURCE_READ_PROVENANCE)
                self.assertNotIn(PUBLIC_VERIFIER_CONSISTENCY, result.violated_invariants)

    def test_retrieval_claims_do_not_import_a_different_url_identity(self):
        text = "I fetched https://research.example/unread."
        runtime = contract(metadata={"source_read_required": True, "requested_source_urls": (URL,)})
        value = identity_candidate(text, runtime=runtime, provenance="read")
        self.assertNotAccepted(value, SOURCE_IDENTITY)

    def test_actual_fetched_read_with_bound_identity_can_remain_accepted(self):
        for text in ("I fetched the page.", "I pulled the text."):
            with self.subTest(text=text):
                runtime = contract(metadata={"source_read_required": True, "requested_source_urls": (URL,)})
                self.assertAccepted(identity_candidate(text, runtime=runtime, provenance="read"))

    def test_missing_retrieval_binding_authority_is_origin_invariant(self):
        text = "I pulled the text from the live site."
        data = inputs(text)
        value = build_public_answer_candidate(text=text, contract=contract(), research_result=data[0],
                                             evidence_packet=data[1], verification_result=data[2])
        baseline = self.assertNotAccepted(value, SOURCE_READ_PROVENANCE)
        for origin in CandidateOrigin:
            with self.subTest(origin=origin):
                self.assertEqual(evaluate(value.with_origin(origin)), baseline)

    def test_conditional_future_questioned_and_negated_retrieval_are_not_read_assertions(self):
        for text in (
            "If I fetched the page, I could answer later.",
            "I will fetch the page.", "I would pull the text.",
            "Did I fetch the page?", "Have I pulled the text?",
            "I did not fetch the page.", "I haven't pulled the text.",
            'The note says "I fetched the page".',
        ):
            with self.subTest(text=text):
                self.assertFalse(_explicit_provenance_claim(text))

    def test_conjoined_affirmative_retrieval_remains_a_read_assertion(self):
        for text in (
            "I did not load it, but I pulled the text from the live site.",
            "I did not browse there, but just fetched the page text.",
            "I checked no other material; and I fetched the page.",
        ):
            with self.subTest(text=text):
                self.assertTrue(_explicit_provenance_claim(text))
                data = inputs(text)
                value = build_public_answer_candidate(text=text, contract=contract(),
                    research_result=data[0], evidence_packet=data[1], verification_result=data[2])
                self.assertNotAccepted(value, SOURCE_READ_PROVENANCE)

    def test_nonasserted_conjoined_retrieval_cannot_manufacture_read_claims(self):
        for text in (
            "If I did not load it, but I fetched the page, I could answer later.",
            '"I did not load it, but I pulled the text from the live site."',
            'The note says "I did not load it, but I fetched the page."',
            "I did not load it, and I did not fetch the page.",
            "I did not load it, but I will fetch the page.",
            "Did I browse there, and did I fetch the page?",
        ):
            with self.subTest(text=text):
                self.assertFalse(_explicit_provenance_claim(text))

    def test_bounded_locative_source_caption_still_uses_exact_loaded_identity(self):
        for text in (
            "The source is right here: " + URL + ".",
            "The official source is here: " + URL + ".",
        ):
            with self.subTest(text=text):
                self.assertAccepted(identity_candidate(text))
        value = identity_candidate("The source is right here: http://docs.vendor.example/orchard.")
        result = self.assertNotAccepted(value, SOURCE_IDENTITY)
        self.assertNotIn(PUBLIC_SENTENCE_SUPPORT, result.violated_invariants)

    def test_locative_caption_does_not_exempt_appended_contents(self):
        for text in (
            "The source is right here: " + URL + " and the chamber contains twelve valves.",
            "The official source is here: " + URL + ", which confirms twelve valves.",
        ):
            with self.subTest(text=text):
                self.assertNotAccepted(identity_candidate(text))


if __name__ == "__main__":
    unittest.main()
