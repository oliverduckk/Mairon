"""Literal topic/role refinements need actual USER relation witnesses."""
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    build_conversational_relation_obligations,
    validate_conversational_relation_assessments,
    verify_core_grounded_draft,
)


SOCIAL = AnswerContractRuntime(
    intent="casual_conversation", speech_act="statement", authority="live_conversation",
    epistemic_mode="conversation", allow_new_factual_claims=False,
)
EVENT_USER = "Ria's handling of the review has already annoyed me."
COMPLAINT = "You can consult the inventory. You should not need me to recite it."
POSITIVE = {"supported": True, "relevant": True, "source_faithful": True,
            "speech_act_faithful": True, "unsupported_claims": []}


class Client:
    def __init__(self, state):
        self.state = state
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.state)))


def packet(draft, *, user=EVENT_USER, conversation=(), contract=SOCIAL):
    return build_conversational_relation_obligations(
        user_input=user, draft=draft, core_answer_contract=contract, conversation=conversation)


def state_for(bundle, *, source_id="current_user", quote=None, predicate=None, supported=True):
    records = []
    for item in bundle["obligations"]:
        records.append({"index": item["index"], "supported": supported,
                        "source_id": source_id,
                        "source_quote": quote if quote is not None else bundle["sources"].get(source_id, ""),
                        "source_predicate": predicate if predicate is not None else item["predicate"]})
    return POSITIVE | {"relation_assessments": records}


def verify(state, draft, *, user=EVENT_USER, conversation=(), contract=SOCIAL):
    client = Client(state)
    with patch("core.claim_grounding.find_deterministic_grounding_violations", return_value=[]):
        outcome = verify_core_grounded_draft(
            client=client, model="qwen-test", user_input=user, draft=draft,
            core_answer_contract=contract, conversation=conversation)
    return outcome, client


class ConversationalRelationTests(unittest.TestCase):
    def test_topic_reaction_quote_cannot_supply_new_event_nominal(self):
        draft = "Ria's obstruction of the review was disgraceful."
        bundle = packet(draft)
        self.assertTrue(bundle["obligations"])
        outcome, _ = verify(state_for(bundle, predicate="handling"), draft)
        self.assertTrue(outcome)

    def test_positive_global_alone_cannot_supply_new_event_predicate(self):
        outcome, client = verify(POSITIVE, "Ria falsified the review.")
        self.assertTrue(outcome)
        self.assertEqual(len(client.calls), 1)
        self.assertIn("relation assessment", " ".join(outcome))

    def test_nominalisation_inside_evaluation_is_still_literal(self):
        bundle = packet("Ria's review obstruction feels like a disgrace.")
        self.assertEqual(bundle["obligations"][0]["predicate"], "review obstruction")
        self.assertTrue(any(item["kind"] == "event_evaluation" for item in bundle["obligations"]))

    def test_same_topic_with_new_moral_predicate_requires_witness(self):
        draft = "Ria's handling of the review feels like a disgrace."
        bundle = packet(draft)
        self.assertTrue(bundle["obligations"])
        self.assertTrue(verify(state_for(bundle), draft)[0])

    def test_unobserved_finite_action_requires_own_predicate(self):
        for draft in ("Ria falsified the review.", "She concealed the result.",
                      "Ria probably concealed the result.", "Her obstruction was effective."):
            with self.subTest(draft=draft):
                self.assertTrue(packet(draft)["obligations"])
                self.assertTrue(verify(POSITIVE, draft)[0])

    def test_finite_reference_does_not_authorise_an_added_event_verdict(self):
        for draft in ("Ria handled it badly.", "She handled it cruelly.", "Ria handled the review poorly.",
                      "She handled it well."):
            with self.subTest(draft=draft):
                bundle = packet(draft)
                self.assertTrue(any(item["kind"] == "event_evaluation" for item in bundle["obligations"]))
                self.assertTrue(verify(POSITIVE, draft)[0])

    def test_finite_reference_without_new_verdict_remains_a_trivial_reference(self):
        for draft in ("She handled it.", "You were annoyed with how she handled it."):
            with self.subTest(draft=draft):
                self.assertEqual(packet(draft)["obligations"], ())
                self.assertEqual(verify(POSITIVE, draft)[0], [])

    def test_copular_actor_evaluation_needs_its_own_user_witness(self):
        for draft in ("She was malicious.", "Ria is dishonest.", "Ria was careless."):
            with self.subTest(draft=draft):
                self.assertTrue(packet(draft)["obligations"])
                self.assertTrue(verify(POSITIVE, draft)[0])

    def test_user_pronoun_does_not_exempt_an_unsupported_consequence(self):
        draft = "Ria's handling is causing you to lose the review."
        self.assertTrue(packet(draft)["obligations"])
        self.assertTrue(verify(POSITIVE, draft)[0])

    def test_reaction_mirror_is_complete_and_cannot_hide_a_tail(self):
        good = "Ria's handling is clearly annoying you."
        bad = "Ria's handling is clearly annoying you because she concealed the result."
        self.assertEqual(packet(good)["obligations"], ())
        self.assertTrue(packet(bad)["obligations"])
        self.assertTrue(verify(POSITIVE, bad)[0])

    def test_event_verdict_is_not_exempt_inside_an_emotional_mirror(self):
        draft = "You're upset with how she handled it cruelly."
        self.assertTrue(packet(draft)["obligations"])
        self.assertTrue(verify(POSITIVE, draft)[0])

    def test_finite_verdict_with_explicit_user_witness_is_permitted(self):
        history = [{"role": "user", "content": "Ria handled it poorly."}]
        draft = "Ria handled it poorly."
        bundle = packet(draft, conversation=history)
        result, _ = verify(state_for(bundle, source_id="prior_user_1", predicate="handled it poorly"),
                           draft, conversation=history)
        self.assertEqual(result, [])

    def test_multiword_named_actor_identity_is_preserved(self):
        user = "Mara Vale's handling of the review annoyed me."
        draft = "Mara Vale concealed the result."
        bundle = packet(draft, user=user)
        self.assertEqual(bundle["obligations"][0]["actor"], "Mara Vale")
        self.assertTrue(verify(POSITIVE, draft, user=user)[0])

    def test_same_last_name_does_not_establish_named_actor_identity(self):
        user = "Mara Vale's handling of the review annoyed me."
        history = [{"role": "user", "content": "Taren Vale concealed the result."}]
        draft = "Mara Vale concealed the result."
        bundle = packet(draft, user=user, conversation=history)
        self.assertTrue(verify(state_for(bundle, source_id="prior_user_1", predicate="concealed"),
                               draft, user=user, conversation=history)[0])

    def test_safe_emotional_mirrors_keep_legacy_protocol(self):
        for draft in ("Yeah, you're clearly annoyed with how she handled it.",
                      "That handling clearly annoyed you.", "Ria's handling clearly annoyed you.",
                      "You're already fed up with that decision."):
            with self.subTest(draft=draft):
                self.assertEqual(packet(draft)["obligations"], ())
                outcome, client = verify(POSITIVE, draft)
                self.assertEqual(outcome, [])
                self.assertEqual(len(client.calls), 1)
                self.assertEqual(client.calls[0]["options"]["num_predict"], 160)

    def test_referenced_topic_is_not_an_external_event_ontology(self):
        for head in ("handling", "response", "reaction", "approach", "treatment", "decision"):
            user = f"Milo's {head} of that situation annoyed me."
            with self.subTest(head=head):
                self.assertTrue(packet("Milo concealed the result.", user=user)["obligations"])

    def test_external_predicate_can_be_backed_by_explicit_user_fact(self):
        prior = [{"role": "user", "content": "Ria obstructed the review."}]
        draft = "Ria obstructed the review."
        bundle = packet(draft, conversation=prior)
        result, _ = verify(state_for(bundle, source_id="prior_user_1", predicate="obstructed"),
                           draft, conversation=prior)
        self.assertEqual(result, [])

    def test_regular_event_nominal_morphology_preserves_supplied_predicate(self):
        prior = [{"role": "user", "content": "Ria manipulated the review."}]
        draft = "Ria's manipulation of the review."
        bundle = packet(draft, conversation=prior)
        result, _ = verify(state_for(bundle, source_id="prior_user_1", predicate="manipulated"),
                           draft, conversation=prior)
        self.assertEqual(result, [])

    def test_emotion_reference_does_not_block_explicit_uncertainty(self):
        draft = "I don't know whether Ria concealed anything; you're clearly annoyed."
        self.assertEqual(packet(draft)["obligations"], ())
        self.assertEqual(verify(POSITIVE, draft)[0], [])

    def test_denial_cannot_hide_an_appended_assertion(self):
        draft = "I cannot verify that Ria concealed it, but Ria falsified the result."
        bundle = packet(draft)
        self.assertEqual(len(bundle["obligations"]), 1)
        self.assertEqual(bundle["obligations"][0]["predicate"], "falsified")

    def test_prior_assistant_event_is_never_a_witness(self):
        history = [{"role": "assistant", "content": "Ria obstructed the review."}]
        draft = "Ria obstructed the review."
        bundle = packet(draft, conversation=history)
        self.assertNotIn("prior_user_1", bundle["sources"])
        result, _ = verify(state_for(bundle, source_id="assistant", quote="Ria obstructed the review."),
                           draft, conversation=history)
        self.assertTrue(result)

    def test_draft_is_not_a_user_source(self):
        draft = "Ria concealed the result."
        result, _ = verify(state_for(packet(draft), source_id="candidate", quote=draft), draft)
        self.assertTrue(result)

    def test_invented_quote_cannot_certify_predicate(self):
        draft = "Ria concealed the result."
        result, _ = verify(state_for(packet(draft), quote=draft), draft)
        self.assertTrue(result)

    def test_quote_with_wrong_actor_cannot_certify_predicate(self):
        history = [{"role": "user", "content": "Milo obstructed the review."}]
        draft = "Ria obstructed the review."
        bundle = packet(draft, conversation=history)
        self.assertTrue(verify(state_for(bundle, source_id="prior_user_1", predicate="obstructed"),
                               draft, conversation=history)[0])

    def test_negated_conditional_questioned_or_future_quote_is_not_a_fact(self):
        for text in ("Ria did not obstruct the review.", "If Ria obstructed the review, complain.",
                     "Did Ria obstruct the review?", "Ria will obstruct the review."):
            history = [{"role": "user", "content": text}]
            draft = "Ria obstructed the review."
            bundle = packet(draft, conversation=history)
            with self.subTest(text=text):
                self.assertTrue(verify(state_for(bundle, source_id="prior_user_1", predicate="obstructed"),
                                       draft, conversation=history)[0])

    def test_truncated_witness_cannot_discard_conditional_context(self):
        text = "If Ria obstructed the review, complain."
        history = [{"role": "user", "content": text}]
        draft = "Ria obstructed the review."
        bundle = packet(draft, conversation=history)
        self.assertTrue(verify(state_for(bundle, source_id="prior_user_1", quote="Ria obstructed the review",
                                        predicate="obstructed"), draft, conversation=history)[0])

    def test_quoted_proposition_is_not_promoted_by_truncated_witness(self):
        text = 'Someone wrote "Ria obstructed the review" as an accusation.'
        history = [{"role": "user", "content": text}]
        draft = "Ria obstructed the review."
        bundle = packet(draft, conversation=history)
        self.assertTrue(verify(state_for(bundle, source_id="prior_user_1", quote="Ria obstructed the review",
                                        predicate="obstructed"), draft, conversation=history)[0])

    def test_complete_assessments_are_required_for_every_refinement(self):
        draft = "Ria concealed the result. She falsified the review."
        bundle = packet(draft)
        self.assertEqual(len(bundle["obligations"]), 2)
        state = state_for(bundle)
        state["relation_assessments"].pop()
        self.assertTrue(verify(state, draft)[0])

    def test_negative_relation_cannot_be_overridden_by_positive_global(self):
        draft = "Ria concealed the result."
        self.assertTrue(verify(state_for(packet(draft), supported=False), draft)[0])

    def test_malformed_assessments_are_not_truthy_support(self):
        draft = "Ria concealed the result."
        for value in (None, {}, "true", [], [True], [{"index": True, "supported": True}]):
            with self.subTest(value=value):
                self.assertTrue(verify(POSITIVE | {"relation_assessments": value}, draft)[0])

    def test_malformed_witness_fields_fail_without_exception(self):
        draft = "Ria concealed the result."
        for field in ("source_id", "source_quote", "source_predicate"):
            value = state_for(packet(draft))
            value["relation_assessments"][0][field] = []
            with self.subTest(field=field):
                self.assertTrue(verify(value, draft)[0])

    def test_duplicate_or_unknown_indexes_are_incomplete(self):
        draft = "Ria concealed the result. She falsified the review."
        for index in (1, 9):
            value = state_for(packet(draft))
            value["relation_assessments"][1]["index"] = index
            with self.subTest(index=index):
                self.assertTrue(verify(value, draft)[0])

    def test_complaint_is_not_authority_for_a_new_role(self):
        draft = "Fine, I'll stop pretending you're my coach."
        bundle = packet(draft, user=COMPLAINT)
        self.assertEqual(bundle["obligations"][0]["kind"], "relationship_role")
        self.assertTrue(verify(POSITIVE, draft, user=COMPLAINT)[0])

    def test_role_nouns_are_not_blacklisted(self):
        for role in ("teacher", "coach", "colleague"):
            prior = [{"role": "user", "content": f"I am your {role}."}]
            draft = f"You're my {role}."
            bundle = packet(draft, user=COMPLAINT, conversation=prior)
            with self.subTest(role=role):
                self.assertEqual(verify(state_for(bundle, source_id="prior_user_1", predicate=role),
                                        draft, user=COMPLAINT, conversation=prior)[0], [])

    def test_role_direction_must_match_user_authorship(self):
        prior = [{"role": "user", "content": "You are my coach."}]
        draft = "You're my coach."
        bundle = packet(draft, user=COMPLAINT, conversation=prior)
        self.assertTrue(verify(state_for(bundle, source_id="prior_user_1", predicate="coach"),
                               draft, user=COMPLAINT, conversation=prior)[0])

    def test_supplied_assistant_role_is_preserved(self):
        prior = [{"role": "user", "content": "You are my coach."}]
        draft = "I'm your coach."
        bundle = packet(draft, user=COMPLAINT, conversation=prior)
        self.assertEqual(verify(state_for(bundle, source_id="prior_user_1", predicate="coach"),
                                draft, user=COMPLAINT, conversation=prior)[0], [])

    def test_direct_complaint_acknowledgement_keeps_legacy_protocol(self):
        draft = "Fair criticism. I should check instead of asking you to recite it."
        self.assertEqual(packet(draft, user=COMPLAINT)["obligations"], ())
        result, client = verify(POSITIVE, draft, user=COMPLAINT)
        self.assertEqual(result, [])
        self.assertEqual(len(client.calls), 1)

    def test_typed_correction_needs_no_lexical_trigger_for_role_obligation(self):
        contract = replace(SOCIAL, intent="correct_mairon", speech_act="correction")
        bundle = packet("You're my supervisor.", user="That was incorrect.", contract=contract)
        self.assertTrue(bundle["obligations"])

    def test_ordinary_supplied_context_stays_outside_new_protocol(self):
        user = "I cleaned my workshop this morning."
        draft = "Your workshop has finally escaped the chaos."
        self.assertEqual(packet(draft, user=user)["obligations"], ())
        self.assertEqual(verify(POSITIVE, draft, user=user)[0], [])

    def test_same_call_carries_trusted_ids_and_required_predicate_spans(self):
        draft = "Ria concealed the result."
        _, client = verify(POSITIVE, draft, conversation=[{"role": "assistant", "content": "SECRET_INVENTION"}])
        self.assertEqual(len(client.calls), 1)
        text = "\n".join(message["content"] for message in client.calls[0]["messages"])
        self.assertIn("CORE LITERAL RELATION OBLIGATIONS", text)
        self.assertIn("relation_assessments", text)
        self.assertIn("NOT evidence", text)
        self.assertNotIn("SECRET_INVENTION", text)


if __name__ == "__main__":
    unittest.main()
