"""Item-bound user omission corrections do not create or retain stale authority.

The regressions exercise the shared resolver, the real follow-up builder, the
canonical evidence factory and the existing enforced provider branch. All
examples concern neutral user-supplied labels rather than benchmark fixtures.
"""
from __future__ import annotations

import re
import sys
import unicodedata
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
from core.missing_inputs import (
    extract_missing_inputs,
    parse_missing_item_list,
    resolve_missing_inputs,
)

from test_core_milestone3b2b_bounded_publication import _provider_branch


def _labels(missing):
    if missing is None:
        return ()
    return tuple(re.sub(r"^(?:the|a|an)\s+", "", unicodedata.normalize("NFC", item).casefold())
                 for item in missing.items)


def _contract():
    return AnswerContractRuntime(
        intent="factual_question", authority="user_context", epistemic_mode="insufficient_user_context",
        allow_follow_up_question=True,
    )


def _candidate(user, answer=None):
    contract = _contract()
    bundle = _limitation_evidence(
        contract=contract, user_input=user, conversation=(), user_history=(),
        failure_reason=None, research_result=None,
    )
    return AnswerCandidate(
        text=build_insufficient_user_context_fallback(user) if answer is None else answer,
        origin=CandidateOrigin.DETERMINISTIC_FALLBACK, contract=contract, evidence=bundle,
    )


class MissingInputItemStateResolutionTests(unittest.TestCase):
    def _assert_labels(self, value, expected):
        self.assertEqual(_labels(value), tuple(expected))
        return value

    def _history(self, *texts):
        return [{"role": "user", "content": text} for text in texts]

    def _assert_followup(self, history, expected):
        state = resolve_missing_inputs(history)
        self._assert_labels(state, expected)
        answer = build_user_context_reasoning_fallback("What should I send?", history)
        if state is not None:
            self.assertEqual(answer, "Send me " + state.description + ". That's what I need to check it properly.")
        else:
            self.assertFalse(answer.startswith("Send me "), answer)
        return answer

    def test_same_turn_different_item_supply_preserves_omission(self):
        user = "I have not provided the site plan, but the cable list is attached now."
        self._assert_labels(extract_missing_inputs(user), ("site plan",))

    def test_same_turn_same_item_supply_cancels_omission(self):
        for user in (
            "I have not provided the site plan, but the site plan is attached now.",
            "I have not sent the site plan. I uploaded the site plan now.",
            "I did not supply the site plan yet; I have supplied the site plan now.",
        ):
            with self.subTest(user=user):
                self.assertIsNone(extract_missing_inputs(user))

    def test_same_turn_partial_supply_preserves_only_unsupplied_items(self):
        user = "I have not provided the site plan, cable list or inspection sheet. I uploaded the cable list now."
        parsed = self._assert_labels(extract_missing_inputs(user), ("site plan", "inspection sheet"))
        self.assertNotIn("cable list", parsed.description.casefold())

    def test_coordinated_passive_partial_supply_never_promotes_omission_list_suffix(self):
        for omitted in ("the terrain sketch and the cable list", "the terrain sketch or the cable list"):
            with self.subTest(omitted=omitted):
                user = "I have not provided " + omitted + ", and the terrain sketch is attached now."
                self._assert_labels(extract_missing_inputs(user), ("cable list",))

    def test_same_turn_multiple_precise_supplies_leave_remaining_item(self):
        user = "I have not uploaded the terrain sketch, cable list or inspection sheet. I uploaded the cable list. I sent the terrain sketch now."
        self._assert_labels(extract_missing_inputs(user), ("inspection sheet",))

    def test_same_turn_filename_omission_is_cancelled_by_later_identical_filename_supply(self):
        for user in (
            "I have not uploaded sensor.csv. I uploaded sensor.csv now.",
            "I have not sent cable-map.svg, but cable-map.svg is attached now.",
        ):
            with self.subTest(user=user):
                self.assertIsNone(extract_missing_inputs(user))

    def test_passive_different_item_supply_does_not_cancel_later_omission(self):
        user = "The cable list is attached now, but I have not provided the terrain sketch."
        self._assert_labels(extract_missing_inputs(user), ("terrain sketch",))

    def test_later_same_turn_condition_does_not_invalidate_initial_omission(self):
        user = "I have not supplied the terrain sketch, but I uploaded the terrain sketch if I remember correctly."
        self._assert_labels(extract_missing_inputs(user), ("terrain sketch",))

    def test_coordinated_conditional_passive_supply_does_not_erase_initial_omission(self):
        user = "I have not supplied the terrain sketch, and the cable list is attached if I remember correctly."
        self._assert_labels(extract_missing_inputs(user), ("terrain sketch",))

    def test_grammar_words_in_filename_labels_do_not_change_statement_authority(self):
        for filename in ("if.yaml", "told.csv", "says.txt"):
            with self.subTest(filename=filename):
                omission = "I have not uploaded " + filename + "."
                supplied = "I uploaded " + filename + " now."
                self._assert_labels(extract_missing_inputs(omission), (filename,))
                self.assertIsNone(extract_missing_inputs(omission + " " + supplied))
                self._assert_followup(self._history(omission, supplied), ())

    def test_told_you_identity_can_be_corrected_by_later_told_you_supply(self):
        for user in (
            "I have not told you the aperture size. I have told you the aperture size now.",
            "I have not told you the aperture size, but I told you the aperture size now.",
        ):
            with self.subTest(user=user):
                self.assertIsNone(extract_missing_inputs(user))

    def test_positive_nominal_told_you_clause_does_not_block_later_direct_omission(self):
        user = "I told you the aperture size, but I have not provided the terrain sketch."
        self._assert_labels(extract_missing_inputs(user), ("terrain sketch",))

    def test_same_turn_absence_after_supply_remains_current(self):
        user = "I uploaded the site plan earlier. I have not provided the site plan."
        self._assert_labels(extract_missing_inputs(user), ("site plan",))

    def test_cross_turn_same_item_supply_cancels_stale_omission(self):
        history = self._history("I have not provided the site plan.", "I uploaded the site plan now.")
        self._assert_followup(history, ())

    def test_cross_turn_different_item_supply_preserves_other_omission(self):
        history = self._history("I have not provided the site plan.", "I uploaded the cable list now.")
        answer = self._assert_followup(history, ("site plan",))
        self.assertNotIn("cable list", answer.casefold())

    def test_cross_turn_partial_supply_leaves_only_unsupplied_items(self):
        history = self._history(
            "I have not supplied the terrain sketch, cable list or inspection sheet.",
            "I uploaded the cable list now.",
        )
        answer = self._assert_followup(history, ("terrain sketch", "inspection sheet"))
        self.assertNotIn("cable list", answer.casefold())

    def test_cross_turn_supply_list_cancels_only_matching_items(self):
        history = self._history(
            "I have not supplied the terrain sketch, cable list or inspection sheet.",
            "I have provided the cable list and inspection sheet.",
        )
        self._assert_followup(history, ("terrain sketch",))

    def test_disjunctive_affirmative_supply_does_not_clear_both_missing_items(self):
        omission = "I have not supplied the terrain sketch or cable list."
        supplied = "I uploaded the terrain sketch or cable list now."
        self._assert_labels(extract_missing_inputs(omission + " " + supplied), ("terrain sketch", "cable list"))
        self._assert_followup(self._history(omission, supplied), ("terrain sketch", "cable list"))

    def test_disjunctive_passive_supply_list_cannot_clear_items_by_suffix_retry(self):
        omitted = "I have not supplied the terrain sketch, cable list or inspection sheet."
        supplied = "The terrain sketch or cable list, inspection sheet are attached now."
        expected = ("terrain sketch", "cable list", "inspection sheet")
        self._assert_labels(extract_missing_inputs(omitted + " " + supplied), expected)
        self._assert_followup(self._history(omitted, supplied), expected)

    def test_cross_turn_new_omission_after_supply_is_not_cancelled(self):
        history = self._history(
            "I have not supplied the site plan.", "I uploaded the site plan now.",
            "I have not supplied the site plan.",
        )
        self._assert_followup(history, ("site plan",))

    def test_cross_turn_independent_missing_items_accumulate(self):
        history = self._history("I have not supplied the terrain sketch.", "I have not supplied the cable list.")
        self._assert_followup(history, ("terrain sketch", "cable list"))

    def test_current_user_supply_resolves_history_state(self):
        history = self._history("I have not supplied the terrain sketch or cable list.")
        state = resolve_missing_inputs(history, "I have sent the terrain sketch now.")
        self._assert_labels(state, ("cable list",))

    def test_assistant_supply_never_corrects_user_omission(self):
        history = self._history("I have not supplied the terrain sketch.")
        history.append({"role": "assistant", "content": "I uploaded the terrain sketch now."})
        self._assert_followup(history, ("terrain sketch",))

    def test_assistant_omission_never_creates_missing_state(self):
        history = [{"role": "assistant", "content": "I have not supplied the terrain sketch."}]
        self._assert_followup(history, ())

    def test_assistant_partial_supply_does_not_reduce_user_list(self):
        history = self._history("I have not supplied the terrain sketch or cable list.")
        history.append({"role": "assistant", "content": "The cable list is attached now."})
        self._assert_followup(history, ("terrain sketch", "cable list"))

    def test_object_records_preserve_role_authority_and_resolution(self):
        history = [
            SimpleNamespace(role="user", content="I have not supplied the terrain sketch or cable list."),
            SimpleNamespace(role="assistant", content="I uploaded the terrain sketch."),
            SimpleNamespace(role="user", content="I uploaded the cable list now."),
        ]
        self._assert_followup(history, ("terrain sketch",))

    def test_article_case_and_whitespace_normalization_resolves_same_identity(self):
        history = self._history("I have not provided the SITE PLAN.", "I uploaded a site   plan now.")
        self._assert_followup(history, ())

    def test_user_possessive_normalization_resolves_same_identity(self):
        history = self._history("I have not provided my terrain sketch.", "I uploaded my terrain sketch now.")
        self._assert_followup(history, ())

    def test_different_user_owner_does_not_resolve_missing_item(self):
        omission = "I have not provided my terrain sketch."
        supplied = "I uploaded your terrain sketch now."
        self._assert_labels(extract_missing_inputs(omission + " " + supplied), ("your terrain sketch",))
        self._assert_followup(self._history(omission, supplied), ("your terrain sketch",))

    def test_unicode_normalization_resolves_same_identity(self):
        omitted = unicodedata.normalize("NFD", "I have not provided the café layout.")
        history = self._history(omitted, "I uploaded the CAFÉ layout now.")
        self._assert_followup(history, ())

    def test_filename_supply_resolves_exact_label_only(self):
        history = self._history(
            "I have not uploaded sensor.csv or cable-map.svg yet 🙂.",
            "I uploaded sensor.csv now.",
        )
        answer = self._assert_followup(history, ("cable-map.svg",))
        self.assertNotIn("sensor.csv", answer)
        self.assertNotIn("🙂", answer)

    def test_similar_but_distinct_labels_are_not_synonymized(self):
        history = self._history("I have not uploaded sensor-old.csv.", "I uploaded sensor.csv now.")
        self._assert_followup(history, ("sensor-old.csv",))

    def test_substring_or_extension_similarity_never_resolves_item_identity(self):
        for missing, supplied in (
            ("terrain sketch", "terrain sketch appendix"),
            ("terrain sketch appendix", "terrain sketch"),
            ("calibration.csv", "calibration.json"),
        ):
            with self.subTest(missing=missing, supplied=supplied):
                history = self._history("I have not provided the " + missing + ".",
                                        "I uploaded the " + supplied + " now.")
                self._assert_followup(history, (missing,))

    def test_itemless_supply_does_not_fabricate_correction(self):
        for supplied in ("I uploaded now.", "It is available now.", "The files are attached now."):
            with self.subTest(supplied=supplied):
                history = self._history("I have not provided the terrain sketch or cable list.", supplied)
                self._assert_followup(history, ("terrain sketch", "cable list"))

    def test_ambiguous_same_turn_pronoun_does_not_clear_multiple_omissions(self):
        for suffix in ("it is attached now", "they are attached now", "I uploaded it now"):
            with self.subTest(suffix=suffix):
                user = "I have not provided the terrain sketch or cable list, but " + suffix + "."
                self._assert_labels(extract_missing_inputs(user), ("terrain sketch", "cable list"))

    def test_separate_turn_pronoun_does_not_resolve_even_singleton_without_named_identity(self):
        history = self._history("I have not provided the terrain sketch.", "It is attached now.")
        self._assert_followup(history, ("terrain sketch",))

    def test_quoted_supply_has_no_current_user_authority(self):
        history = self._history(
            "I have not provided the terrain sketch.",
            'A colleague said "I uploaded the terrain sketch now."',
        )
        self._assert_followup(history, ("terrain sketch",))

    def test_conditional_future_and_question_supply_do_not_correct_absence(self):
        for supplied in (
            "If I uploaded the terrain sketch, you could assess it.",
            "I will upload the terrain sketch tomorrow.",
            "Did I upload the terrain sketch?",
            "I have uploaded the terrain sketch?",
        ):
            with self.subTest(supplied=supplied):
                history = self._history("I have not provided the terrain sketch.", supplied)
                self._assert_followup(history, ("terrain sketch",))

    def test_negated_supply_does_not_correct_absence(self):
        history = self._history("I have not provided the terrain sketch.", "I have not uploaded the terrain sketch yet.")
        self._assert_followup(history, ("terrain sketch",))

    def test_supply_does_not_create_new_missing_requirement(self):
        history = self._history("I uploaded the cable list now.")
        self._assert_followup(history, ())

    def test_external_availability_does_not_mean_material_was_supplied_to_core(self):
        for available in (
            "The terrain sketch is available from the archive.",
            "The terrain sketch is available at the exhibition.",
        ):
            with self.subTest(available=available):
                history = self._history("I have not provided the terrain sketch.", available)
                self._assert_followup(history, ("terrain sketch",))

    def test_strict_candidate_list_parser_does_not_gain_ingress_cleanup(self):
        for candidate_tail in (
            "the terrain sketch, but the capacity is 318 litres",
            "the terrain sketch, the cable list is attached now",
            "the terrain sketch or cable list yet 🙂",
            "the terrain sketch, I uploaded the cable list now",
        ):
            with self.subTest(candidate_tail=candidate_tail):
                self.assertIsNone(parse_missing_item_list(candidate_tail))

    def test_resolved_same_turn_evidence_contains_only_current_missing_items(self):
        user = "I have not supplied the terrain sketch or cable list, but the cable list is attached now."
        candidate = _candidate(user)
        availability = next(evidence.data["availability"] for evidence in candidate.evidence.evidence
                            if evidence.kind == EvidenceKind.UNCERTAINTY
                            and evidence.data.get("availability", {}).get("kind") == "missing_input")
        self.assertEqual(_labels(SimpleNamespace(items=availability["missing_inputs"])), ("terrain sketch",))
        self.assertTrue(any(item.kind == EvidenceKind.CURRENT_USER_TURN and item.claim == user
                            for item in candidate.evidence.evidence))
        self.assertEqual(CoreAcceptanceEvaluator().evaluate(candidate).status, AcceptanceStatus.ACCEPTED)

    def test_correction_is_not_inferred_from_candidate_prose(self):
        user = "I have not provided the terrain sketch or cable list."
        bounded = _candidate(user)
        invented = _candidate(user, "The cable list is attached now. The terrain sketch has 318 lines.")
        self.assertEqual(invented.evidence, bounded.evidence)
        self.assertNotEqual(CoreAcceptanceEvaluator().evaluate(invented).status, AcceptanceStatus.ACCEPTED)

    def test_no_stale_omission_candidate_authority_after_same_item_supply(self):
        user = "I have not provided the terrain sketch. I uploaded the terrain sketch now."
        candidate = _candidate(user, "I cannot determine that because you have not given me the terrain sketch.")
        self.assertNotEqual(CoreAcceptanceEvaluator().evaluate(candidate).status, AcceptanceStatus.ACCEPTED)

    def test_resolved_item_semantics_are_origin_and_path_invariant(self):
        user = "I have not supplied the terrain sketch or cable list, but the cable list is attached now."
        valid = _candidate(user)
        for answer, outcome in (
            (valid.text, "accepted"),
            ("I cannot determine that because you have not given me the cable list.", "replaced"),
        ):
            baseline = None
            for origin in CandidateOrigin:
                for path in ("neutral.state", "neutral.other"):
                    with self.subTest(origin=origin, path=path, outcome=outcome):
                        result = publish_limitation_response(
                            text=answer, contract=_contract(), user_input=user,
                            path=path, origin=origin, emit=False,
                        )
                        current = (result.text, result.record.decision, result.record.replacement_decision,
                                   result.record.outcome, result.record.replacement_used)
                        if baseline is None:
                            baseline = current
                        self.assertEqual(current, baseline)
                        self.assertEqual(result.record.outcome, outcome)

    def test_real_missing_input_branch_preserves_valid_resolved_tailored_candidate(self):
        records = []
        run, namespace = _provider_branch("core_epistemic_mode == 'insufficient_user_context'", records, publish_tail=True)
        user = "I have not supplied the terrain sketch or cable list, but the cable list is attached now."
        namespace["user_input"] = user
        expected = build_insufficient_user_context_fallback(user)
        result = run()
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1]["content"], expected)
        self.assertIn("terrain sketch", expected)
        self.assertNotIn("cable list", expected)
        self.assertEqual(records[0].record.decision.status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(records[0].record.outcome, "accepted")
        self.assertFalse(records[0].record.replacement_used)

    def test_real_stale_or_fabricated_candidate_uses_existing_bounded_replacement(self):
        user = "I have not supplied the terrain sketch or cable list, but the cable list is attached now."
        for invalid in (
            "I cannot determine that because you have not given me the cable list.",
            "The exact capacity is 318 litres.",
        ):
            with self.subTest(invalid=invalid):
                records, candidates = [], []
                run, namespace = _provider_branch("core_epistemic_mode == 'insufficient_user_context'", records, publish_tail=True)
                namespace["user_input"] = user
                namespace["build_insufficient_user_context_fallback"] = lambda value: invalid
                evaluate = CoreAcceptanceEvaluator.evaluate

                def capture(evaluator, candidate):
                    candidates.append(candidate)
                    return evaluate(evaluator, candidate)

                with patch.object(CoreAcceptanceEvaluator, "evaluate", capture):
                    result = run()
                self.assertNotEqual(result[0], invalid)
                self.assertEqual(result[1][-1]["content"], result[0])
                self.assertEqual(records[0].record.outcome, "replaced")
                self.assertEqual(records[0].record.replacement_decision.status, AcceptanceStatus.ACCEPTED)
                self.assertEqual(len(candidates), 2)
                self.assertEqual(candidates[0].evidence, candidates[1].evidence)
                self.assertEqual(candidates[0].contract, candidates[1].contract)


if __name__ == "__main__":
    unittest.main()
