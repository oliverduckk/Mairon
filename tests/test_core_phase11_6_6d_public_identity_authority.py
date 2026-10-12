"""Literal public identity and date roles cannot be acquired by model approval."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_core_phase11_6_6c_public_content_authority import Client, packet, verdict
from research.public_claim_obligations import public_identity_date_obligations, public_identity_date_failures
from research.public_factual_grounding import verify_public_factual_draft, build_public_factual_retry_instruction


def check(text, *, body='The preview is titled "Avery Morgan".', title='[April 7] "Avery Morgan" Preview', **state):
    retained = packet(body=body, title=title, **state)
    client = Client(verdict(sentences=len(text.split("\n"))))
    result = verify_public_factual_draft(client, "replaceable-model", "What was the preview called?", text,
                                        json.dumps(retained))
    return result, client


class PublicIdentityAuthorityTests(unittest.TestCase):
    def test_full_name_cannot_become_conjoined_title(self):
        result, _ = check('The preview is titled "Avery & Morgan".')
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)

    def test_word_conjunction_cannot_split_title(self):
        result, _ = check('The preview is called "Avery and Morgan".')
        self.assertTrue(result)

    def test_disjunction_cannot_split_title(self):
        result, _ = check('The preview is called "Avery or Morgan".')
        self.assertTrue(result)

    def test_slash_cannot_split_title(self):
        result, _ = check('The preview is called "Avery/Morgan".')
        self.assertTrue(result)

    def test_plus_cannot_split_title(self):
        result, _ = check('The preview is called "Avery + Morgan".')
        self.assertTrue(result)

    def test_comma_cannot_split_title(self):
        result, _ = check('The preview is called "Avery, Morgan".')
        self.assertTrue(result)

    def test_colon_cannot_split_title(self):
        result, _ = check('The preview is called "Avery: Morgan".')
        self.assertTrue(result)

    def test_dash_cannot_split_title(self):
        result, _ = check('The preview is called "Avery — Morgan".')
        self.assertTrue(result)

    def test_unquoted_entity_split_still_fails(self):
        result, _ = check('The preview is titled Avery & Morgan.')
        self.assertTrue(result)
        self.assertIn("entity_identity_split", " ".join(result))

    def test_unquoted_title_cannot_be_supported_by_same_tokens_in_body_mention(self):
        result, _ = check("The preview is titled Cora & Dax.",
                          body="Cora & Dax appear in the list of contributors.", title="Preview")
        self.assertTrue(result)
        self.assertIn("literal_identity_witness_missing", " ".join(result))

    def test_actual_body_unquoted_title_supports_same_title(self):
        text = "The preview is titled Cora & Dax."
        result, _ = check(text, body=text, title="Preview")
        self.assertFalse(result)

    def test_quoted_body_title_supports_equivalent_unquoted_rendering(self):
        result, _ = check("The preview is titled Cora & Dax.", body='The preview is titled "Cora & Dax".', title="Preview")
        self.assertFalse(result)

    def test_unquoted_body_title_supports_equivalent_quoted_rendering(self):
        result, _ = check('The preview is titled "Cora & Dax".', body="The preview is titled Cora & Dax.", title="Preview")
        self.assertFalse(result)

    def test_unquoted_word_conjunction_cannot_mutate_retained_name(self):
        result, _ = check("The preview is titled Avery and Morgan.")
        self.assertTrue(result)

    def test_curly_single_quoted_full_name_cannot_be_truncated(self):
        result, _ = check('The preview is titled "Avery".', title="‘Avery Morgan’ Preview", body="A preview exists.")
        self.assertTrue(result)

    def test_curly_single_quoted_identity_can_remain_exact(self):
        result, _ = check('The preview is titled "Avery Morgan".', title="‘Avery Morgan’ Preview", body="A preview exists.")
        self.assertFalse(result)

    def test_exact_title_preserves_name_span(self):
        text = 'The preview is titled "Avery Morgan".'
        result, client = check(text)
        self.assertFalse(result)
        self.assertEqual(result.accepted_sentences, [text])
        self.assertEqual(len(client.calls), 1)

    def test_typographic_outer_quotes_and_casing_are_harmless(self):
        result, _ = check('The preview is titled “avery morgan”.')
        self.assertFalse(result)

    def test_typographic_apostrophe_inside_identity_is_harmless(self):
        result, _ = check('The preview is titled “Avery’s Chronicle”.', title='"Avery\'s Chronicle" Preview')
        self.assertFalse(result)

    def test_genuine_multi_participant_title_metadata_is_literal_identity_evidence(self):
        result, _ = check('The preview is titled "Cora & Dax".', title='"Cora & Dax" Preview')
        self.assertFalse(result)

    def test_genuine_multi_participant_title_body_is_literal_identity_evidence(self):
        text = 'The preview is called "Cora & Dax".'
        result, _ = check(text, body=text, title="Preview index")
        self.assertFalse(result)

    def test_body_title_does_not_have_to_equal_whole_source_heading(self):
        text = 'The archive item is named "Cora & Dax".'
        result, _ = check(text, body='The archive item is named "Cora & Dax". A description follows.', title="Archive")
        self.assertFalse(result)

    def test_body_mention_does_not_authorize_item_title(self):
        result, _ = check('The preview is titled "Cora & Dax".',
                          body="Cora & Dax appear in the list of contributors.", title="Preview")
        self.assertTrue(result)

    def test_other_object_title_is_not_requested_object_identity(self):
        result, _ = check('The episode is titled "Cora & Dax".',
                          body='The article is titled "Cora & Dax".', title="Article archive")
        self.assertTrue(result)

    def test_single_name_cannot_truncate_quoted_full_name_identity(self):
        result, _ = check('The preview is titled "Avery".')
        self.assertTrue(result)

    def test_unrelated_substring_of_quoted_title_is_not_exact_title(self):
        result, _ = check('The preview is titled "Silver".', title='"Silver Harbour" Preview', body="A preview exists.")
        self.assertTrue(result)

    def test_search_snippet_alone_cannot_authorize_rewritten_title(self):
        result, _ = check('The preview is called "Avery & Morgan".', search_snippet='The preview is called "Avery & Morgan".')
        self.assertTrue(result)

    def test_rejected_source_cannot_prove_title(self):
        text = 'The preview is called "Cora & Dax".'
        result, _ = check(text, body=text, title='"Cora & Dax"', accepted_as_evidence=False)
        self.assertTrue(result)

    def test_unreadable_source_cannot_prove_title(self):
        text = 'The preview is called "Cora & Dax".'
        result, _ = check(text, body=text, title='"Cora & Dax"', read_success=False)
        self.assertTrue(result)

    def test_unavailable_source_cannot_prove_title(self):
        text = 'The preview is called "Cora & Dax".'
        result, _ = check(text, body=text, title='"Cora & Dax"', relevance_status="unavailable")
        self.assertTrue(result)

    def test_duplicate_source_ids_do_not_prove_title(self):
        retained = packet()
        retained["sources"].append(copy.deepcopy(retained["sources"][0]))
        result = verify_public_factual_draft(Client(verdict()), "model", "What is it called?",
                'The preview is titled "Avery Morgan".', json.dumps(retained))
        self.assertTrue(result)

    def test_body_question_is_not_title_assertion(self):
        result, _ = check('The preview is called "Cora & Dax".', body='Is the preview called "Cora & Dax"?', title="Preview")
        self.assertTrue(result)

    def test_body_negation_does_not_support_positive_identity(self):
        result, _ = check('The preview is called "Cora & Dax".', body='The preview is not called "Cora & Dax".', title="Preview")
        self.assertTrue(result)

    def test_body_conditional_does_not_support_actual_title(self):
        result, _ = check('The preview is called "Cora & Dax".', body='If the preview is called "Cora & Dax", the record changes.', title="Preview")
        self.assertTrue(result)

    def test_global_positive_cannot_override_identity_failure(self):
        result, _ = check('The preview is titled "Avery & Morgan".')
        self.assertTrue(result.verification_state["global_supported"])
        self.assertFalse(result.verification_state["effective_supported"])

    def test_identity_failure_cannot_be_salvaged(self):
        good = "A preview exists."
        bad = 'The preview is titled "Avery & Morgan".'
        result, _ = check(good + "\n" + bad)
        self.assertEqual(result.accepted_sentences, [good])

    def test_source_preview_label_is_not_episode_air_date(self):
        result, _ = check("The episode aired on April 7, 2028.", title='[April 7, 2028] Episode 12 "Avery Morgan" Preview')
        self.assertTrue(result)
        self.assertIn("event_date_role_witness_missing", " ".join(result))

    def test_source_publication_date_is_not_item_release_date(self):
        result, _ = check("The package was released on April 7, 2028.", published_date="2028-04-07")
        self.assertTrue(result)

    def test_title_explicit_release_claim_still_needs_body_relation(self):
        text = "Aurora was released on April 7, 2028."
        result, _ = check(text, title=text)
        self.assertTrue(result)

    def test_actual_body_air_date_passes(self):
        text = "The episode aired on April 7, 2028."
        result, _ = check(text, body=text)
        self.assertFalse(result)

    def test_actual_body_release_date_passes(self):
        text = "Aurora was released on April 7, 2028."
        result, _ = check(text, body=text)
        self.assertFalse(result)

    def test_actual_body_posting_date_passes(self):
        text = "The preview was posted on April 7, 2028."
        result, _ = check(text, body=text)
        self.assertFalse(result)

    def test_relative_event_date_without_resolvable_date_fails(self):
        result, _ = check("The preview dropped around then.")
        self.assertTrue(result)
        self.assertIn("event_date_reference_unresolved", " ".join(result))

    def test_relative_preview_date_cannot_be_borrowed_from_metadata_label(self):
        text = "The article was published on April 7, 2028.\nThe preview dropped around then."
        result, _ = check(text, published_date="2028-04-07", title='[April 7, 2028] "Avery Morgan" Preview')
        self.assertTrue(result)
        self.assertEqual(result.accepted_sentences, ["The article was published on April 7, 2028."])

    def test_relative_preview_date_has_actual_matching_body_event_witness(self):
        text = "The article was published on April 7, 2028.\nThe preview dropped around then."
        result, _ = check(text, published_date="2028-04-07", body="The preview dropped on April 7, 2028.")
        self.assertFalse(result)

    def test_actual_relative_body_relation_resolves_its_own_body_date_context(self):
        text = "The article was published on April 7, 2028.\nThe preview was posted around then."
        body = "The article was published on April 7, 2028. The preview was posted then."
        result, _ = check(text, body=body)
        self.assertFalse(result)

    def test_relative_same_sentence_date_remains_actual_body_supported(self):
        text = "Aurora was released on April 7, 2028, and the preview dropped then."
        result, _ = check(text, body=text)
        self.assertFalse(result)

    def test_relative_date_cannot_convert_air_date_to_posting_date(self):
        text = "The article was published on April 7, 2028.\nThe preview was posted around then."
        result, _ = check(text, published_date="2028-04-07", body="The preview aired on April 7, 2028.")
        self.assertTrue(result)

    def test_relative_date_cannot_borrow_different_item_subject(self):
        text = "The article was published on April 7, 2028.\nAurora was released around then."
        result, _ = check(text, published_date="2028-04-07", body="Borealis was released on April 7, 2028.")
        self.assertTrue(result)

    def test_posting_date_cannot_support_air_date(self):
        result, _ = check("The episode aired on April 7, 2028.", body="The preview was posted on April 7, 2028.")
        self.assertTrue(result)

    def test_air_date_cannot_support_release_date(self):
        result, _ = check("The package was released on April 7, 2028.", body="The package aired on April 7, 2028.")
        self.assertTrue(result)

    def test_date_of_different_subject_cannot_support_requested_item(self):
        result, _ = check("Aurora was released on April 7, 2028.", body="Borealis was released on April 7, 2028.")
        self.assertTrue(result)

    def test_pronoun_cannot_borrow_date_of_other_named_item(self):
        result, _ = check("It was released on April 7, 2028.",
                          body="Borealis was released on April 7, 2028.", title='"Aurora" Release notice')
        self.assertTrue(result)

    def test_pronoun_same_retained_quoted_identity_with_actual_body_date_passes(self):
        result, _ = check("It was released on April 7, 2028.",
                          body="Aurora was released on April 7, 2028.", title='"Aurora" Release notice')
        self.assertFalse(result)

    def test_pronoun_same_retained_numbered_item_with_actual_body_date_passes(self):
        result, _ = check("It aired on April 7, 2028.",
                          body="Episode 12 aired on April 7, 2028.", title='[April 7, 2028] Episode 12 Preview')
        self.assertFalse(result)

    def test_pronoun_different_retained_numbered_item_cannot_borrow_date(self):
        result, _ = check("It aired on April 7, 2028.",
                          body="Episode 15 aired on April 7, 2028.", title='[April 7, 2028] Episode 12 Preview')
        self.assertTrue(result)

    def test_pronoun_unnumbered_unknown_identity_cannot_manufacture_scope(self):
        result, _ = check("It was released on April 7, 2028.",
                          body="Aurora was released on April 7, 2028.", title="Release notice")
        self.assertTrue(result)

    def test_year_cannot_be_added_to_month_day_evidence(self):
        result, _ = check("Aurora was released on April 7, 2028.", body="Aurora was released on April 7.")
        self.assertTrue(result)

    def test_date_cannot_be_changed(self):
        result, _ = check("Aurora was released on April 8, 2028.", body="Aurora was released on April 7, 2028.")
        self.assertTrue(result)

    def test_iso_and_calendar_rendering_preserve_identical_body_date(self):
        result, _ = check("Aurora was released on April 7, 2028.", body="Aurora was released on 2028-04-07.")
        self.assertFalse(result)

    def test_ordinal_and_day_first_rendering_preserve_identical_body_date(self):
        result, _ = check("Aurora was released on April 7th, 2028.", body="Aurora was released on 7 April 2028.")
        self.assertFalse(result)

    def test_source_publication_role_can_use_actual_publication_metadata(self):
        result, _ = check("The article was published on April 7, 2028.", published_date="2028-04-07")
        self.assertFalse(result)

    def test_publication_metadata_cannot_authorize_publication_of_different_item(self):
        result, _ = check("Aurora was published on April 7, 2028.", published_date="2028-04-07")
        self.assertTrue(result)

    def test_conditional_body_date_is_not_actual_event_date(self):
        result, _ = check("Aurora was released on April 7, 2028.", body="If Aurora was released on April 7, 2028, the index would change.")
        self.assertTrue(result)

    def test_quoted_body_date_is_not_actual_event_date(self):
        result, _ = check("Aurora was released on April 7, 2028.", body='"Aurora was released on April 7, 2028."')
        self.assertTrue(result)

    def test_negative_body_date_does_not_support_positive_event(self):
        result, _ = check("Aurora was released on April 7, 2028.", body="Aurora was not released on April 7, 2028.")
        self.assertTrue(result)

    def test_global_positive_cannot_override_date_role_failure(self):
        result, _ = check("Aurora was released on April 7, 2028.")
        self.assertTrue(result.verification_state["global_supported"])
        self.assertFalse(result.verification_state["effective_supported"])

    def test_negative_event_date_requires_its_own_body_support(self):
        result, _ = check("Aurora was not released on April 7, 2028.")
        self.assertTrue(result)

    def test_body_supported_negative_event_date_passes(self):
        text = "Aurora was not released on April 7, 2028."
        result, _ = check(text, body=text)
        self.assertFalse(result)

    def test_actual_publication_metadata_cannot_support_negative_publication_claim(self):
        result, _ = check("The article was not published on April 7, 2028.", published_date="2028-04-07")
        self.assertTrue(result)

    def test_truthful_bounded_unknown_date_does_not_assert_target_date(self):
        text = "I cannot verify whether Aurora was released on April 7, 2028."
        result, _ = check(text)
        self.assertFalse(result)
        self.assertFalse(public_identity_date_obligations([text]))

    def test_bounded_unknown_date_cannot_hide_external_date_tail(self):
        text = "I cannot verify the preview, but Aurora was released on April 7, 2028."
        result, _ = check(text)
        self.assertTrue(result)

    def test_date_failure_excludes_only_its_sentence(self):
        good = 'The preview is titled "Avery Morgan".'
        result, _ = check(good + "\nThe episode aired on April 7, 2028.")
        self.assertEqual(result.accepted_sentences, [good])

    def test_obligations_are_immutable_in_retained_verifier_transport(self):
        result, _ = check('The preview is titled "Avery Morgan".')
        with self.assertRaises(TypeError):
            result.verification_state["identity_date_obligations"][0]["identity"] = "changed"

    def test_helper_does_not_mutate_evidence_or_obligations(self):
        retained = packet()
        obligations = public_identity_date_obligations(['The preview is titled "Avery & Morgan".'])
        before = copy.deepcopy(retained), copy.deepcopy(obligations)
        self.assertTrue(public_identity_date_failures(obligations, retained))
        self.assertEqual((retained, obligations), before)

    def test_existing_content_rejection_receives_retry_repair_instruction(self):
        instruction = build_public_factual_retry_instruction(["public factual content obligation unsupported: entity_identity_split: sentence=1"])
        self.assertIn("Remove unsupported details", instruction)


if __name__ == "__main__":
    unittest.main()
