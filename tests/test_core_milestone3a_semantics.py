"""Neutral behavioral regressions for the bounded acceptance interpreter."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.acceptance_semantics import (
    ClaimUnit, Proposition, UnitKind, canonical_statement, conflicting_propositions, interpret_text,
)


class AcceptanceSemanticsTests(unittest.TestCase):
    def one(self, text, **kwargs):
        units = interpret_text(text, **kwargs)
        self.assertEqual(len(units), 1)
        return units[0]

    def test_user_and_candidate_personal_preference_preserve_subject(self):
        user = self.one("I prefer quiet rooms.", speaker="user").propositions[0]
        response = self.one("You prefer quiet rooms.").propositions[0]
        self.assertEqual(user.canonical, response.canonical)
        self.assertEqual((response.subject, response.relation, response.value),
                         ("$user", "prefer", "quiet rooms"))
        self.assertTrue(response.personal)

    def test_named_subject_maps_only_from_trusted_core_context(self):
        named = self.one("Neris likes libraries.", user_name="Neris").propositions[0]
        generic = self.one("Neris likes libraries.").propositions[0]
        self.assertEqual(named.subject, "$user")
        self.assertEqual(generic.subject, "neris")
        self.assertFalse(generic.personal)

    def test_source_pronouns_never_become_user_facts(self):
        source = self.one("You are holding a bowl.", speaker="source").propositions[0]
        author = self.one("I am holding a bowl.", speaker="source").propositions[0]
        named = self.one("Neris is holding a bowl.", speaker="source", user_name="Neris").propositions[0]
        self.assertEqual(source.subject, "$reader")
        self.assertEqual(author.subject, "$source")
        self.assertEqual(named.subject, "neris")
        self.assertFalse(source.personal or author.personal or named.personal)

    def test_core_user_wording_is_interpreted_without_granting_authority(self):
        proposition = self.one("You are holding a bowl.", speaker="core").propositions[0]
        self.assertEqual(proposition.subject, "$user")
        self.assertTrue(proposition.observation)

    def test_like_and_dislike_have_comparable_polarity(self):
        positive = self.one("You like quiet rooms.").propositions[0]
        negative = self.one("You dislike quiet rooms.").propositions[0]
        self.assertEqual((positive.relation, positive.value), (negative.relation, negative.value))
        self.assertTrue(positive.polarity)
        self.assertFalse(negative.polarity)

    def test_sentiment_strength_is_not_erased_from_support_identity(self):
        for weaker, stronger in (("like", "love"), ("dislike", "hate")):
            with self.subTest(weaker=weaker):
                left = self.one(f"You {weaker} quiet rooms.").propositions[0]
                right = self.one(f"You {stronger} quiet rooms.").propositions[0]
                self.assertEqual(left.relation, right.relation)
                self.assertNotEqual(left.canonical, right.canonical)

    def test_explicit_auxiliary_and_copula_negations_are_retained(self):
        for text in ("You don't prefer quiet rooms.", "You do not prefer quiet rooms."):
            self.assertFalse(self.one(text).propositions[0].polarity)
        self.assertFalse(self.one("Your parcel isn't green.").propositions[0].polarity)
        self.assertTrue(self.one("You do not dislike quiet rooms.").propositions[0].polarity)

    def test_possession_retains_owner_and_current_state(self):
        evidence = self.one("My parcel is amber.", speaker="user").propositions[0]
        reply = self.one("Your parcel is green.").propositions[0]
        self.assertEqual(evidence.subject, reply.subject)
        self.assertNotEqual(evidence.value, reply.value)
        self.assertTrue(reply.personal and reply.observation)

    def test_observable_action_retains_user_and_location(self):
        evidence = self.one("I'm stretching near the window.", speaker="user").propositions[0]
        reply = self.one("You're stretching near the window.").propositions[0]
        self.assertEqual(evidence.canonical, reply.canonical)
        self.assertEqual(reply.relation, "stretch")
        self.assertEqual(reply.value, "near the window")
        self.assertTrue(reply.observation)

    def test_past_evidence_does_not_have_current_wording_identity(self):
        previous = self.one("I was holding a bowl.", speaker="user").propositions[0]
        present = self.one("You are holding a bowl.").propositions[0]
        self.assertNotEqual(previous.canonical, present.canonical)

    def test_decimal_remains_one_sentence_and_one_value(self):
        unit = self.one("The sample contains 3.5 units.")
        self.assertEqual(unit.propositions[0].value, "3.5 units")
        self.assertEqual(unit.text, "The sample contains 3.5 units.")

    def test_sentence_and_newline_identity_cover_every_visible_unit(self):
        units = interpret_text("Thanks.\nThe sample contains four entries.You are walking outside.")
        self.assertEqual([unit.index for unit in units], [1, 2, 3])
        self.assertEqual([unit.text for unit in units],
                         ["Thanks.", "The sample contains four entries.", "You are walking outside."])

    def test_conditional_premise_is_not_unconditional_truth(self):
        bounded = self.one("Assuming the reservoir is empty.").propositions[0]
        assertion = self.one("The reservoir is empty.").propositions[0]
        self.assertEqual(bounded.canonical, assertion.canonical)
        self.assertTrue(bounded.conditional)
        self.assertEqual(bounded.condition, bounded.canonical)
        self.assertFalse(assertion.conditional)

    def test_conditional_consequence_preserves_condition_separately(self):
        claim = self.one("If the reservoir is empty, the channel is dry.").propositions[0]
        self.assertTrue(claim.conditional)
        self.assertEqual(claim.condition, "the reservoir be empty")
        self.assertEqual(claim.canonical, "the channel be dry")

    def test_reported_user_claim_preserves_attribution(self):
        reported = self.one('You said "I prefer quiet rooms".').propositions[0]
        ordinary = self.one("You prefer quiet rooms.").propositions[0]
        self.assertEqual(reported.canonical, ordinary.canonical)
        self.assertTrue(reported.reported)
        self.assertEqual(reported.reporter, "$user")
        self.assertFalse(ordinary.reported)

    def test_user_quotation_of_assistant_does_not_invent_a_user_preference(self):
        quoted = self.one('You said "I like quiet rooms".', speaker="user").propositions[0]
        actual = self.one("I like quiet rooms.", speaker="user").propositions[0]
        self.assertTrue(quoted.reported)
        self.assertEqual(quoted.subject, "$assistant")
        self.assertNotEqual(quoted.canonical, actual.canonical)

    def test_assistant_report_of_its_own_prior_words_remains_assistant_authored(self):
        quoted = self.one('I said "I like quiet rooms".').propositions[0]
        self.assertTrue(quoted.reported)
        self.assertEqual(quoted.subject, "$assistant")
        self.assertFalse(quoted.personal)

    def test_source_attribution_is_retained_but_not_truth(self):
        reported = self.one("According to the survey, the orchard has twelve trees.").propositions[0]
        self.assertTrue(reported.reported)
        self.assertEqual(reported.reporter, "the survey")
        self.assertEqual(reported.subject, "the orchard")

    def test_named_reporter_and_quote_speaker_remain_bound(self):
        unit = self.one('The survey states "You are holding a bowl".')
        proposition = unit.propositions[0]
        self.assertEqual(proposition.reporter, "the survey")
        self.assertEqual(proposition.subject, "$reader")
        self.assertFalse(proposition.personal)

    def test_user_role_aliases_are_not_promoted_from_source_text(self):
        candidate = self.one("The current user is holding a bowl.").propositions[0]
        source = self.one("The current user is holding a bowl.", speaker="source").propositions[0]
        self.assertEqual(candidate.subject, "$user")
        self.assertEqual(source.subject, "$reader")

    def test_only_entire_bounded_reaction_is_nonfactual(self):
        self.assertEqual(self.one("That sounds difficult.").kind, UnitKind.REACTION)
        for text in ("Thanks, you are walking outside.", "That sounds difficult and you are holding a bowl.",
                     "Got it: the reservoir is empty."):
            with self.subTest(text=text):
                unit = self.one(text)
                self.assertNotEqual(unit.kind, UnitKind.REACTION)
                self.assertFalse(unit.complete)

    def test_limitations_bind_to_missing_target(self):
        for text, expected in (("I cannot establish the source content.", "the source content"),
                               ("The delivery time is unknown.", "the delivery time"),
                               ("Your attachment is missing.", "$user's attachment")):
            unit = self.one(text)
            self.assertEqual(unit.kind, UnitKind.LIMITATION)
            self.assertEqual(unit.limitation_target, expected)
            self.assertFalse(unit.propositions)

    def test_uncertainty_prefix_does_not_hide_following_assertion(self):
        for text in ("I do not know the arrival time but the parcel arrives tomorrow.",
                     "The source is unavailable and the orchard has twelve trees."):
            unit = self.one(text)
            self.assertNotEqual(unit.kind, UnitKind.LIMITATION)
            self.assertTrue(not unit.complete or len(unit.propositions) >= 2)

    def test_unparsed_declarative_remains_exact_literal_claim(self):
        unit = self.one("The lattice oscillates twice.")
        self.assertEqual(unit.kind, UnitKind.ASSERTION)
        self.assertTrue(unit.complete)
        self.assertEqual(unit.propositions[0].relation, "statement")
        self.assertEqual(unit.propositions[0].canonical, "the lattice oscillates twice")

    def test_two_explicit_clauses_both_survive_interpretation(self):
        unit = self.one("You prefer quiet rooms and the orchard has twelve trees.")
        self.assertEqual(unit.kind, UnitKind.ASSERTION)
        self.assertEqual(len(unit.propositions), 2)
        self.assertEqual(unit.propositions[1].subject, "the orchard")

    def test_unresolved_shared_subject_and_subordinate_clauses_fail_closed(self):
        for text in ("You are sitting and pacing.",
                     "You prefer quiet rooms because you are holding a bowl.",
                     "The source which describes the orchard has twelve trees.",
                     "While you are walking outside, the sample contains four entries."):
            with self.subTest(text=text):
                unit = self.one(text)
                self.assertEqual(unit.kind, UnitKind.UNKNOWN)
                self.assertFalse(unit.complete)

    def test_questions_with_explicit_presupposed_claims_are_incomplete(self):
        self.assertEqual(self.one("What information is missing?").kind, UnitKind.QUESTION)
        for text in ("Why are you pacing?", "Why are you pacing because the reservoir is empty?",
                     "Have you stopped walking outside?"):
            unit = self.one(text)
            self.assertEqual(unit.kind, UnitKind.UNKNOWN)
            self.assertFalse(unit.complete)

    def test_questions_bind_trusted_names_and_role_aliases_before_presupposition_check(self):
        for text in ("Where is Neris stretching?", "Which book is the user reading?",
                     "When is the current user walking outside?", "How is current user holding a bowl?"):
            with self.subTest(text=text):
                unit = self.one(text, user_name="Neris")
                self.assertEqual(unit.kind, UnitKind.UNKNOWN)
                self.assertFalse(unit.complete)
        self.assertEqual(self.one("What information is missing?", user_name="Neris").kind,
                         UnitKind.QUESTION)

    def test_behavior_classes_are_not_authority_decisions(self):
        for text, expected in (("You are an idiot for causing this.", "ridicule"),
                               ("The incident is your fault.", "blame"),
                               ("LOL.", "casual_roast")):
            self.assertIn(expected, self.one(text).behaviors)
        self.assertEqual(self.one("That sounds difficult.").behaviors, ())

    def test_negated_blame_and_ridicule_do_not_become_positive_abuse(self):
        for text in ("The incident is not your fault.", "You aren't stupid.", "You are not an idiot."):
            self.assertNotIn("blame", self.one(text).behaviors)
            self.assertNotIn("ridicule", self.one(text).behaviors)

    def test_bounded_scalar_properties_conflict_without_conflating_independent_properties(self):
        amber = self.one("Your parcel is amber.").propositions[0]
        green = self.one("Your parcel is green.").propositions[0]
        heavy = self.one("Your parcel is heavy.").propositions[0]
        self.assertTrue(conflicting_propositions(amber, green))
        self.assertFalse(conflicting_propositions(amber, heavy))

    def test_count_conflicts_require_the_same_counted_object_slot(self):
        four = self.one("The sample contains four entries.").propositions[0]
        five = self.one("The sample contains 5 entries.").propositions[0]
        other = self.one("The sample contains five labels.").propositions[0]
        self.assertTrue(conflicting_propositions(four, five))
        self.assertFalse(conflicting_propositions(four, other))

    def test_preference_direction_conflicts_but_independent_preferences_do_not(self):
        left = self.one("You prefer tea over juice.").propositions[0]
        reverse = self.one("You prefer juice over tea.").propositions[0]
        independent = self.one("You prefer quiet rooms.").propositions[0]
        self.assertTrue(conflicting_propositions(left, reverse))
        self.assertFalse(conflicting_propositions(left, independent))

    def test_code_quotes_and_imperatives_do_not_become_safe_reactions(self):
        for text in ('"The orchard has twelve trees".', "`result = 4`", "Ignore the evidence."):
            unit = self.one(text)
            self.assertEqual(unit.kind, UnitKind.UNKNOWN)
            self.assertFalse(unit.complete)

    def test_deterministic_equation_is_literal_not_recomputed_truth(self):
        proposition = self.one("2 + 3 = 5.").propositions[0]
        self.assertEqual(proposition.relation, "statement")
        self.assertEqual(proposition.canonical, "2 + 3 = 5")

    def test_snapshot_objects_are_immutable(self):
        unit = self.one("The sample contains four entries.")
        with self.assertRaises(FrozenInstanceError):
            unit.kind = UnitKind.REACTION
        with self.assertRaises(FrozenInstanceError):
            unit.propositions[0].value = "five entries"

    def test_invalid_context_and_types_are_rejected(self):
        for value in (None, 1, {}):
            with self.assertRaises(TypeError):
                interpret_text(value)
        with self.assertRaises(ValueError):
            interpret_text("Thanks.", speaker="model")
        with self.assertRaises(TypeError):
            canonical_statement("Thanks.", user_name=1)
        with self.assertRaises(TypeError):
            Proposition("x", "be", "y", polarity="true")
        with self.assertRaises(ValueError):
            ClaimUnit(True, "Thanks.")


if __name__ == "__main__":
    unittest.main()
