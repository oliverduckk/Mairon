"""Neutral knowledge-basis regressions; no live model, web, or stored persona."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.evidence import Evidence, EvidenceBundle, EvidenceKind, EvidenceStatus
from core.evidence_normalization import normalize_research_evidence
from core.opinion_knowledge import (
    find_opinion_knowledge_violations, has_admitted_work_research_basis, opinion_request_subject,
    project_work_appraisals,
)


SUBJECT = "Silver Orchard"
REQUEST = "What do you actually think of Silver Orchard? I want your own take."


def packet(*, subject=SUBJECT, rejected=False, readable=True, content=None, success=True):
    return {"success": success, "query": SUBJECT, "sources": [{
        "title": subject + " critical overview", "url": "https://research.example/silver-orchard",
        "source_id": "source-a", "read_success": readable,
        "accepted_as_evidence": not rejected, "quality_eligible": not rejected,
        "content_excerpt": (content or subject + " has measured pacing and clear prose.") if readable else "",
    }]}


def check(text, **kwargs):
    return find_opinion_knowledge_violations(REQUEST, text, **kwargs)


class OpinionKnowledgeTests(unittest.TestCase):
    def test_one_work_property_is_enough_to_require_a_basis(self):
        self.assertTrue(check("The pacing is uneven."))

    def test_writing_quality_is_a_property_even_without_word_style(self):
        self.assertTrue(check("The writing is consistent."))

    def test_does_not_drag_is_a_concrete_pacing_property(self):
        self.assertTrue(check("The writing doesn't drag."))

    def test_consumption_appraisal_requires_an_informed_basis(self):
        self.assertTrue(check("It's a decent read."))

    def test_visual_work_appraisal_is_not_free_model_memory(self):
        self.assertTrue(check("The animation is clumsy."))

    def test_game_work_appraisal_is_not_free_model_memory(self):
        self.assertTrue(check("The gameplay feels repetitive."))

    def test_appeal_explanation_is_a_work_specific_property(self):
        self.assertTrue(check("The appeal comes from its volume of content."))

    def test_story_property_is_not_a_pure_preference(self):
        self.assertTrue(check("The story is predictable."))

    def test_first_person_confidence_is_not_a_knowledge_basis(self):
        self.assertTrue(check("From what I know, the prose is clear."))

    def test_first_person_opinion_marker_is_not_a_property_witness(self):
        self.assertTrue(check("I think the pacing is steady."))

    def test_disclaimer_does_not_license_appended_properties(self):
        self.assertTrue(check("I haven't read it, but the writing is strong."))

    def test_uncertainty_sentence_does_not_license_next_sentence(self):
        self.assertTrue(check("I don't know enough about it. The plot is coherent."))

    def test_uncertainty_semicolon_does_not_hide_a_property(self):
        self.assertTrue(check("I don't know enough about it; the dialogue is excellent."))

    def test_uncertainty_comma_and_does_not_hide_a_property(self):
        self.assertTrue(check("I don't know enough about it, and the prose is clear."))

    def test_uncertainty_comma_finite_clause_does_not_hide_a_property(self):
        self.assertTrue(check("I don't know enough, the prose is clear."))

    def test_uncertainty_colon_finite_clause_does_not_hide_a_property(self):
        self.assertTrue(check("I'm not familiar: its prose is clear."))

    def test_unknown_whether_is_still_a_bounded_limitation(self):
        self.assertEqual(check("I don't know whether the prose is clear."), [])

    def test_truthful_limitation_remains_available(self):
        self.assertEqual(check("I don't know enough about Silver Orchard to give an informed take."), [])

    def test_request_for_details_is_not_familiarity(self):
        self.assertEqual(check("Is the pacing slow?"), [])

    def test_generic_conditional_preference_remains_available(self):
        self.assertEqual(check("If the character work is strong, I can enjoy a slower story."), [])

    def test_first_person_conditional_preference_remains_available(self):
        self.assertEqual(check("I would enjoy clear prose, but I don't know whether this has it."), [])

    def test_pure_subjective_prior_preference_remains_available(self):
        subject = {"key": "silver_orchard::overall_opinion", "title": SUBJECT, "kind": "overall_opinion"}
        entry = {"key": subject["key"], "stance_text": "I like Silver Orchard."}
        self.assertEqual(check(entry["stance_text"], opinion_subject=subject, opinion_entry=entry), [])

    def test_prior_stance_does_not_authorize_old_factual_reasons(self):
        subject = {"key": "silver_orchard::overall_opinion", "title": SUBJECT, "kind": "overall_opinion"}
        text = "I like Silver Orchard because the prose is clear."
        entry = {"key": subject["key"], "stance_text": text}
        self.assertTrue(check(text, opinion_subject=subject, opinion_entry=entry))

    def test_assistant_history_is_not_subject_familiarity(self):
        history = [{"role": "assistant", "content": "Silver Orchard's writing is consistent."}]
        self.assertTrue(check("The writing is consistent.", conversation=history))

    def test_candidate_claim_of_prior_research_is_not_evidence(self):
        self.assertTrue(check("I researched it thoroughly. The prose is clear."))

    def test_matching_named_user_property_can_be_used_with_user_scope(self):
        history = [{"role": "user", "content": "In Silver Orchard, the writing is consistent."}]
        self.assertEqual(check("The writing is consistent.", conversation=history), [])

    def test_dimension_mention_does_not_authorize_property(self):
        history = [{"role": "user", "content": "Tell me about Silver Orchard's writing."}]
        self.assertTrue(check("The writing is consistent.", conversation=history))

    def test_topic_overlap_does_not_authorize_property(self):
        history = [{"role": "user", "content": "I like Silver Orchard."}]
        self.assertTrue(check("The writing is consistent.", conversation=history))

    def test_user_question_does_not_supply_a_property(self):
        history = [{"role": "user", "content": "Is Silver Orchard's prose clear?"}]
        self.assertTrue(check("The prose is clear.", conversation=history))

    def test_user_property_polarity_is_preserved(self):
        history = [{"role": "user", "content": "Silver Orchard's prose is not clear."}]
        self.assertTrue(check("The prose is clear.", conversation=history))

    def test_user_property_tense_is_preserved(self):
        history = [{"role": "user", "content": "Silver Orchard's prose was clear."}]
        self.assertTrue(check("The prose is clear.", conversation=history))

    def test_different_work_user_property_is_not_familiarity(self):
        history = [{"role": "user", "content": "Copper Atlas's prose is clear."}]
        self.assertTrue(check("The prose is clear.", conversation=history))

    def test_latest_named_user_correction_supersedes_prior_property(self):
        history = [{"role": "user", "content": "Silver Orchard's prose is clear."},
                   {"role": "user", "content": "Correction: Silver Orchard's prose is not clear."}]
        self.assertTrue(check("The prose is clear.", conversation=history))
        self.assertEqual(check("The prose is not clear.", conversation=history), [])

    def test_subject_matching_readable_research_uses_existing_source_verifier(self):
        self.assertEqual(check("The prose is clear.", research_evidence=packet()), [])

    def test_canonical_media_research_has_the_same_basis(self):
        evidence = normalize_research_evidence(packet(), kind=EvidenceKind.MEDIA_SOURCE)
        self.assertEqual(check("The prose is clear.", research_evidence=evidence), [])

    def test_canonical_public_research_has_the_same_basis(self):
        evidence = normalize_research_evidence(packet(), kind=EvidenceKind.PUBLIC_SOURCE)
        self.assertEqual(check("The prose is clear.", research_evidence=evidence), [])

    def test_unsupported_body_subject_does_not_pass_from_query_or_title(self):
        evidence = packet(content="Copper Atlas has clear prose.")
        self.assertTrue(check("The prose is clear.", research_evidence=evidence))

    def test_rejected_research_is_not_familiarity(self):
        self.assertTrue(check("The prose is clear.", research_evidence=packet(rejected=True)))

    def test_unread_source_is_not_familiarity(self):
        self.assertTrue(check("The prose is clear.", research_evidence=packet(readable=False)))

    def test_global_research_failure_is_not_familiarity(self):
        self.assertTrue(check("The prose is clear.", research_evidence=packet(success=False)))

    def test_malformed_research_is_not_familiarity(self):
        self.assertTrue(check("The prose is clear.", research_evidence="model says it researched Silver Orchard"))

    def test_model_knowledge_permission_is_not_subject_evidence(self):
        evidence = EvidenceBundle(authority="model", canonical=True, success=True, evidence=[Evidence(
            claim="", provenance="core", confidence="permission",
            kind=EvidenceKind.STABLE_MODEL_KNOWLEDGE_PERMISSION, status=EvidenceStatus.ADMISSIBLE,
        )]).snapshot()
        self.assertTrue(check("The prose is clear.", research_evidence=evidence))

    def test_optional_packet_tuple_preserves_available_real_basis(self):
        self.assertEqual(check("The prose is clear.", research_evidence=(None, packet())), [])

    def test_current_subject_cannot_be_overridden_by_an_unrelated_ledger_hint(self):
        other = {"kind": "overall_opinion", "title": "Copper Atlas"}
        self.assertEqual(opinion_request_subject(REQUEST, other), SUBJECT)

    def test_subject_wrapper_can_use_matching_core_title(self):
        subject = {"kind": "overall_opinion", "title": "Amber Archive"}
        self.assertEqual(opinion_request_subject("What do you think of the novel Amber Archive?", subject),
                         "Amber Archive")

    def test_subject_wrapper_does_not_use_an_unrelated_hint(self):
        subject = {"kind": "overall_opinion", "title": "Copper Atlas"}
        self.assertEqual(opinion_request_subject("What do you think of the novel Amber Archive?", subject),
                         "the novel Amber Archive")

    def test_research_basis_capability_does_not_accept_a_candidate(self):
        self.assertTrue(has_admitted_work_research_basis(REQUEST, packet()))
        self.assertFalse(has_admitted_work_research_basis(REQUEST, packet(rejected=True)))

    def test_positive_named_consumption_is_not_licensed_by_research(self):
        self.assertTrue(check("I've read Silver Orchard.", research_evidence=packet()))

    def test_positive_quoted_named_consumption_is_not_licensed_by_research(self):
        self.assertTrue(check('I read "Silver Orchard".', research_evidence=packet()))

    def test_positive_watched_work_is_not_licensed_by_research(self):
        self.assertTrue(check("I watched it.", research_evidence=packet()))

    def test_positive_played_work_is_not_licensed_by_research(self):
        self.assertTrue(check("I played it.", research_evidence=packet()))

    def test_positive_finished_work_is_not_licensed_by_research(self):
        self.assertTrue(check("I finished reading it.", research_evidence=packet()))

    def test_negative_consumption_disclaimer_remains_valid(self):
        self.assertEqual(check("I haven't read Silver Orchard, so I can't give a real take."), [])

    def test_quoted_consumption_claim_is_not_assistant_experience(self):
        self.assertEqual(check('Someone said "I read it." I don\'t know enough myself.'), [])

    def test_user_consumption_does_not_grant_assistant_consumption(self):
        history = [{"role": "user", "content": "I've read Silver Orchard."}]
        self.assertTrue(check("I've read Silver Orchard.", conversation=history))

    def test_other_request_forms_are_general(self):
        self.assertTrue(find_opinion_knowledge_violations(
            "What's your honest view of Amber Archive?", "The prose is clear."))

    def test_non_work_abstract_opinion_is_outside_this_guard(self):
        self.assertEqual(find_opinion_knowledge_violations(
            "I think patient decisions can be better than quick ones if the stakes are high.",
            "That trade-off makes sense to me."), [])

    def test_obligations_are_frozen_projections_not_claim_authority(self):
        items = project_work_appraisals("The writing is consistent.")
        self.assertEqual(items[0].dimension, "writing")
        self.assertEqual(items[0].predicate, "is consistent")
        with self.assertRaises(AttributeError):
            items[0].predicate = "is verified"


if __name__ == "__main__":
    unittest.main()
