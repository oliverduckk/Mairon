"""Neutral target-binding checks through the complete legacy public producer.

The actual direct-conversation function, packet builder, sentence verifier and
supported-subset completion check execute offline. Unrelated services are inert.
No common acceptance verdict, tool, live research or additional loop is used.
"""
from __future__ import annotations

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

from core.answer_candidate import CandidateOrigin
from test_core_milestone3b3a_public_shadow_integration import contract, provider, research
from research.public_factual_grounding import (
    _split_draft_sentences,
    build_failed_public_factual_fallback,
    build_public_factual_generation_instruction,
    build_supported_current_lookup_fallback,
    requires_public_factual_salvage_completion,
    verify_public_factual_draft,
    verify_public_factual_salvage_completion,
)
from research.public_factual_research import (
    actual_read_url,
    build_public_factual_authority_context,
)
from research.public_claim_obligations import build_public_claim_obligations

USER = "Why does phased gating cause stripe noise?"
GOOD = ("Phased gating changes timing in the release stage, which can make stripe noise "
        "appear because neighbouring sections receive unequal intervals.")
ADVICE = "Try changing the release limit."
LIMITATION = "I cannot verify why phased gating causes stripe noise from the available evidence."
NUMERIC = "When values jump from 12 to 31 to 18, the system keeps adjusting."
ONLY_MECHANISM = "Phased gating changes timing in the release stage."
OTHER_MECHANISM = "Cache sweeping produces stripe noise because buffer entries expire."
UNRELATED = "The service delays export because its queue is full."
UNSUPPORTED = "Phased gating causes stripe noise because the module is permanently damaged."
PARAPHRASE = ("Segmented release alters the timing, which can produce striped interference "
              "because neighbouring sections receive unequal intervals.")
PRONOUNS = ("Phased gating changes timing. "
            "That mode can produce stripe noise because neighbouring sections receive unequal intervals.")
AMBIGUOUS = "It produces that because the interval changes."
ALIAS_BODY = (GOOD + " Phased gating is also called segmented release. "
              "Stripe noise is also called striped interference. " + PARAPHRASE)
BODY = (GOOD + " " + ADVICE + " " + NUMERIC + " " + ONLY_MECHANISM + " "
        + OTHER_MECHANISM + " " + UNRELATED + " "
        + ALIAS_BODY + " "
        + PRONOUNS + " " + AMBIGUOUS)
MISSING = object()


def target(candidate=GOOD, *, outcome="factual_explanation", bound=True,
           mechanism="Phased gating", effect="stripe noise", answer=None,
           source_quote=GOOD):
    """One scripted scoped assessment; literal witnesses stay source-owned."""
    if outcome == "bounded_limitation":
        return [{"index": 1, "outcome": outcome, "mechanism_bound": True,
                 "effect_bound": True, "relationship_answered": True,
                 "mechanism_quote": "phased gating", "effect_quote": "stripe noise",
                 "answer_quote": candidate, "source_id": None, "source_quote": None}]
    if outcome == "incomplete":
        return [{"index": 1, "outcome": outcome, "mechanism_bound": False,
                 "effect_bound": False, "relationship_answered": False,
                 "mechanism_quote": None, "effect_quote": None, "answer_quote": None,
                 "source_id": None, "source_quote": None}]
    return [{"index": 1, "outcome": outcome, "mechanism_bound": bound,
             "effect_bound": bound, "relationship_answered": bound,
             "mechanism_quote": mechanism, "effect_quote": effect,
             "answer_quote": candidate if answer is None else answer,
             "source_id": "S1", "source_quote": source_quote}]


def verification(candidate, *, assessments=MISSING, statuses=None, quote=None):
    sentences = _split_draft_sentences(candidate)
    statuses = list(statuses) if statuses is not None else [True] * len(sentences)
    value = {"supported": all(statuses),
             "unsupported_claims": [] if all(statuses) else ["Unsupported detail"],
             "sentence_assessments": [{"index": index, "supported": status}
                                      for index, status in enumerate(statuses, 1)]}
    obligations = build_public_claim_obligations(sentences)
    if obligations:
        value["claim_assessments"] = [
            {"index": item["index"], "supported": statuses[item["sentence_index"] - 1],
             "source_id": "S1" if statuses[item["sentence_index"] - 1] else None,
             "source_quote": (quote or item["candidate_span"]) if statuses[item["sentence_index"] - 1] else None}
            for item in obligations
        ]
    if assessments is not MISSING:
        value["explanation_target_assessments"] = copy.deepcopy(assessments)
    return value


def completion(candidate=GOOD, *, assessments=MISSING, completed=True,
               outcome="factual_answer"):
    value = {"completed": completed, "outcome": outcome,
             "request_fulfilled": completed, "required_claim_assessments": [],
             "violations": [] if completed else ["incomplete_request"]}
    if assessments is not MISSING:
        value["explanation_target_assessments"] = copy.deepcopy(assessments)
    return value


class TargetClient:
    def __init__(self, drafts, verifications, completions=()):
        self.drafts = iter(drafts)
        self.verifications = iter(verifications)
        self.completions = iter(completions)
        self.calls = []
        self.generations = self.verifier_calls = self.completion_calls = 0

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        system = "\n".join(item["content"] for item in kwargs["messages"]
                           if item["role"] == "system")
        if "INTERNAL supported-subset answer-completion verifier" in system:
            self.completion_calls += 1
            value = next(self.completions)
            if isinstance(value, Exception):
                raise value
            content = json.dumps(value)
        elif "INTERNAL public-factual evidence verifier" in system:
            self.verifier_calls += 1
            content = json.dumps(next(self.verifications))
        else:
            self.generations += 1
            content = next(self.drafts)
        return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=[]),
                               done_reason="stop")


def run(client, current=USER, *, body=BODY, current_contract=None, observer=None,
        history=()):
    retained = copy.deepcopy(research())
    retained["query"] = retained["original_query"] = "phased gating stripe noise"
    retained["sources"][0]["title"] = "Release stage technical guide"
    retained["sources"][0]["read_result"]["content"] = body
    fn, namespace = provider(retained=retained)
    observations = []
    namespace.update({
        "build_public_factual_authority_context": build_public_factual_authority_context,
        "build_public_factual_generation_instruction": build_public_factual_generation_instruction,
        "actual_read_url": actual_read_url,
        "verify_public_factual_draft": verify_public_factual_draft,
        "should_verify_public_factual_salvage_completion": requires_public_factual_salvage_completion,
        "verify_public_factual_salvage_completion": verify_public_factual_salvage_completion,
        "build_supported_current_lookup_fallback": build_supported_current_lookup_fallback,
        "build_failed_public_factual_fallback": build_failed_public_factual_fallback,
        "observe_public_factual_response": observer or (lambda **kwargs: observations.append(kwargs)),
    })
    log = io.StringIO()
    with redirect_stdout(log):
        result = fn(client, current, list(history),
                    core_answer_contract=current_contract or contract())
    return result, observations, log.getvalue()


class PublicTargetBindingProductionTests(unittest.TestCase):
    def assert_published(self, result, expected, *withheld):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": expected})
        self.assertEqual(result[2:], (None, None))
        for text in withheld:
            self.assertNotIn(text, [item["content"] for item in result[1]])

    def retry(self, bad, *, bad_assessment=MISSING, bad_verdict=None):
        if bad_verdict is None:
            bad_verdict = verification(bad, assessments=bad_assessment)
        client = TargetClient([bad, GOOD], [bad_verdict, verification(GOOD, assessments=target())])
        result, observations, log = run(client)
        self.assert_published(result, GOOD, bad)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 0))
        self.assertEqual(len(client.calls), 4, "Target checks share the existing verifier call")
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["origin"], CandidateOrigin.RETRY)
        return client, log

    def test_targetless_numeric_adjacent_behaviour_cannot_publish(self):
        self.retry(NUMERIC + " " + ADVICE, bad_assessment=target(outcome="incomplete"))

    def test_global_positive_without_target_assessment_cannot_publish(self):
        self.retry(NUMERIC + " " + ADVICE)

    def test_missing_effect_cannot_complete_explanation(self):
        self.retry(ONLY_MECHANISM, bad_assessment=target(outcome="incomplete"))

    def test_effect_with_replacement_mechanism_cannot_complete_explanation(self):
        self.retry(OTHER_MECHANISM, bad_assessment=target(outcome="incomplete"))

    def test_unrelated_causal_sentence_is_not_requested_relationship(self):
        self.retry(UNRELATED, bad_assessment=target(outcome="incomplete"))

    def test_advice_only_positive_support_remains_incomplete(self):
        self.retry(ADVICE, bad_assessment=target(outcome="incomplete"))

    def test_empty_target_assessments_fail_closed(self):
        self.retry(NUMERIC, bad_assessment=[])

    def test_non_list_target_assessment_fails_closed(self):
        self.retry(NUMERIC, bad_assessment={"index": 1})

    def test_non_boolean_bound_field_fails_closed(self):
        malformed = target(NUMERIC)
        malformed[0]["mechanism_bound"] = "true"
        self.retry(NUMERIC, bad_assessment=malformed)

    def test_duplicate_target_assessment_fails_closed(self):
        malformed = target(NUMERIC)
        self.retry(NUMERIC, bad_assessment=malformed + malformed)

    def test_wrong_target_index_fails_closed(self):
        malformed = target(NUMERIC)
        malformed[0]["index"] = 2
        self.retry(NUMERIC, bad_assessment=malformed)

    def test_ambiguous_pronouns_cannot_establish_targets(self):
        self.retry(AMBIGUOUS, bad_assessment=target(outcome="incomplete"))

    def test_supported_bound_explanation_publishes_unchanged(self):
        client = TargetClient([GOOD], [verification(GOOD, assessments=target())])
        result, observations, _ = run(client)
        self.assert_published(result, GOOD)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (1, 1, 0))
        self.assertEqual(observations[0]["origin"], CandidateOrigin.GENERATED)

    def test_supported_explanation_with_optional_advice_publishes_unchanged(self):
        candidate = GOOD + " " + ADVICE
        client = TargetClient([candidate], [verification(candidate, assessments=target(answer=GOOD))])
        result, _, _ = run(client)
        self.assert_published(result, candidate)
        self.assertEqual(len(client.calls), 2)

    def test_source_established_alias_paraphrase_can_publish(self):
        annotation = target(PARAPHRASE, mechanism="Segmented release", effect="striped interference",
                            source_quote=ALIAS_BODY)
        client = TargetClient([PARAPHRASE], [verification(PARAPHRASE, assessments=annotation)])
        result, _, _ = run(client)
        self.assert_published(result, PARAPHRASE)
        self.assertEqual(client.generations, 1)

    def test_explicit_antecedents_allow_a_following_pronoun_explanation(self):
        annotation = target(PRONOUNS, mechanism="That mode",
                            answer="That mode can produce stripe noise because neighbouring sections receive unequal intervals.")
        client = TargetClient([PRONOUNS], [verification(PRONOUNS, assessments=annotation)])
        result, _, _ = run(client)
        self.assert_published(result, PRONOUNS)
        self.assertEqual(client.generations, 1)

    def test_truthful_bound_limitation_remains_available(self):
        client = TargetClient([LIMITATION], [verification(LIMITATION, assessments=target(LIMITATION, outcome="bounded_limitation"))])
        result, _, _ = run(client)
        self.assert_published(result, LIMITATION)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (1, 1, 0))

    def test_every_bounded_retry_requires_its_own_target_assessment(self):
        client = TargetClient([NUMERIC, UNRELATED], [
            verification(NUMERIC, assessments=target(outcome="incomplete")),
            verification(UNRELATED, assessments=target(outcome="incomplete")),
        ])
        result, observations, _ = run(client)
        self.assert_published(result, build_failed_public_factual_fallback(), NUMERIC, UNRELATED)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 0))
        self.assertFalse(observations)

    def test_unsupported_explanation_removed_leaving_advice_is_not_publishable(self):
        bad = UNSUPPORTED + " " + ADVICE
        client = TargetClient([bad, LIMITATION], [
            verification(bad, assessments=target(outcome="incomplete"), statuses=[False, True]),
            verification(LIMITATION, assessments=target(LIMITATION, outcome="bounded_limitation")),
        ], [completion(ADVICE, assessments=target(outcome="incomplete"))])
        result, _, _ = run(client)
        self.assert_published(result, LIMITATION, bad, ADVICE)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 1))

    def test_supported_explanatory_subset_still_salvages_without_generation_retry(self):
        draft = GOOD + " " + UNSUPPORTED
        client = TargetClient([draft], [verification(draft, assessments=target(), statuses=[True, False])],
                              [completion(GOOD, assessments=target())])
        result, observations, _ = run(client)
        self.assert_published(result, GOOD, draft)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (1, 1, 1))
        self.assertFalse(observations, "Sentence salvage stays outside generated-public shadow")

    def test_subset_missing_target_assessment_cannot_publish(self):
        draft = ONLY_MECHANISM + " " + UNSUPPORTED
        client = TargetClient([draft, LIMITATION], [
            verification(draft, assessments=target(outcome="incomplete"), statuses=[True, False]),
            verification(LIMITATION, assessments=target(LIMITATION, outcome="bounded_limitation")),
        ], [completion(ONLY_MECHANISM)])
        result, _, _ = run(client)
        self.assert_published(result, LIMITATION, draft, ONLY_MECHANISM)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 1))

    def test_subset_malformed_target_assessment_cannot_publish(self):
        draft = ONLY_MECHANISM + " " + UNSUPPORTED
        client = TargetClient([draft, LIMITATION], [
            verification(draft, assessments=target(outcome="incomplete"), statuses=[True, False]),
            verification(LIMITATION, assessments=target(LIMITATION, outcome="bounded_limitation")),
        ], [completion(ONLY_MECHANISM, assessments="supported")])
        result, _, _ = run(client)
        self.assert_published(result, LIMITATION, draft, ONLY_MECHANISM)

    def test_subset_global_completion_positive_cannot_erase_target_failure(self):
        draft = ONLY_MECHANISM + " " + UNSUPPORTED
        client = TargetClient([draft, LIMITATION], [
            verification(draft, assessments=target(outcome="incomplete"), statuses=[True, False]),
            verification(LIMITATION, assessments=target(LIMITATION, outcome="bounded_limitation")),
        ], [completion(ONLY_MECHANISM, assessments=target(outcome="incomplete"))])
        result, _, _ = run(client)
        self.assert_published(result, LIMITATION, draft, ONLY_MECHANISM)

    def test_supported_explanation_and_advice_subset_can_salvage(self):
        good = GOOD + " " + ADVICE
        draft = good + " " + UNSUPPORTED
        client = TargetClient([draft], [verification(draft, assessments=target(), statuses=[True, True, False])],
                              [completion(good, assessments=target(answer=GOOD))])
        result, observations, _ = run(client)
        self.assert_published(result, good, draft)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (1, 1, 1))
        self.assertFalse(observations)

    def test_truthful_limitation_subset_can_salvage(self):
        draft = UNSUPPORTED + " " + LIMITATION
        annotation = target(LIMITATION, outcome="bounded_limitation")
        client = TargetClient([draft], [verification(draft, assessments=annotation, statuses=[False, True])],
                              [completion(LIMITATION, outcome="bounded_limitation")])
        result, observations, _ = run(client)
        self.assert_published(result, LIMITATION, draft)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (1, 1, 1))
        self.assertFalse(observations)

    def test_subset_infrastructure_failure_uses_existing_retry(self):
        draft = ONLY_MECHANISM + " " + UNSUPPORTED
        client = TargetClient([draft, GOOD], [
            verification(draft, assessments=target(outcome="incomplete"), statuses=[True, False]),
            verification(GOOD, assessments=target()),
        ], [RuntimeError("Private payload must not be logged")])
        result, _, log = run(client)
        self.assert_published(result, GOOD, draft, ONLY_MECHANISM)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 1))
        self.assertNotIn("Private payload", log)

    def test_repeated_incomplete_subsets_remain_bounded(self):
        draft = ONLY_MECHANISM + " " + UNSUPPORTED
        verdict = verification(draft, assessments=target(outcome="incomplete"), statuses=[True, False])
        client = TargetClient([draft, draft], [verdict, verdict], [
            completion(ONLY_MECHANISM, assessments=target(outcome="incomplete")),
            completion(ONLY_MECHANISM, assessments=target(outcome="incomplete")),
        ])
        result, observations, _ = run(client)
        self.assert_published(result, build_failed_public_factual_fallback(), draft, ONLY_MECHANISM)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 2))
        self.assertEqual(len(client.calls), 6)
        self.assertFalse(observations)

    def test_ordinary_non_explanatory_question_does_not_require_new_annotations(self):
        client = TargetClient([ADVICE], [verification(ADVICE)])
        result, _, _ = run(client, "What should I try next?")
        self.assert_published(result, ADVICE)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (1, 1, 0))
        self.assertNotIn("explanation_target_assessments", client.calls[1]["format"].get("required", []))

    def test_shadow_observation_cannot_replace_successful_bound_answer(self):
        def reject_shadow(**kwargs):
            return {"status": "REJECTED", "text": "Unpublished shadow replacement"}
        client = TargetClient([GOOD], [verification(GOOD, assessments=target())])
        result, _, _ = run(client, observer=reject_shadow)
        self.assert_published(result, GOOD, "Unpublished shadow replacement")

    def test_assistant_prior_answer_cannot_repair_current_ambiguous_target(self):
        client = TargetClient([AMBIGUOUS, GOOD], [
            verification(AMBIGUOUS, assessments=target(outcome="incomplete")),
            verification(GOOD, assessments=target()),
        ])
        result, _, _ = run(client, history=[{"role": "assistant", "content": GOOD}])
        self.assert_published(result, GOOD, AMBIGUOUS)
        self.assertEqual(client.generations, 2)

    def test_literal_numeric_source_witness_does_not_establish_requested_targets(self):
        malformed = target(NUMERIC, mechanism="system", effect="adjusting", source_quote=NUMERIC)
        self.retry(NUMERIC, bad_assessment=malformed)


if __name__ == "__main__":
    unittest.main()
