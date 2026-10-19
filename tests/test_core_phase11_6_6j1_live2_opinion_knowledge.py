"""Unknown-work appraisals need a basis regardless of grammatical placement."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.opinion_knowledge import find_opinion_knowledge_violations, project_work_appraisals
from test_core_phase11_6_6g_opinion_knowledge import packet


SUBJECT = "Lumen Harbor"
REQUEST = "What do you actually think of Lumen Harbor? I want your take."


def check(draft, **kwargs):
    return find_opinion_knowledge_violations(REQUEST, draft, **kwargs)


def researched(**kwargs):
    return packet(subject=SUBJECT, content=SUBJECT + " has measured pacing and unusual controls.", **kwargs)


class WorkPropertyProjectionTests(unittest.TestCase):
    def test_arbitrary_consumption_quality_is_not_a_preference(self):
        self.assertTrue(check("It's an arresting read."))

    def test_named_work_consumption_quality_has_the_same_requirement(self):
        self.assertTrue(check("Lumen Harbor is an arresting read."))

    def test_indirect_first_person_quality_marker_does_not_supply_a_basis(self):
        self.assertTrue(check("I think it's an arresting read."))

    def test_attributive_work_property_requires_a_basis(self):
        self.assertTrue(check("It has measured pacing."))

    def test_adverbial_modifier_is_a_property_not_a_confidence_authority(self):
        self.assertTrue(check("It has unusually measured pacing."))

    def test_nominal_list_properties_are_independently_projected(self):
        items = project_work_appraisals("It has measured pacing and unusual controls.")
        self.assertEqual({item.dimension for item in items}, {"pacing", "controls"})

    def test_attributive_property_after_consumption_appraisal_is_projected(self):
        items = project_work_appraisals("It's an arresting read with meticulous world-building.")
        self.assertEqual({item.dimension for item in items}, {"world-building", "consumption_appraisal"})

    def test_possessive_named_property_is_projected(self):
        self.assertTrue(check("Lumen Harbor's meticulous world-building appeals to me."))

    def test_standalone_nominal_appraisal_requires_a_basis(self):
        self.assertTrue(check("Meticulous world-building."))

    def test_regular_release_property_requires_a_basis(self):
        self.assertTrue(check("It has regular updates."))

    def test_release_schedule_predicate_requires_a_basis(self):
        self.assertTrue(check("The release schedule is regular."))

    def test_quality_preservation_predicate_requires_a_basis(self):
        self.assertTrue(check("The artwork holds up."))

    def test_adverbial_quality_preservation_requires_a_basis(self):
        self.assertTrue(check("The dialogue still stands up."))

    def test_disclaimer_cannot_supply_attributive_property(self):
        self.assertTrue(check("I haven't read it, but it has measured pacing."))

    def test_disclaimer_cannot_supply_quality_preservation(self):
        self.assertTrue(check("I don't know enough; the artwork holds up."))

    def test_work_topic_mention_does_not_supply_property(self):
        self.assertTrue(check("It has measured pacing.", conversation=[
            {"role": "user", "content": "I like Lumen Harbor."}]))

    def test_model_knowledge_qualifier_does_not_supply_property(self):
        self.assertTrue(check("From what I know, it has measured pacing."))

    def test_assistant_property_is_not_a_user_witness(self):
        self.assertTrue(check("It has measured pacing.", conversation=[
            {"role": "assistant", "content": "Lumen Harbor has measured pacing."}]))

    def test_candidate_research_claim_is_not_research(self):
        self.assertTrue(check("I researched Lumen Harbor. It has measured pacing."))

    def test_named_user_attribute_can_be_discussed(self):
        self.assertEqual(check("It has measured pacing.", conversation=[
            {"role": "user", "content": "Lumen Harbor has measured pacing."}]), [])

    def test_user_predicate_and_candidate_attribute_have_the_same_property(self):
        self.assertEqual(check("It has measured pacing.", conversation=[
            {"role": "user", "content": "Lumen Harbor's pacing is measured."}]), [])

    def test_user_attribute_and_candidate_predicate_have_the_same_property(self):
        self.assertEqual(check("The pacing is measured.", conversation=[
            {"role": "user", "content": "Lumen Harbor has measured pacing."}]), [])

    def test_user_attributed_release_property_can_be_discussed(self):
        self.assertEqual(check("According to you, it has regular updates.", conversation=[
            {"role": "user", "content": "Lumen Harbor has regular updates."}]), [])

    def test_user_consumption_appraisal_can_be_discussed_without_own_consumption(self):
        self.assertEqual(check("It's an arresting read.", conversation=[
            {"role": "user", "content": "Lumen Harbor is an arresting read."}]), [])

    def test_user_consumption_tense_is_not_silently_upgraded(self):
        self.assertTrue(check("It's an arresting read.", conversation=[
            {"role": "user", "content": "Lumen Harbor was an arresting read."}]))

    def test_user_predicate_polarity_is_preserved(self):
        self.assertTrue(check("It has measured pacing.", conversation=[
            {"role": "user", "content": "Lumen Harbor's pacing is not measured."}]))

    def test_user_attribute_tense_is_preserved(self):
        self.assertTrue(check("The pacing is measured.", conversation=[
            {"role": "user", "content": "Lumen Harbor's pacing was measured."}]))

    def test_latest_named_user_correction_wins(self):
        history = [{"role": "user", "content": "Lumen Harbor has measured pacing."},
                   {"role": "user", "content": "Correction: Lumen Harbor's pacing is not measured."}]
        self.assertTrue(check("It has measured pacing.", conversation=history))
        self.assertEqual(check("The pacing is not measured.", conversation=history), [])

    def test_unrelated_work_attribute_does_not_supply_current_work(self):
        self.assertTrue(check("It has measured pacing.", conversation=[
            {"role": "user", "content": "Coral Atlas has measured pacing."}]))

    def test_property_question_is_not_a_user_witness(self):
        self.assertTrue(check("It has measured pacing.", conversation=[
            {"role": "user", "content": "Does Lumen Harbor have measured pacing?"}]))

    def test_prior_accepted_preference_does_not_supply_work_properties(self):
        self.assertTrue(check("I still like it; it has measured pacing.", opinion_entry={
            "stance_text": "I like Lumen Harbor."}))

    def test_established_pure_preference_stays_available(self):
        self.assertEqual(check("I still like Lumen Harbor.", opinion_entry={
            "stance_text": "I like Lumen Harbor."}), [])

    def test_real_subject_research_defers_entailment_to_existing_source_verifier(self):
        self.assertEqual(check("It has measured pacing.", research_evidence=researched()), [])

    def test_rejected_source_does_not_supply_familiarity(self):
        self.assertTrue(check("It has measured pacing.", research_evidence=researched(rejected=True)))

    def test_unread_source_does_not_supply_familiarity(self):
        self.assertTrue(check("It has measured pacing.", research_evidence=researched(readable=False)))

    def test_subject_title_without_matching_body_does_not_supply_familiarity(self):
        evidence = packet(subject=SUBJECT, content="Coral Atlas has measured pacing.")
        self.assertTrue(check("It has measured pacing.", research_evidence=evidence))

    def test_conditional_property_discussion_remains_available(self):
        self.assertEqual(check("If it has measured pacing, I might enjoy it."), [])

    def test_speculative_conditional_preference_remains_available(self):
        self.assertEqual(check("I would enjoy measured pacing, but I don't know whether this has it."), [])

    def test_generic_first_person_taste_is_not_work_familiarity(self):
        self.assertEqual(check("I prefer clear prose and measured pacing."), [])

    def test_plain_property_question_is_not_an_appraisal(self):
        self.assertEqual(check("Does it have measured pacing?"), [])

    def test_truthful_self_limitation_remains_available(self):
        self.assertEqual(check("I don't know enough about Lumen Harbor to assess its pacing."), [])

    def test_quoted_example_is_not_a_work_property(self):
        self.assertEqual(check('The phrase "measured pacing" would need an actual basis.'), [])

    def test_appraisal_projection_does_not_create_research_or_consumption(self):
        self.assertTrue(check("I've read it. It has measured pacing.", research_evidence=researched()))


if __name__ == "__main__":
    unittest.main()
