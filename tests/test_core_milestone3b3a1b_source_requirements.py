"""Current USER source obligations survive natural identity and honesty forms.

These obligations refine generated-public shadow evaluation. They do not grant
source authority or change lookup, publication, or research permission behaviour.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.public_source_requirements import public_source_requirements


class ExactIdentityRequirementsTests(unittest.TestCase):
    def test_interrogative_link_identity(self):
        for text in ("Which link is that from?", "Which source is this from?",
                     "What URL did that come from?", "Which page did you use?",
                     "What link was the excerpt from?"):
            with self.subTest(text=text):
                self.assertTrue(public_source_requirements(text)["exact_source_required"])

    def test_official_modifier_does_not_hide_identity(self):
        value = public_source_requirements("Which official link did you use?")
        self.assertTrue(value["exact_source_required"])
        self.assertTrue(value["official_source_required"])

    def test_primary_modifier_does_not_hide_identity(self):
        value = public_source_requirements("What primary source was that from?")
        self.assertTrue(value["exact_source_required"])
        self.assertTrue(value["primary_source_required"])
        self.assertFalse(value["official_source_required"])

    def test_bounded_combined_identity_modifiers(self):
        value = public_source_requirements("Which exact official source link did you use?")
        self.assertTrue(value["exact_source_required"])
        self.assertTrue(value["official_source_required"])

    def test_source_code_is_not_a_citation_question(self):
        self.assertFalse(public_source_requirements("Which source code module implements sorting?")
                         ["exact_source_required"])

    def test_structural_link_subject_does_not_request_source_identity(self):
        self.assertFalse(public_source_requirements("Which link joins the two beams?")
                         ["exact_source_required"])

    def test_physical_heat_source_does_not_request_source_identity(self):
        self.assertFalse(public_source_requirements("What source of heat drives the chamber?")
                         ["exact_source_required"])

    def test_nonattribution_page_question_does_not_gain_identity_obligation(self):
        self.assertFalse(public_source_requirements("What page contains the exercise?")
                         ["exact_source_required"])

    def test_structural_link_use_is_not_document_attribution(self):
        self.assertFalse(public_source_requirements("Which link did you use to join the beams?")
                         ["exact_source_required"])

    def test_attribution_use_relation_remains_recognized(self):
        for text in ("Which link did you use?", "What source have you read?",
                     "What source was that from?", "What page did that originate from?",
                     "Which link did you cite for this answer?"):
            with self.subTest(text=text):
                self.assertTrue(public_source_requirements(text)["exact_source_required"])

    def test_unambiguous_url_question_remains_identity_obligation(self):
        self.assertTrue(public_source_requirements("What URL did you consult?")
                        ["exact_source_required"])

    def test_source_identity_does_not_imply_actual_read(self):
        self.assertFalse(public_source_requirements("Which source link was that from?")
                         ["source_read_required"])

    def test_prior_first_person_source_report_is_not_current_identity(self):
        value = public_source_requirements("I used the official source URL yesterday.")
        self.assertFalse(value["exact_source_required"])
        self.assertFalse(value["official_source_required"])

    def test_quoted_identity_question_is_not_current_obligation(self):
        value = public_source_requirements('"Which official link did you use?"')
        self.assertFalse(value["exact_source_required"])
        self.assertFalse(value["official_source_required"])

    def test_reported_identity_question_is_not_current_obligation(self):
        self.assertFalse(public_source_requirements("Someone asked which official link did you use?")
                         ["exact_source_required"])

    def test_requested_address_preserves_scheme_path_query(self):
        value = public_source_requirements(
            "Give the exact source URL https://docs.vendor.example/reference?edition=4.")
        self.assertEqual(value["requested_source_urls"],
                         ("https://docs.vendor.example/reference?edition=4",))

    def test_source_identity_does_not_guess_an_address(self):
        self.assertEqual(public_source_requirements("Which official link did you use?")
                         ["requested_source_urls"], ())


class ConditionalReadHonestyTests(unittest.TestCase):
    def test_negative_read_condition_requires_disclosure(self):
        self.assertTrue(public_source_requirements("If you did not read it, say that.")
                        ["source_read_required"])

    def test_negative_load_condition_requires_disclosure(self):
        self.assertTrue(public_source_requirements("If you didn't actually load it, say so.")
                        ["source_read_required"])

    def test_typographic_negative_contraction(self):
        self.assertTrue(public_source_requirements("If you didn’t check it, tell me that.")
                        ["source_read_required"])

    def test_perfect_negative_read(self):
        self.assertTrue(public_source_requirements("If you have not read the page, admit it.")
                        ["source_read_required"])

    def test_perfect_negative_loaded(self):
        self.assertTrue(public_source_requirements("If you haven't actually loaded the document, acknowledge that.")
                        ["source_read_required"])

    def test_typographic_perfect_negative_checked(self):
        self.assertTrue(public_source_requirements("If you haven’t checked the source, make it clear.")
                        ["source_read_required"])

    def test_had_not_read_form(self):
        self.assertTrue(public_source_requirements("If you had not consulted the source, be honest about that.")
                        ["source_read_required"])

    def test_polite_honesty_consequent(self):
        self.assertTrue(public_source_requirements("If you didn't inspect the page, please say so.")
                        ["source_read_required"])

    def test_directive_modal_honesty_consequent(self):
        self.assertTrue(public_source_requirements("If you did not review the source, you should admit it.")
                        ["source_read_required"])

    def test_anaphoric_plural_target(self):
        self.assertTrue(public_source_requirements("If you didn't open them, say that.")
                        ["source_read_required"])

    def test_target_url_is_preserved(self):
        value = public_source_requirements(
            "If you didn't load https://docs.vendor.example/spec, say so.")
        self.assertTrue(value["source_read_required"])
        self.assertTrue(value["exact_source_required"])
        self.assertEqual(value["requested_source_urls"], ("https://docs.vendor.example/spec",))

    def test_target_url_query_and_fragment_remain_distinct(self):
        value = public_source_requirements(
            "If you didn't load https://docs.vendor.example/spec?edition=4#details, say so.")
        self.assertTrue(value["source_read_required"])
        self.assertEqual(value["requested_source_urls"],
                         ("https://docs.vendor.example/spec?edition=4#details",))

    def test_identity_and_conditional_obligations_coexist(self):
        value = public_source_requirements(
            "Which official link is that from? And if you didn't actually load it, say that.")
        self.assertTrue(value["exact_source_required"])
        self.assertTrue(value["official_source_required"])
        self.assertTrue(value["source_read_required"])

    def test_comma_conjunction_keeps_both_obligations(self):
        value = public_source_requirements(
            "What exact source did you use, and if you have not checked it, tell me that.")
        self.assertTrue(value["exact_source_required"])
        self.assertTrue(value["source_read_required"])

    def test_conditional_official_source_is_not_read_prohibition(self):
        value = public_source_requirements("If you do not check the official page, say that.")
        self.assertTrue(value["source_read_required"])
        self.assertTrue(value["official_source_required"])

    def test_primary_honesty_requirement_retains_primary_flag(self):
        value = public_source_requirements("If you haven't read the primary source, be explicit.")
        self.assertTrue(value["source_read_required"])
        self.assertTrue(value["primary_source_required"])


class NonRequestProtectionTests(unittest.TestCase):
    def test_positive_hypothetical_does_not_require_actual_read(self):
        self.assertFalse(public_source_requirements("If you read the manual, explain it.")
                         ["source_read_required"])

    def test_negative_hypothetical_without_honesty_consequent_is_not_request(self):
        self.assertFalse(public_source_requirements("If you didn't read it, the hypothetical response would change.")
                         ["source_read_required"])

    def test_negative_hypothetical_cannot_smuggle_source_authority(self):
        value = public_source_requirements("If you didn't read the official page, imagine an answer.")
        self.assertFalse(value["source_read_required"])
        self.assertFalse(value["official_source_required"])

    def test_explicit_hypothetical_frame_is_not_real_read_honesty(self):
        for text in ("Imagine an exchange, if you did not read the page, say that.",
                     "Hypothetically, if you did not load it, say so.",
                     "Suppose this is a rehearsal, if you have not checked the source, admit it."):
            with self.subTest(text=text):
                self.assertFalse(public_source_requirements(text)["source_read_required"])

    def test_quoted_conditional_is_not_fresh_request(self):
        self.assertFalse(public_source_requirements('"If you did not read it, say that."')
                         ["source_read_required"])

    def test_reported_conditional_is_not_fresh_request(self):
        self.assertFalse(public_source_requirements("Someone said if you did not load it, say that.")
                         ["source_read_required"])

    def test_first_person_reported_conditional_is_not_fresh_request(self):
        self.assertFalse(public_source_requirements("I said if you did not load it, say that.")
                         ["source_read_required"])

    def test_arbitrary_state_check_is_not_source_read_honesty(self):
        self.assertFalse(public_source_requirements("If you did not check my balance, say that.")
                         ["source_read_required"])

    def test_future_read_condition_does_not_create_retrospective_claim(self):
        self.assertFalse(public_source_requirements("If you will read the page tomorrow, say that.")
                         ["source_read_required"])

    def test_negated_honesty_consequent_is_not_disclosure_request(self):
        self.assertFalse(public_source_requirements("If you did not read it, don't say that.")
                         ["source_read_required"])

    def test_unbounded_honesty_factual_tail_does_not_enter_family(self):
        self.assertFalse(public_source_requirements("If you did not load it, say so and claim the system is safe.")
                         ["source_read_required"])

    def test_prohibition_is_not_read_requirement(self):
        value = public_source_requirements("Do not read the official page.")
        self.assertFalse(value["source_read_required"])
        self.assertFalse(value["official_source_required"])

    def test_no_need_to_read_is_not_read_requirement(self):
        value = public_source_requirements("There is no need to check the official source.")
        self.assertFalse(value["source_read_required"])
        self.assertFalse(value["official_source_required"])

    def test_source_authority_never_appears_as_proof(self):
        value = public_source_requirements("Which official link did you use?")
        self.assertEqual(set(value), {"source_read_required", "official_source_required",
                                     "primary_source_required", "exact_source_required",
                                     "requested_source_urls"})

    def test_nontext_input_is_safe(self):
        self.assertFalse(public_source_requirements(None)["source_read_required"])

    def test_informal_second_person_retains_the_same_source_obligations(self):
        for text in (
            "Could u inspect the official archive page?",
            "If u didn't read that page, be explicit about it.",
            "If u haven't checked it, say so.",
        ):
            with self.subTest(text=text):
                self.assertTrue(public_source_requirements(text)["source_read_required"])
        self.assertTrue(public_source_requirements("Which link did u use?")["exact_source_required"])
        self.assertFalse(public_source_requirements('"If u did not read it, say so."')["source_read_required"])
        self.assertFalse(public_source_requirements("Suppose u checked a page.")["source_read_required"])


if __name__ == "__main__":
    unittest.main()
