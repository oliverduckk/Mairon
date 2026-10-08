"""Affirmative user morphology uses the existing item-identity state resolver.

Contractions and first-person plural statements add no new authority: only a
direct user supply of an identical named input can resolve its prior omission.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from core.acceptance_evaluator import CoreAcceptanceEvaluator
from core.acceptance_publication import publish_limitation_response
from core.acceptance_shadow import _limitation_evidence
from core.answer_candidate import AcceptanceStatus, AnswerCandidate, CandidateOrigin
from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    build_insufficient_user_context_fallback,
    build_user_context_reasoning_fallback,
)
from core.evidence import EvidenceKind
from core.missing_inputs import extract_missing_inputs, parse_missing_item_list, resolve_missing_inputs


def _labels(state):
    return () if state is None else tuple(
        re.sub(r"^(?:the|a|an)\s+", "", item.casefold()) for item in state.items
    )


def _history(*texts):
    return [{"role": "user", "content": text} for text in texts]


def _contract():
    return AnswerContractRuntime(
        intent="factual_question", authority="user_context", epistemic_mode="insufficient_user_context",
        allow_follow_up_question=True,
    )


def _candidate(user, answer=None):
    contract = _contract()
    evidence = _limitation_evidence(
        contract=contract, user_input=user, conversation=(), user_history=(),
        failure_reason=None, research_result=None,
    )
    return AnswerCandidate(
        text=build_insufficient_user_context_fallback(user) if answer is None else answer,
        origin=CandidateOrigin.DETERMINISTIC_FALLBACK, contract=contract, evidence=evidence,
    )


class UserSupplyMorphologyTests(unittest.TestCase):
    omission = "I have not provided the contour map."

    def _assert_clears(self, supplied):
        self.assertIsNone(extract_missing_inputs(self.omission + " " + supplied))
        self.assertIsNone(resolve_missing_inputs(_history(self.omission, supplied)))

    def _assert_preserves(self, supplied, expected=("contour map",), omission=None):
        absent = self.omission if omission is None else omission
        self.assertEqual(_labels(extract_missing_inputs(absent + " " + supplied)), expected)
        self.assertEqual(_labels(resolve_missing_inputs(_history(absent, supplied))), expected)

    def test_ascii_first_person_perfect_contraction_clears_identical_item(self):
        self._assert_clears("I've uploaded the contour map now.")

    def test_typographic_first_person_perfect_contraction_clears_identical_item(self):
        self._assert_clears("I’ve uploaded the contour map now.")

    def test_contracted_attach_forms_clear_identical_item(self):
        for subject in ("I've", "I’ve"):
            with self.subTest(subject=subject):
                self._assert_clears(subject + " attached the contour map now.")

    def test_contracted_provide_forms_clear_identical_item(self):
        for subject in ("I've", "I’ve"):
            with self.subTest(subject=subject):
                self._assert_clears(subject + " provided the contour map now.")

    def test_contracted_send_forms_clear_identical_item(self):
        for subject in ("I've", "I’ve"):
            with self.subTest(subject=subject):
                self._assert_clears(subject + " sent the contour map now.")

    def test_plural_simple_past_clears_identical_item(self):
        self._assert_clears("We uploaded the contour map now.")

    def test_plural_expanded_perfect_clears_identical_item(self):
        self._assert_clears("We have uploaded the contour map now.")

    def test_plural_ascii_perfect_contraction_clears_identical_item(self):
        self._assert_clears("We've uploaded the contour map now.")

    def test_plural_typographic_perfect_contraction_clears_identical_item(self):
        self._assert_clears("We’ve uploaded the contour map now.")

    def test_plural_attach_provide_and_send_share_identical_item_resolution(self):
        for subject in ("We", "We have", "We've", "We’ve"):
            for verb in ("attached", "provided", "sent"):
                with self.subTest(subject=subject, verb=verb):
                    self._assert_clears(subject + " " + verb + " the contour map now.")

    def test_same_turn_coordinated_contracted_and_plural_supply_clears_identical_item(self):
        for subject in ("I've", "I’ve", "We", "We have", "We've", "We’ve"):
            for connector in (", but ", ", and "):
                with self.subTest(subject=subject, connector=connector):
                    user = "I have not provided the contour map" + connector + subject + " uploaded the contour map now."
                    self.assertIsNone(extract_missing_inputs(user))

    def test_partial_contracted_and_plural_supply_leaves_only_unsupplied_items(self):
        absent = "I have not supplied the contour map, wiring index or sample record."
        for subject in ("I've", "I’ve", "We", "We have", "We've", "We’ve"):
            with self.subTest(subject=subject):
                self._assert_preserves(
                    subject + " uploaded the wiring index now.",
                    expected=("contour map", "sample record"), omission=absent,
                )

    def test_contracted_and_plural_supply_of_different_item_does_not_clear_omission(self):
        for subject in ("I've", "I’ve", "We", "We have", "We've", "We’ve"):
            with self.subTest(subject=subject):
                self._assert_preserves(subject + " uploaded the wiring index now.")

    def test_contracted_and_plural_positive_disjunction_does_not_clear_either_item(self):
        absent = "I have not supplied the contour map or wiring index."
        for subject in ("I've", "I’ve", "We", "We have", "We've", "We’ve"):
            with self.subTest(subject=subject):
                self._assert_preserves(
                    subject + " uploaded the contour map or wiring index now.",
                    expected=("contour map", "wiring index"), omission=absent,
                )

    def test_contracted_and_plural_supply_conjunction_resolves_only_named_items(self):
        absent = "I have not supplied the contour map, wiring index or sample record."
        for subject in ("I've", "We have", "We've", "We’ve"):
            with self.subTest(subject=subject):
                self._assert_preserves(
                    subject + " uploaded the contour map and sample record now.",
                    expected=("wiring index",), omission=absent,
                )

    def test_quoted_contracted_and_plural_supply_remains_non_authoritative(self):
        for supplied in (
            '"I\'ve uploaded the contour map now."',
            '“I’ve uploaded the contour map now.”',
            '"We\'ve uploaded the contour map now."',
            '“We’ve uploaded the contour map now.”',
        ):
            with self.subTest(supplied=supplied):
                self._assert_preserves(supplied)

    def test_reported_contracted_and_plural_supply_remains_non_authoritative(self):
        for subject in ("I've", "I’ve", "We've", "We’ve"):
            supplied = 'A colleague said "' + subject + ' uploaded the contour map now."'
            with self.subTest(supplied=supplied):
                self._assert_preserves(supplied)

    def test_prefix_conditional_contracted_and_plural_supply_remains_non_authoritative(self):
        for subject in ("I've", "I’ve", "We have", "We've", "We’ve"):
            with self.subTest(subject=subject):
                self._assert_preserves("If " + subject + " uploaded the contour map, the check can start.")

    def test_suffix_conditional_contracted_and_plural_supply_remains_non_authoritative(self):
        for subject in ("I've", "I’ve", "We have", "We've", "We’ve"):
            with self.subTest(subject=subject):
                self._assert_preserves(subject + " uploaded the contour map if I remember correctly.")

    def test_future_contracted_and_plural_supply_remains_non_authoritative(self):
        for supplied in (
            "I'll upload the contour map tomorrow.",
            "I’ll have uploaded the contour map by tomorrow.",
            "We'll upload the contour map tomorrow.",
            "We’ll have uploaded the contour map by tomorrow.",
            "We will upload the contour map tomorrow.",
        ):
            with self.subTest(supplied=supplied):
                self._assert_preserves(supplied)

    def test_questioned_contracted_and_plural_supply_remains_non_authoritative(self):
        for subject in ("I've", "I’ve", "We", "We have", "We've", "We’ve"):
            with self.subTest(subject=subject):
                self._assert_preserves(subject + " uploaded the contour map?")

    def test_negated_contracted_and_plural_supply_remains_non_authoritative(self):
        for supplied in (
            "I've not uploaded the contour map.", "I’ve not attached the contour map.",
            "We've not uploaded the contour map.", "We’ve not sent the contour map.",
            "We have not uploaded the contour map.", "We didn't upload the contour map.",
            "We did not upload the contour map.",
        ):
            with self.subTest(supplied=supplied):
                self._assert_preserves(supplied)

    def test_assistant_contracted_and_plural_supply_cannot_resolve_user_state(self):
        for subject in ("I've", "I’ve", "We", "We have", "We've", "We’ve"):
            history = _history(self.omission)
            history.append({"role": "assistant", "content": subject + " uploaded the contour map now."})
            with self.subTest(subject=subject):
                self.assertEqual(_labels(resolve_missing_inputs(history)), ("contour map",))

    def test_contract_morphology_cannot_create_alias_matching(self):
        for label in ("contour maps", "map", "elevation drawing", "new contour map"):
            for subject in ("I've", "We've"):
                with self.subTest(label=label, subject=subject):
                    self._assert_preserves(subject + " uploaded the " + label + " now.")

    def test_existing_identity_normalization_applies_to_contracted_and_plural_forms(self):
        for supplied in ("I've uploaded a CONTOUR MAP now.", "We’ve uploaded CONTOUR MAP now."):
            with self.subTest(supplied=supplied):
                self._assert_clears(supplied)

    def test_real_followup_does_not_request_item_supplied_by_contraction_or_plural(self):
        for subject in ("I've", "I’ve", "We", "We have", "We've", "We’ve"):
            history = _history(self.omission, subject + " uploaded the contour map now.")
            with self.subTest(subject=subject):
                answer = build_user_context_reasoning_fallback("What should I send?", history)
                self.assertFalse(answer.startswith("Send me "), answer)

    def test_real_followup_requests_only_remaining_items_after_plural_partial_supply(self):
        for subject in ("I've", "We've", "We have", "We"):
            history = _history(
                "I have not supplied the contour map or the sample record.",
                subject + " uploaded the contour map now.",
            )
            with self.subTest(subject=subject):
                answer = build_user_context_reasoning_fallback("What should I send?", history)
                self.assertEqual(answer, "Send me the sample record. That's what I need to check it properly.")

    def test_partial_supply_constructs_only_remaining_typed_availability(self):
        for subject in ("I've", "I’ve", "We", "We have", "We've", "We’ve"):
            user = "I have not supplied the contour map or sample record, but " + subject + " uploaded the contour map now."
            with self.subTest(subject=subject):
                candidate = _candidate(user)
                availability = next(evidence.data["availability"] for evidence in candidate.evidence.evidence
                                    if evidence.kind == EvidenceKind.UNCERTAINTY
                                    and evidence.data.get("availability", {}).get("kind") == "missing_input")
                self.assertEqual(_labels(SimpleNamespace(items=availability["missing_inputs"])), ("sample record",))
                self.assertEqual(CoreAcceptanceEvaluator().evaluate(candidate).status, AcceptanceStatus.ACCEPTED)

    def test_candidate_prose_cannot_claim_supply_or_change_typed_state(self):
        user = "I have not supplied the contour map or sample record."
        valid = _candidate(user)
        invalid = _candidate(user, "We've uploaded the contour map now. The sample record contains 263 entries.")
        self.assertEqual(invalid.evidence, valid.evidence)
        self.assertNotEqual(CoreAcceptanceEvaluator().evaluate(invalid).status, AcceptanceStatus.ACCEPTED)

    def test_strict_candidate_list_parser_is_unchanged_for_positive_assertion_tails(self):
        for subject in ("I've", "I’ve", "We", "We have", "We've", "We’ve"):
            with self.subTest(subject=subject):
                self.assertIsNone(parse_missing_item_list("the contour map, but " + subject + " uploaded the sample record now"))

    def test_same_contract_evidence_and_text_are_origin_and_path_invariant(self):
        user = "I have not supplied the contour map or sample record, but We’ve uploaded the contour map now."
        valid = _candidate(user)
        for text, expected in (
            (valid.text, "accepted"),
            ("I cannot determine that because you have not given me the contour map.", "replaced"),
        ):
            baseline = None
            for origin in CandidateOrigin:
                for path in ("neutral.first", "neutral.second"):
                    with self.subTest(origin=origin, path=path, expected=expected):
                        result = publish_limitation_response(
                            text=text, contract=_contract(), user_input=user,
                            path=path, origin=origin, emit=False,
                        )
                        current = (result.text, result.record.decision, result.record.replacement_decision,
                                   result.record.outcome, result.record.replacement_used)
                        if baseline is None:
                            baseline = current
                        self.assertEqual(current, baseline)
                        self.assertEqual(result.record.outcome, expected)


if __name__ == "__main__":
    unittest.main()
