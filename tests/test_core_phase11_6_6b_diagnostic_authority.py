"""Core-detected diagnostic propositions cannot disappear in model labels."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.diagnostic_obligations import build_diagnostic_obligations, diagnostic_obligation_violations


def assessment(kind="none", *, index=1, supported=True, applicable=False, quote=None, turn=1):
    return {
        "sentence_index": index, "kind": kind, "supported": supported,
        "applicability_established": applicable,
        "user_witness": {"turn_index": turn, "quote": quote} if quote is not None else None,
    }


def check(draft, record=None, user="My readings vary during the quiet cycle."):
    return diagnostic_obligation_violations(
        build_diagnostic_obligations([draft]),
        [assessment() if record is None else record], [user],
    )


class DiagnosticAuthorityClosureTests(unittest.TestCase):
    def test_clear_causal_structures_are_owned_by_core(self):
        cases = (
            "Queue resets cause packet loss.",
            "The packet loss is caused by queue resets.",
            "Queue resets explain packet loss.",
            "The packet loss is because of queue resets.",
            "Queue resets are why packets disappear.",
            "Queue resets make packets disappear.",
            "The reason for packet loss is queue resets.",
            "This happens because queue counters expire.",
            "Your gateway is dropping packets because the queue resets.",
            "You are only noticing the jitter because the room is quiet.",
        )
        for draft in cases:
            with self.subTest(draft=draft):
                targets = build_diagnostic_obligations([draft])
                self.assertTrue(targets)
                self.assertTrue(any(target["predicate"] == "causal" for target in targets))
                self.assertTrue(check(draft))

    def test_positive_none_cannot_erase_causes_in_five_domains(self):
        cases = (
            "The packet loss is caused by queue resets.",
            "The shimmer is caused by scan timing changes.",
            "The drain is because the controller keeps waking.",
            "The pause is caused by cache flushes.",
            "The exception is caused by index rebuilding.",
        )
        for draft in cases:
            with self.subTest(draft=draft):
                self.assertTrue(check(draft, assessment("none")))

    def test_positive_conditional_label_cannot_erase_actual_cause(self):
        for draft in (
            "Your gateway is dropping packets because the queue resets.",
            "The shimmer is caused by scan timing changes.",
            "The drain is because the controller keeps waking.",
            "The pause is caused by cache flushes.",
            "The exception is caused by index rebuilding.",
        ):
            with self.subTest(draft=draft):
                self.assertTrue(check(draft, assessment("conditional_hypothesis")))

    def test_actual_user_cause_is_accepted(self):
        user = "My queue resets cause packet loss."
        self.assertEqual(check(
            "Your queue resets cause packet loss.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ), [])

    def test_active_user_cause_supports_passive_candidate(self):
        user = "My queue resets cause packet loss."
        self.assertEqual(check(
            "The packet loss is caused by queue resets.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ), [])

    def test_passive_user_cause_supports_active_candidate(self):
        user = "My packet loss is caused by queue resets."
        self.assertEqual(check(
            "Queue resets cause packet loss.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ), [])

    def test_past_user_cause_is_structurally_available(self):
        user = "My queue resets caused packet loss."
        self.assertEqual(check(
            "Queue resets caused packet loss.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ), [])

    def test_symptom_only_quote_cannot_support_cause(self):
        user = "My packet loss rises when the workload rises."
        self.assertTrue(check(
            "The packet loss is caused by queue resets.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_topic_overlap_cannot_support_a_different_cause(self):
        user = "My signal fade causes packet loss."
        self.assertTrue(check(
            "Queue resets cause packet loss.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_matching_cause_with_changed_effect_is_rejected(self):
        user = "My queue resets cause counter jumps."
        self.assertTrue(check(
            "Queue resets cause packet loss.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_cause_effect_reversal_is_rejected(self):
        user = "My queue resets cause packet loss."
        self.assertTrue(check(
            "Packet loss causes queue resets.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_exact_user_pronominal_cause_can_remain_accepted(self):
        user = "That causes it."
        self.assertEqual(check(user, assessment("supplied_mechanism", applicable=True, quote=user), user), [])

    def test_pronominal_cause_still_requires_a_user_causal_proposition(self):
        user = "My readings rise during the quiet cycle."
        self.assertTrue(check("That causes it.", assessment("supplied_mechanism", applicable=True, quote=user), user))

    def test_causal_exclusion_needs_its_own_authority(self):
        user = "My scan timing changes cause shimmer."
        self.assertTrue(check(
            "The shimmer is not caused by scan timing changes.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_user_authored_causal_exclusion_remains_accepted(self):
        user = "My shimmer is not caused by scan timing changes."
        self.assertEqual(check(
            "The shimmer is not caused by scan timing changes.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ), [])

    def test_contracted_causal_exclusion_is_detected(self):
        self.assertTrue(check("The shimmer isn't caused by scan timing changes."))

    def test_reason_exclusion_cannot_match_affirmative_reason(self):
        user = "The reason for pauses is cache flushing."
        self.assertTrue(check(
            "The reason for pauses is not cache flushing.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_actual_property_in_five_domains_requires_authority(self):
        for draft in (
            "Your gateway has a reset queue.",
            "Your module has a slow response.",
            "Your battery is losing capacity.",
            "Your disk is flushing its cache.",
            "Your runtime is rebuilding indexes.",
        ):
            with self.subTest(draft=draft):
                targets = build_diagnostic_obligations([draft])
                self.assertTrue(any(item["kind"] == "actual_property" for item in targets))
                self.assertTrue(check(draft))

    def test_user_property_can_support_actual_property(self):
        user = "My module has slow response."
        self.assertEqual(check(
            "Your module has slow response.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ), [])

    def test_observed_property_can_support_actual_property(self):
        user = "I measured slow response in my module."
        self.assertEqual(check(
            "Your module has slow response.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ), [])

    def test_observed_property_does_not_support_causal_application(self):
        user = "I measured slow response in my module."
        self.assertTrue(check(
            "Your module has slow response and that explains the shimmer.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_supplied_property_with_generic_relative_explanation_is_allowed(self):
        user = "My module has slow response."
        self.assertEqual(check(
            "Your module has slow response, which could explain the shimmer.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ), [])

    def test_actual_property_changes_are_not_topic_entailment(self):
        user = "My module has slow response."
        self.assertTrue(check(
            "Your module has a damaged connector.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_actual_property_subject_changes_are_rejected(self):
        user = "My controller has slow response."
        self.assertTrue(check(
            "Your module has slow response.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_negative_property_cannot_support_positive_property(self):
        user = "My queue does not reset."
        self.assertTrue(check(
            "Your queue does reset.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_positive_property_cannot_support_negative_property(self):
        user = "My queue does reset."
        self.assertTrue(check(
            "Your queue does not reset.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_same_negative_property_is_accepted(self):
        user = "My queue does not reset."
        self.assertEqual(check(
            "Your queue does not reset.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ), [])

    def test_absence_property_cannot_match_positive_property(self):
        user = "My module has intermittent contact."
        self.assertTrue(check(
            "Your module has no intermittent contact.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_comparative_user_property_is_not_inferred(self):
        user = "My hearing is sensitive to that tone."
        self.assertTrue(check(
            "Your hearing is more sensitive to that tone.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_perceptual_application_is_not_mechanism_free(self):
        self.assertTrue(check("You are only noticing the jitter because the room is quiet."))

    def test_perceptual_user_observation_can_be_preserved(self):
        user = "I am noticing the jitter."
        self.assertEqual(check(
            "You are noticing the jitter.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ), [])

    def test_perceptual_observation_does_not_establish_its_explanation(self):
        user = "I am noticing the jitter in the quiet room."
        self.assertTrue(check(
            "You are noticing the jitter because the room is quiet.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_explicit_generic_hypotheses_across_domains_remain_allowed(self):
        for draft in (
            "One possibility is that queue variation could cause packet loss.",
            "Scan timing variation can make shimmer easier to notice.",
            "One hypothesis is that controller wakes might cause drain.",
            "Cache flushes could explain pauses.",
            "One possible explanation is that index rebuilding can cause delays.",
        ):
            with self.subTest(draft=draft):
                targets = build_diagnostic_obligations([draft])
                self.assertTrue(targets)
                self.assertTrue(all(target["mode"] == "conditional" for target in targets))
                self.assertEqual(check(draft, assessment("conditional_hypothesis")), [])

    def test_conditional_mechanism_cannot_be_erased_by_none(self):
        self.assertTrue(check("Cache flushes could explain pauses.", assessment("none")))

    def test_if_antecedent_and_modal_explanation_remain_allowed(self):
        draft = ("If your module has different timing, that could make shimmer easier to notice, "
                 "but we do not know that your module is doing that.")
        targets = build_diagnostic_obligations([draft])
        self.assertTrue(targets)
        self.assertTrue(all(target["mode"] == "conditional" for target in targets))
        self.assertEqual(check(draft, assessment("conditional_hypothesis")), [])

    def test_initial_if_does_not_exempt_later_actual_property(self):
        draft = "If timing varies, it could explain shimmer; your module has slow response."
        self.assertTrue(any(target["mode"] == "asserted" for target in build_diagnostic_obligations([draft])))
        self.assertTrue(check(draft, assessment("conditional_hypothesis")))

    def test_initial_modal_does_not_exempt_later_actual_cause(self):
        draft = "Queue resets could explain loss, but the actual loss is caused by signal fade."
        self.assertTrue(check(draft, assessment("conditional_hypothesis")))

    def test_generic_conditional_does_not_exempt_property_tail(self):
        draft = "Cache flushes could explain pauses and your disk has a failing controller."
        self.assertTrue(check(draft, assessment("conditional_hypothesis")))

    def test_known_property_claim_is_detected(self):
        self.assertTrue(check("That is a known quirk of your controller."))

    def test_supplied_property_can_back_a_conditional_explanation(self):
        user = "I measured an intermittent contact in my relay."
        draft = "The intermittent contact you measured could explain the jump, though it is not proven to be the only cause."
        self.assertEqual(check(draft, assessment("supplied_mechanism", applicable=True, quote=user), user), [])

    def test_competing_hypotheses_and_limits_create_no_actual_claim(self):
        for draft in (
            "The relay remains plausible; the observation does not establish it as the cause.",
            "Queue resets and signal fade remain plausible alternatives.",
            "Your observation does not establish the cause.",
            "No cause is established.",
            "The cause remains unknown.",
            "The reason is not known.",
            "That observation does not identify a cause.",
            "The observation does not prove that queue resets cause packet loss.",
            "We do not know whether queue resets cause packet loss.",
            "There is no evidence that queue resets cause packet loss.",
            "Its presence in your relay is unestablished.",
        ):
            with self.subTest(draft=draft):
                self.assertEqual(build_diagnostic_obligations([draft]), ())

    def test_requesting_or_offering_an_explanation_does_not_assert_a_cause(self):
        for draft in (
            "Can you explain what happens?", "Could you please explain the symptom?",
            "Please explain what you measured.", "Explain the symptom.", "I can explain the procedure.",
        ):
            with self.subTest(draft=draft):
                self.assertEqual(build_diagnostic_obligations([draft]), ())

    def test_limitation_does_not_hide_later_causal_tail(self):
        self.assertTrue(check("We do not know the cause, but queue resets cause the loss."))

    def test_contrast_exclusion_and_replacement_need_authority(self):
        self.assertTrue(check("It is not the cable; it is the cache flushing."))

    def test_matching_user_contrast_remains_accepted(self):
        user = "It is not the cable; it is the cache flushing."
        self.assertEqual(check(user, assessment("supplied_mechanism", applicable=True, quote=user), user), [])

    def test_a_single_supplied_cause_does_not_establish_exclusive_cause(self):
        user = "My queue resets cause packet loss."
        self.assertTrue(check(
            "Only queue resets cause packet loss.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_matching_exclusive_user_cause_is_accepted(self):
        user = "Only my queue resets cause packet loss."
        self.assertEqual(check(
            "Only your queue resets cause packet loss.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ), [])

    def test_quoted_user_proposition_is_not_authority(self):
        quote = "Queue resets cause packet loss"
        self.assertTrue(check(
            quote + ".", assessment("supplied_mechanism", applicable=True, quote=quote),
            'The log says "' + quote + '" but I have not confirmed it.',
        ))

    def test_full_quoted_witness_does_not_remove_quotation_boundary(self):
        user = '"Queue resets cause packet loss"'
        self.assertTrue(check(
            "Queue resets cause packet loss.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_larger_witness_cannot_promote_quoted_proposition(self):
        user = 'The note says "Queue resets cause packet loss".'
        self.assertTrue(check(
            "Queue resets cause packet loss.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_short_witness_cannot_drop_conditional_source_scope(self):
        quote = "queue resets cause packet loss"
        self.assertTrue(check(
            quote + ".", assessment("supplied_mechanism", applicable=True, quote=quote),
            "If " + quote + ", I will test them.",
        ))

    def test_questioned_user_proposition_is_not_an_actual_cause(self):
        user = "Do queue resets cause packet loss?"
        self.assertTrue(check(
            "Queue resets cause packet loss.",
            assessment("supplied_mechanism", applicable=True, quote="queue resets cause packet loss"), user,
        ))

    def test_future_proposition_is_not_current_user_authority(self):
        user = "Queue resets will cause packet loss."
        self.assertTrue(check(
            "Queue resets cause packet loss.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_conditional_user_cause_cannot_be_promoted_to_actual(self):
        user = "Queue resets could cause packet loss."
        self.assertTrue(check(
            "Queue resets cause packet loss.",
            assessment("supplied_mechanism", applicable=True, quote=user), user,
        ))

    def test_assistant_or_candidate_text_is_not_a_user_witness(self):
        draft = "Queue resets cause packet loss."
        self.assertTrue(check(draft, assessment("supplied_mechanism", applicable=True, quote=draft)))

    def test_missing_assessments_fail_closed(self):
        targets = build_diagnostic_obligations(["Queue resets cause packet loss."])
        for raw in (None, {}, [], "none"):
            with self.subTest(raw=raw):
                self.assertTrue(diagnostic_obligation_violations(targets, raw, ["Readings vary."]))

    def test_scoped_assessment_indexes_are_strict(self):
        for index in (True, "1", 0, -1, 2):
            with self.subTest(index=index):
                self.assertTrue(check("Queue resets cause packet loss.", assessment(index=index)))

    def test_duplicate_assessment_indexes_fail_closed(self):
        targets = build_diagnostic_obligations(["Queue resets cause packet loss."])
        self.assertTrue(diagnostic_obligation_violations(targets, [assessment(), assessment()], []))

    def test_malformed_assessment_kinds_do_not_raise_or_accept(self):
        for kind in (None, [], {}, "trusted_from_model"):
            with self.subTest(kind=kind):
                self.assertTrue(check("Queue resets cause packet loss.", assessment(kind)))

    def test_assessment_booleans_are_strict(self):
        for field in ("supported", "applicability_established"):
            record = assessment()
            record[field] = "true"
            self.assertTrue(check("Queue resets cause packet loss.", record))

    def test_conditional_assessment_cannot_claim_established_applicability(self):
        self.assertTrue(check("Cache flushes could explain pauses.", assessment("conditional_hypothesis", applicable=True)))

    def test_missing_witness_field_cannot_clear_a_conditional_obligation(self):
        record = assessment("conditional_hypothesis")
        del record["user_witness"]
        self.assertTrue(check("Cache flushes could explain pauses.", record))

    def test_wrong_witness_turn_or_boolean_index_fails_closed(self):
        user = "My queue resets cause packet loss."
        for turn in (True, 0, 2, "1"):
            with self.subTest(turn=turn):
                self.assertTrue(check(user, assessment("supplied_mechanism", applicable=True, quote=user, turn=turn), user))

    def test_negatively_assessed_obligation_never_accepts(self):
        self.assertTrue(check("Queue resets could cause packet loss.", assessment("conditional_hypothesis", supported=False)))

    def test_sentence_indexes_and_order_remain_core_owned(self):
        targets = build_diagnostic_obligations([
            "No cause is established.", "Queue resets cause packet loss.", "Cache flushes could explain pauses.",
        ])
        self.assertEqual({target["sentence_index"] for target in targets}, {2, 3})
        user = "Queue resets cause packet loss."
        self.assertEqual(diagnostic_obligation_violations(targets, [
            assessment("conditional_hypothesis", index=3),
            assessment("supplied_mechanism", index=2, applicable=True, quote=user),
            assessment(index=1),
        ], [user]), [])

    def test_no_obligation_adds_no_unrelated_schema(self):
        self.assertEqual(diagnostic_obligation_violations((), {}, []), [])


if __name__ == "__main__":
    unittest.main()
