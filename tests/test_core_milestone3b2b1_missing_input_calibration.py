"""User-authored missing-input lists survive bounded acceptance/publication.

These cases use neutral materials and real Core factories. Provider fragments
are copied from the actual production AST, with inert surrounding setup; the
evaluator and publication boundary execute normally.
"""
from __future__ import annotations

import re
import sys
import unicodedata
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from core.acceptance_evaluator import CoreAcceptanceEvaluator
from core.acceptance_publication import publish_limitation_response
from core.acceptance_shadow import _limitation_evidence
from core.answer_candidate import AcceptanceStatus, AnswerCandidate, CandidateOrigin
from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    _extract_explicit_missing_items,
    build_insufficient_user_context_fallback,
    build_user_context_reasoning_fallback,
)
from core.evidence import Evidence, EvidenceKind, EvidenceStatus
from core.missing_inputs import extract_missing_inputs, parse_missing_item_list

from test_core_milestone3b2b_bounded_publication import _provider_branch


def _contract(subject=None):
    return AnswerContractRuntime(
        intent="factual_question", authority="user_context", epistemic_mode="insufficient_user_context",
        subject=subject, allow_follow_up_question=True,
    )


def _labels(items):
    return tuple(re.sub(r"^(?:the|a|an)\s+", "", " ".join(item.casefold().split()).strip("\"'"))
                 for item in items)


def _candidate(user_input, text=None, *, subject=None, conversation=()):
    runtime = _contract(subject)
    evidence = _limitation_evidence(
        contract=runtime, user_input=user_input, conversation=conversation, user_history=(),
        failure_reason=None, research_result=None,
    )
    return AnswerCandidate(
        text=build_insufficient_user_context_fallback(user_input) if text is None else text,
        origin=CandidateOrigin.DETERMINISTIC_FALLBACK, contract=runtime, evidence=evidence,
    )


class MissingInputCalibrationTests(unittest.TestCase):
    def _assert_origins(self, candidate, accepted):
        evaluator = CoreAcceptanceEvaluator()
        baseline = evaluator.evaluate(candidate)
        self.assertEqual(baseline.status is AcceptanceStatus.ACCEPTED, accepted, baseline)
        for origin in CandidateOrigin:
            self.assertEqual(evaluator.evaluate(candidate.with_origin(origin)), baseline)
        return baseline

    def _assert_extracted(self, text, expected):
        parsed = extract_missing_inputs(text)
        self.assertIsNotNone(parsed)
        self.assertEqual(_labels(parsed.items), tuple(expected))
        self.assertEqual(_extract_explicit_missing_items(text), parsed.description)
        return parsed

    def test_singular_present_perfect_omission_verbs_are_user_bound(self):
        for verb in ("attached", "uploaded", "provided", "sent", "given"):
            with self.subTest(verb=verb):
                recipient = " you" if verb in {"sent", "given"} else ""
                text = "Please inspect the plan. I have not " + verb + recipient + " the blueprint."
                self._assert_extracted(text, ("blueprint",))
                self._assert_origins(_candidate(text), True)

    def test_explicit_told_user_context_is_preserved(self):
        text = "Please assess the plan. I have not told you the tolerances."
        self._assert_extracted(text, ("tolerances",))
        self._assert_origins(_candidate(text), True)

    def test_simple_past_omission_verbs_preserve_the_named_material(self):
        for verb in ("attach", "upload", "provide", "send", "give"):
            with self.subTest(verb=verb):
                recipient = " you" if verb in {"send", "give"} else ""
                text = "Please inspect the plan. I did not " + verb + recipient + " the blueprint."
                self._assert_extracted(text, ("blueprint",))
                self._assert_origins(_candidate(text), True)

    def test_contraction_case_and_typographic_apostrophe_do_not_change_items(self):
        for phrase in ("I haven't provided", "I haven’t provided", "I HAVENT PROVIDED"):
            with self.subTest(phrase=phrase):
                text = phrase + " the blueprint, parts list or tolerances."
                self._assert_extracted(text, ("blueprint", "parts list", "tolerances"))
                self._assert_origins(_candidate(text), True)

    def test_comma_or_list_is_not_split_into_factual_clauses(self):
        text = "Please assess the plan. I have not provided the blueprint, parts list or tolerances."
        self._assert_extracted(text, ("blueprint", "parts list", "tolerances"))
        self._assert_origins(_candidate(text), True)

    def test_comma_and_list_is_not_split_into_factual_clauses(self):
        text = "Please assess the plan. I have not provided the blueprint, parts list, and tolerances."
        self._assert_extracted(text, ("blueprint", "parts list", "tolerances"))
        self._assert_origins(_candidate(text), True)

    def test_binary_nominal_and_or_lists_have_the_same_authority(self):
        for connector in ("and", "or"):
            with self.subTest(connector=connector):
                text = "I have not supplied the mosaic plan " + connector + " the frame sketch."
                self._assert_extracted(text, ("mosaic plan", "frame sketch"))
                self._assert_origins(_candidate(text), True)

    def test_case_and_terminal_punctuation_preserve_nominal_labels(self):
        for terminal in (".", "!", "..."):
            with self.subTest(terminal=terminal):
                text = "I have not provided the BLUEPRINT, Parts List, or TOLERANCES" + terminal
                self._assert_extracted(text, ("blueprint", "parts list", "tolerances"))
                self._assert_origins(_candidate(text), True)

    def test_numbered_user_material_labels_do_not_establish_numerical_answers(self):
        text = "I have not provided figure 3, draft B or revision notes."
        self._assert_extracted(text, ("figure 3", "draft b", "revision notes"))
        self._assert_origins(_candidate(text), True)

    def test_nominal_before_after_labels_are_not_causal_assertions(self):
        text = "I have not provided the before-photo or after-photo."
        self._assert_extracted(text, ("before-photo", "after-photo"))
        self._assert_origins(_candidate(text), True)

    def test_user_possessive_perspective_is_bound_without_new_items(self):
        text = "I have not sent you my blueprint, my parts list or my tolerances."
        parsed = extract_missing_inputs(text)
        self.assertEqual(_labels(parsed.items), ("your blueprint", "your parts list", "your tolerances"))
        self._assert_origins(_candidate(text), True)

    def test_trailing_yet_is_not_part_of_a_missing_item(self):
        text = "I have not provided the blueprint, parts list or tolerances yet."
        self._assert_extracted(text, ("blueprint", "parts list", "tolerances"))
        self._assert_origins(_candidate(text), True)

    def test_trailing_informal_discourse_does_not_become_material(self):
        for suffix in ("yet lol", "yet haha", "yet tbh"):
            with self.subTest(suffix=suffix):
                text = "I have not provided the blueprint, parts list or tolerances " + suffix + "."
                self._assert_extracted(text, ("blueprint", "parts list", "tolerances"))
                self._assert_origins(_candidate(text), True)

    def test_trailing_emoji_does_not_become_material(self):
        for suffix in ("yet 🙂", "yet 😅", "🙂"):
            with self.subTest(suffix=suffix):
                text = "I have not provided the blueprint, parts list or tolerances " + suffix + "."
                self._assert_extracted(text, ("blueprint", "parts list", "tolerances"))
                self._assert_origins(_candidate(text), True)

    def test_followup_sentence_is_not_promoted_to_missing_input(self):
        text = "I have not provided the blueprint, parts list or tolerances. Can you use the previous draft instead?"
        parsed = self._assert_extracted(text, ("blueprint", "parts list", "tolerances"))
        self.assertNotIn("previous", parsed.description.casefold())
        self._assert_origins(_candidate(text), True)

    def test_followup_question_after_comma_is_not_a_nominal_item(self):
        text = "I have not provided the blueprint, parts list or tolerances, can you use the previous draft instead?"
        parsed = self._assert_extracted(text, ("blueprint", "parts list", "tolerances"))
        self.assertNotIn("previous", parsed.description.casefold())
        self._assert_origins(_candidate(text), True)

    def test_real_followup_builder_uses_clean_prior_user_materials(self):
        for suffix in ("yet lol.", "yet 🙂.", ", can you use the previous draft instead?"):
            with self.subTest(suffix=suffix):
                user = "I have not provided the blueprint, parts list or tolerances " + suffix
                parsed = self._assert_extracted(user, ("blueprint", "parts list", "tolerances"))
                history = [
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": "I have not provided the maintenance log."},
                ]
                answer = build_user_context_reasoning_fallback("What should I send?", history)
                self.assertEqual(answer, "Send me " + parsed.description + ". That's what I need to check it properly.")
                for contamination in ("yet", "lol", "🙂", "previous", "maintenance"):
                    self.assertNotIn(contamination, answer.casefold())

    def test_real_followup_builder_ignores_assistant_only_omissions(self):
        history = [{"role": "assistant", "content": "I have not provided the maintenance log, serial record or service sketch yet lol."}]
        answer = build_user_context_reasoning_fallback("What should I send?", history)
        for material in ("maintenance log", "serial record", "service sketch", "lol"):
            self.assertNotIn(material, answer.casefold())

    def test_independent_assertion_is_not_an_omitted_material_description(self):
        for suffix in ("but the machine is amber", "and the machine is amber", "because the machine is amber"):
            with self.subTest(suffix=suffix):
                text = "I have not provided the blueprint, parts list or tolerances, " + suffix + "."
                parsed = self._assert_extracted(text, ("blueprint", "parts list", "tolerances"))
                self.assertNotIn("machine", parsed.description.casefold())
                self._assert_origins(_candidate(text), True)

    def test_typed_availability_contains_atomic_user_items_and_original_user_evidence(self):
        text = "I have not provided the BLUEPRINT, Parts List or TOLERANCES yet 🙂."
        parsed = extract_missing_inputs(text)
        candidate = _candidate(text)
        state = next(item for item in candidate.evidence.evidence if item.kind == EvidenceKind.UNCERTAINTY
                     and item.data.get("availability", {}).get("kind") == "missing_input")
        self.assertEqual(state.data["availability"]["missing_inputs"], parsed.items)
        self.assertEqual(state.status, EvidenceStatus.UNAVAILABLE)
        self.assertEqual(state.authority_scope, "evidence_availability")
        self.assertEqual(state.provenance, "core_evidence_availability")
        self.assertTrue(any(item.kind == EvidenceKind.CURRENT_USER_TURN and item.claim == text
                            for item in candidate.evidence.evidence))

    def test_candidate_answer_never_supplies_canonical_missing_items(self):
        text = "I have not provided the blueprint or parts list."
        first = _candidate(text)
        second = _candidate(text, "The hidden schematic has 441 components.")
        self.assertEqual(first.evidence, second.evidence)
        self._assert_origins(second, False)

    def test_detailed_truthful_list_renderings_complete_the_same_contract(self):
        user = "I have not provided the blueprint, parts list or tolerances."
        for answer in (
            "The blueprint, parts list and tolerances are unavailable. Please provide the blueprint, parts list or tolerances.",
            "I cannot assess the blueprint, parts list or tolerances. Please supply the blueprint, parts list or tolerances.",
            "I cannot determine that until you provide the blueprint, parts list or tolerances.",
        ):
            with self.subTest(answer=answer):
                self._assert_origins(_candidate(user, answer), True)

    def test_filename_labels_remain_opaque_missing_material_names(self):
        user = "I have not uploaded plan.pdf, notes_v3.md or figure-4.svg yet."
        parsed = self._assert_extracted(user, ("plan.pdf", "notes_v3.md", "figure-4.svg"))
        self.assertNotIn("yet", parsed.description.casefold())
        self._assert_origins(_candidate(user), True)

    def test_filename_labels_do_not_authorize_missing_contents_or_exact_answers(self):
        user = "I have not uploaded plan.pdf, notes_v3.md or figure-4.svg yet."
        valid = _candidate(user)
        for answer in (
            "The plan.pdf contains four layers.",
            valid.text + " The exact capacity is 441 units.",
            "I cannot determine that because you have not given me plan.pdf, notes_v3.md or figure-4.svg, but the capacity is 441 units.",
        ):
            with self.subTest(answer=answer):
                self._assert_origins(replace(valid, text=answer), False)

    def test_repeated_filename_list_occurrence_does_not_hide_a_later_assertion(self):
        user = "I have not uploaded plan.pdf, notes_v3.md or figure-4.svg."
        valid = _candidate(user)
        for suffix in (
            " The plan.pdf contains 441 measurements.",
            " The plan.pdf, notes_v3.md or figure-4.svg contain 441 instructions.",
        ):
            with self.subTest(suffix=suffix):
                self._assert_origins(replace(valid, text=valid.text + suffix), False)

    def test_unicode_normalization_preserves_labels_and_original_user_evidence(self):
        user = unicodedata.normalize("NFD", "I have not provided the café plan or naïve sketch yet.")
        parsed = self._assert_extracted(user, ("café plan", "naïve sketch"))
        self.assertEqual(parsed.description, unicodedata.normalize("NFC", parsed.description))
        candidate = _candidate(user)
        self.assertTrue(any(item.kind == EvidenceKind.CURRENT_USER_TURN and item.claim == user
                            for item in candidate.evidence.evidence))
        self._assert_origins(candidate, True)

    def test_added_undeclared_missing_item_has_no_authority(self):
        text = "I have not provided the blueprint or parts list."
        self._assert_origins(_candidate(text,
            "I cannot determine that because you have not given me the blueprint, parts list or maintenance log."), False)

    def test_missing_material_content_cannot_be_invented(self):
        text = "I have not provided the blueprint, parts list or tolerances."
        self._assert_origins(_candidate(text, "The missing blueprint contains twelve sections."), False)

    def test_valid_list_caveat_cannot_hide_an_exact_answer(self):
        text = "I have not provided the blueprint, parts list or tolerances."
        candidate = _candidate(text)
        self._assert_origins(replace(candidate, text=candidate.text + " The exact capacity is 441 units."), False)

    def test_same_sentence_omission_list_cannot_hide_a_factual_suffix(self):
        text = "I have not provided the blueprint, parts list or tolerances."
        self._assert_origins(_candidate(text,
            "I cannot determine that because you have not given me the blueprint, parts list or tolerances, but the capacity is 441 units."), False)

    def test_strict_candidate_list_parser_does_not_accept_assertive_tail(self):
        for text in ("the blueprint, parts list or tolerances, but the capacity is 441 units",
                     "the blueprint and the machine is amber", "the blueprint, can you verify the capacity"):
            with self.subTest(text=text):
                self.assertIsNone(parse_missing_item_list(text))

    def test_generic_input_words_do_not_hide_assertions_when_clauses_are_joined(self):
        user = "I have not provided the input."
        for answer in (
            "I cannot determine the answer. Please provide the input, the information is available.",
            "I cannot inspect the input, the information is available.",
            "I cannot determine the answer until you provide the input, the information is available.",
        ):
            with self.subTest(answer=answer):
                self._assert_origins(_candidate(user, answer), False)

    def test_access_unavailable_does_not_prove_user_omission(self):
        text = "I have provided the blueprint and parts list."
        candidate = _candidate(text, "I cannot access the blueprint from the supplied context.", subject="the blueprint")
        self._assert_origins(candidate, True)
        self._assert_origins(replace(candidate, text="I cannot determine that because you have not given me the blueprint."), False)
        self.assertIsNone(extract_missing_inputs(text))

    def test_assistant_history_cannot_supply_missing_item_authority(self):
        history = [{"role": "assistant", "content": "I have not provided the maintenance log."}]
        candidate = _candidate("I have not provided the blueprint.",
                               "I cannot determine that because you have not given me the maintenance log.",
                               conversation=history)
        self._assert_origins(candidate, False)
        self.assertFalse(any(item.claim == history[0]["content"] for item in candidate.evidence.authoritative_evidence))

    def test_rejected_source_does_not_expand_user_authored_missing_items(self):
        user = "I have not provided the blueprint."
        candidate = _candidate(user,
            "I cannot determine that because you have not given me the blueprint or maintenance log.")
        for status in (EvidenceStatus.REJECTED, EvidenceStatus.UNAVAILABLE):
            with self.subTest(status=status):
                source = Evidence(
                    claim="The user has not supplied the maintenance log.",
                    provenance="public_retrieval", confidence="none",
                    kind=EvidenceKind.PUBLIC_SOURCE, status=status,
                    authority_scope="public_factual", quality_eligible=False,
                    source_id="neutral.reference", evidence_id="neutral.unusable",
                )
                bundle = replace(candidate.evidence, evidence=tuple(candidate.evidence.evidence) + (source,)).snapshot()
                self._assert_origins(replace(candidate, evidence=bundle), False)
                self.assertFalse(any(item.evidence_id == source.evidence_id for item in bundle.authoritative_evidence))

    def test_quoted_assistant_omission_is_not_a_current_user_omission(self):
        self.assertIsNone(extract_missing_inputs('A prior assistant said "I have not provided the blueprint."'))

    def test_provided_or_unspecified_material_does_not_create_explicit_omission(self):
        for text in ("I have provided the blueprint.", "Please inspect the blueprint.", "The blueprint cannot be accessed."):
            with self.subTest(text=text):
                self.assertIsNone(extract_missing_inputs(text))

    def test_qualified_or_conditional_supply_does_not_prove_whole_list_absence(self):
        for user in (
            "If I have not provided the blueprint, please ask me for it.",
            "I have not provided both the blueprint and parts list.",
            "I have not provided only the blueprint.",
            "I have not provided either the blueprint or parts list, if that is required.",
        ):
            with self.subTest(user=user):
                self.assertIsNone(extract_missing_inputs(user))
                self._assert_origins(_candidate(user,
                    "I cannot determine that because you have not given me the blueprint."), False)

    def test_later_explicit_supply_cancels_the_stale_omission(self):
        for user in (
            "I have not attached the route map yet, but the route map is attached now.",
            "I have not attached the route map yet, it is attached now.",
            "I have not attached the route map yet. I have attached the route map now.",
        ):
            with self.subTest(user=user):
                self.assertIsNone(extract_missing_inputs(user))
                self._assert_origins(_candidate(user,
                    "I cannot determine that because you have not given me the route map."), False)

    def test_real_missing_fallback_publishes_clean_user_tailored_answer_unchanged(self):
        for prompt in ("I have not provided the blueprint, parts list or tolerances yet 🙂.",
                       "I have not provided the mosaic plan and frame sketch.",
                       "I have not uploaded plan.pdf, notes_v3.md or figure-4.svg yet."):
            with self.subTest(prompt=prompt):
                records = []
                run, namespace = _provider_branch("core_epistemic_mode == 'insufficient_user_context'", records, publish_tail=True)
                namespace["user_input"] = prompt
                expected = build_insufficient_user_context_fallback(prompt)
                returned = run()
                self.assertEqual(returned[0], expected)
                self.assertEqual(returned[1][-1]["content"], expected)
                self.assertEqual(records[0].record.decision.status, AcceptanceStatus.ACCEPTED)
                self.assertEqual(records[0].record.outcome, "accepted")
                self.assertFalse(records[0].record.replacement_used)
                self.assertEqual(len(records), 1)

    def test_real_invalid_missing_candidate_is_withheld_and_boundedly_replaced(self):
        records = []
        run, namespace = _provider_branch("core_epistemic_mode == 'insufficient_user_context'", records, publish_tail=True)
        namespace["user_input"] = "I have not provided the blueprint, parts list or tolerances."
        invalid = "The exact capacity is 441 units."
        namespace["build_insufficient_user_context_fallback"] = lambda value: invalid
        candidates = []
        real = CoreAcceptanceEvaluator.evaluate

        def capture(evaluator, candidate):
            candidates.append(candidate)
            return real(evaluator, candidate)

        with patch.object(CoreAcceptanceEvaluator, "evaluate", capture):
            returned = run()
        self.assertNotEqual(returned[0], invalid)
        self.assertEqual(returned[1][-1]["content"], returned[0])
        self.assertEqual(records[0].record.outcome, "replaced")
        self.assertEqual(records[0].record.replacement_decision.status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].contract, candidates[1].contract)
        self.assertEqual(candidates[0].evidence, candidates[1].evidence)

    def test_real_provider_withholds_an_assertion_hidden_after_a_generic_request(self):
        records = []
        run, namespace = _provider_branch("core_epistemic_mode == 'insufficient_user_context'", records, publish_tail=True)
        namespace["user_input"] = "I have not provided the input."
        invalid = "I cannot determine the answer. Please provide the input, the information is available."
        namespace["build_insufficient_user_context_fallback"] = lambda value: invalid
        returned = run()
        self.assertNotEqual(returned[0], invalid)
        self.assertEqual(returned[1][-1]["content"], returned[0])
        self.assertEqual(records[0].record.outcome, "replaced")
        self.assertEqual(records[0].record.replacement_decision.status, AcceptanceStatus.ACCEPTED)

    def test_origin_and_static_path_do_not_change_list_acceptance_or_publication(self):
        user = "I have not provided the blueprint, parts list or tolerances yet 🙂."
        for answer, outcome in (
            (build_insufficient_user_context_fallback(user), "accepted"),
            ("I cannot determine that because you have not given me the blueprint, parts list or tolerances, but the capacity is 441 units.", "replaced"),
        ):
            expected = None
            for origin in CandidateOrigin:
                for path in ("neutral.input", "neutral.other"):
                    with self.subTest(origin=origin, path=path, outcome=outcome):
                        result = publish_limitation_response(
                            text=answer, contract=_contract(), user_input=user,
                            path=path, origin=origin, emit=False,
                        )
                        actual = (result.text, result.record.decision, result.record.replacement_decision,
                                  result.record.outcome, result.record.replacement_used)
                        if expected is None:
                            expected = actual
                        self.assertEqual(actual, expected)
                        self.assertEqual(result.record.outcome, outcome)


if __name__ == "__main__":
    unittest.main()
