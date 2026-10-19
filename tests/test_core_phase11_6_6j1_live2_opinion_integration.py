"""Production retry/source paths enforce the same unknown-work property ceiling."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_core_phase11_6_6g_opinion_knowledge import SUBJECT, packet
from test_core_phase11_6_6g_opinion_knowledge_integration import Client, run


LIMIT = "I don't know enough about Silver Orchard to give an informed take."


class OpinionPropertyProductionTests(unittest.TestCase):
    def assert_retry(self, bad, *, conversation=(), overrides=None):
        client = Client([bad, LIMIT])
        result = run(client, conversation=conversation, overrides=overrides)
        self.assertEqual(result[0], LIMIT)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": LIMIT})
        self.assertNotIn(bad, [item["content"] for item in result[1]])
        self.assertEqual(len(client.generation_calls()), 2)
        return client, result

    def test_arbitrary_experience_appraisal_cannot_publish_from_model_memory(self):
        self.assert_retry("It's an arresting read.")

    def test_attributive_property_cannot_publish_from_model_memory(self):
        self.assert_retry("It has meticulous world-building.")

    def test_update_consistency_cannot_publish_from_model_memory(self):
        self.assert_retry("It has regular updates.")

    def test_quality_preservation_cannot_publish_from_model_memory(self):
        self.assert_retry("The artwork holds up.")

    def test_positive_global_verifier_does_not_override_projected_properties(self):
        self.assert_retry("I think it's an arresting read with measured pacing.")

    def test_mixed_property_list_is_not_hidden_by_a_first_person_qualifier(self):
        self.assert_retry("From what I know, it has measured pacing, unusual controls and regular updates.")

    def test_same_unknown_ceiling_applies_on_every_bounded_retry(self):
        drafts = ["It's an arresting read.", "It has measured pacing.", "The artwork holds up."]
        client = Client(drafts)
        result = run(client)
        self.assertEqual(len(client.generation_calls()), 3)
        self.assertNotIn(result[0], drafts)
        self.assertIn("don't know enough", result[0])
        self.assertTrue(all(text not in [item["content"] for item in result[1]] for text in drafts))

    def test_assistant_prior_appraisal_is_not_a_basis(self):
        self.assert_retry("It has measured pacing.", conversation=[
            {"role": "assistant", "content": SUBJECT + " has measured pacing."}])

    def test_user_property_can_be_discussed_without_forcing_research(self):
        good = "According to you, it has measured pacing."
        calls = []
        client = Client([good])
        result = run(client, conversation=[{"role": "user", "content": SUBJECT + " has measured pacing."}],
                     overrides={"build_spoiler_safe_media_evidence": lambda **kwargs: calls.append(kwargs)})
        self.assertEqual(result[0], good)
        self.assertEqual(len(client.generation_calls()), 1)
        self.assertFalse(calls)

    def test_latest_user_correction_cannot_be_overwritten_by_model_appraisal(self):
        self.assert_retry("It has measured pacing.", conversation=[
            {"role": "user", "content": SUBJECT + " has measured pacing."},
            {"role": "user", "content": "Correction: " + SUBJECT + "'s pacing is not measured."}])

    def test_real_admitted_subject_research_still_uses_ordinary_source_verifier(self):
        text = "It has measured pacing and meticulous world-building."
        evidence = packet(content=SUBJECT + " has measured pacing and meticulous world-building.")
        client = Client([text])
        result = run(client, retained_media=evidence)
        self.assertEqual(result[0], text)
        self.assertEqual(len(client.generation_calls()), 1)
        self.assertEqual(len(client.calls_of("INTERNAL factual-support verifier")), 1)

    def test_researched_familiarity_does_not_override_negative_source_verdict(self):
        text = "It has meticulous world-building."
        client = Client([text] * 2, media_supported=False)
        result = run(client, retained_media=packet())
        self.assertNotEqual(result[0], text)
        self.assertEqual(len(client.generation_calls()), 2)
        self.assertEqual(len(client.calls_of("INTERNAL factual-support verifier")), 2)

    def test_generic_conditional_discussion_stays_available_without_research(self):
        text = "If it has measured pacing, I might enjoy it."
        client = Client([text])
        result = run(client)
        self.assertEqual(result[0], text)
        self.assertEqual(len(client.generation_calls()), 1)
        self.assertEqual(len(client.calls_of("INTERNAL factual-support verifier")), 0)

    def test_existing_assistant_preference_does_not_license_new_property(self):
        subject = {"kind": "overall_opinion", "key": "silver_orchard::overall_opinion", "title": SUBJECT}
        entry = {"key": subject["key"], "kind": "overall_opinion", "stance_text": "I like Silver Orchard."}
        self.assert_retry("I like it because it has measured pacing.", overrides={
            "classify_opinion_subject": lambda **kwargs: subject,
            "get_or_recover_opinion_entry": lambda **kwargs: entry,
        })

    def test_genuine_existing_assistant_preference_remains_available(self):
        subject = {"kind": "overall_opinion", "key": "silver_orchard::overall_opinion", "title": SUBJECT}
        entry = {"key": subject["key"], "kind": "overall_opinion", "stance_text": "I like Silver Orchard."}
        text = "I still like Silver Orchard."
        client = Client([text])
        result = run(client, overrides={
            "classify_opinion_subject": lambda **kwargs: subject,
            "get_or_recover_opinion_entry": lambda **kwargs: entry,
        })
        self.assertEqual(result[0], text)
        self.assertEqual(len(client.generation_calls()), 1)

    def test_truthful_limitation_needs_no_additional_model_or_research_loop(self):
        calls = []
        client = Client([LIMIT])
        result = run(client, overrides={
            "build_spoiler_safe_media_evidence": lambda **kwargs: calls.append(kwargs),
        })
        self.assertEqual(result[0], LIMIT)
        self.assertEqual(len(client.generation_calls()), 1)
        self.assertEqual(len(client.calls_of("INTERNAL claim-grounding verifier")), 1)
        self.assertEqual(len(client.calls), 2)
        self.assertFalse(calls)


if __name__ == "__main__":
    unittest.main()
