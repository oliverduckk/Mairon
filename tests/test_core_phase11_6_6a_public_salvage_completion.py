"""Supported public sentences must still answer the current factual request.

No live web or model is used. Scripted semantic assessments exercise the
Core-owned completion boundary and its strict failure semantics; factual
authority remains with the preceding real sentence-support verifier.
"""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.answer_contract_runtime import AnswerContractRuntime
from research.public_factual_grounding import (
    PUBLIC_FACTUAL_COMPLETION_RESPONSE_SCHEMA,
    build_failed_public_factual_fallback,
    requires_public_factual_salvage_completion,
    verify_public_factual_draft,
    verify_public_factual_salvage_completion,
)


PACKET = json.dumps({
    "freshness_required": True,
    "sources": [{
        "source_id": "S1",
        "title": "Morrow service notices",
        "url": "https://docs.morrow.example/notices",
        "read_success": True,
        "accepted_as_evidence": True,
        "content_excerpt": "The Morrow service is accepting new registrations today. Archived clients need a migration check.",
    }],
})


def contract(**kwargs):
    return AnswerContractRuntime(
        intent=kwargs.pop("intent", "factual_question"),
        authority=kwargs.pop("authority", "public_web"),
        epistemic_mode=kwargs.pop("epistemic_mode", "public_source_verified"),
        **kwargs,
    )


def assessment(*, complete=True, outcome=None, claims=(), violations=()):
    return {
        "completed": complete,
        "outcome": outcome or ("factual_answer" if complete else "incomplete"),
        "request_fulfilled": complete,
        "required_claim_assessments": [
            {"index": index, "fulfilled": value}
            for index, value in enumerate(claims, 1)
        ],
        "violations": list(violations),
    }


class Client:
    def __init__(self, payload=None, *, raw=None, error=None):
        self.payload = payload
        self.raw = raw
        self.error = error
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        content = self.raw if self.raw is not None else json.dumps(self.payload)
        return SimpleNamespace(message=SimpleNamespace(content=content))


class PublicSalvageCompletionTests(unittest.TestCase):
    def verify(self, payload=None, *, client=None, draft="The Morrow service is accepting registrations today.",
               current="Is the Morrow service taking new registrations today?", runtime=None, packet=PACKET,
               authority_context=None):
        client = client or Client(payload or assessment())
        result = verify_public_factual_salvage_completion(
            client, "replaceable-model", current, draft,
            runtime or contract(), packet, authority_context=authority_context,
        )
        return result, client

    def test_real_supported_side_sentence_does_not_establish_answer_completion(self):
        original = "The Morrow service is not accepting registrations today. Archived clients need a migration check."
        legacy = Client({
            "supported": False,
            "unsupported_claims": ["Unsupported current-state assertion"],
            "sentence_assessments": [
                {"index": 1, "supported": False},
                {"index": 2, "supported": True},
            ],
        })
        supported = verify_public_factual_draft(
            legacy, "replaceable-model", "Is the Morrow service taking new registrations today?",
            original, PACKET,
        )
        self.assertEqual(supported.accepted_sentences, ["Archived clients need a migration check."])
        subset = " ".join(supported.accepted_sentences)
        result, _ = self.verify(
            assessment(complete=False, violations=("current_predicate_missing",)), draft=subset,
        )
        self.assertTrue(result)
        self.assertEqual(supported.accepted_sentences, ["Archived clients need a migration check."])

    def test_empty_contract_required_claims_do_not_exempt_the_current_question(self):
        result, client = self.verify(
            assessment(complete=False, violations=("unrelated_side_detail",)),
            draft="Archived clients need a migration check.",
        )
        self.assertTrue(result)
        self.assertEqual(len(client.calls), 1)
        self.assertIn("Empty required_claims does NOT mean", client.calls[0]["messages"][0]["content"])

    def test_supported_actual_current_predicate_is_complete(self):
        result, _ = self.verify()
        self.assertEqual(result, [])

    def test_answer_wording_need_not_use_yes_or_no(self):
        for text in (
            "Registrations remain open today.",
            "Today's service notice confirms new registrations are open.",
            "New accounts can currently register for Morrow.",
        ):
            with self.subTest(text=text):
                result, _ = self.verify(draft=text)
                self.assertEqual(result, [])

    def test_relevant_bounded_current_limitation_is_complete(self):
        result, _ = self.verify(
            assessment(outcome="bounded_limitation"),
            draft="I can't verify whether registrations are open right now from the available notices.",
        )
        self.assertEqual(result, [])

    def test_existing_public_failure_builder_can_complete_the_request(self):
        text = build_failed_public_factual_fallback()
        result, _ = self.verify(assessment(outcome="bounded_limitation"), draft=text)
        self.assertEqual(result, [])

    def test_limitation_about_an_unrelated_property_does_not_complete_request(self):
        result, _ = self.verify(
            assessment(complete=False, violations=("limitation_not_relevant",)),
            draft="I don't know which font the notices use.",
        )
        self.assertTrue(result)

    def test_limitation_followed_by_missing_exact_fact_cannot_rescue_completion(self):
        result, _ = self.verify(
            assessment(complete=False, violations=("factual_tail_after_limitation",)),
            draft="I can't establish the current registration state. It is definitely closed now.",
        )
        self.assertTrue(result)

    def test_multiple_requested_predicates_must_all_be_answered(self):
        result, client = self.verify(
            assessment(complete=False, violations=("incomplete_request",)),
            current="Are Morrow registrations open today, and which regions are eligible?",
            draft="Morrow registrations are open today.",
        )
        self.assertTrue(result)
        self.assertIn("all factual predicates", client.calls[0]["messages"][0]["content"])

    def test_completion_is_not_limited_to_release_or_product_questions(self):
        for request, surviving in (
            ("Who currently coordinates the Westhaven archive?", "The archive has public reading rooms."),
            ("Is the Estuary crossing open this morning?", "Walking shoes are useful on the route."),
            ("When does the next Dovetail session begin?", "The venue has a water station."),
        ):
            with self.subTest(request=request):
                result, client = self.verify(
                    assessment(complete=False, violations=("incomplete_request",)),
                    current=request, draft=surviving,
                )
                self.assertTrue(result)
                self.assertIn(request, client.calls[0]["messages"][3]["content"])

    def test_all_known_core_required_claims_remain_obligatory(self):
        runtime = contract(required_claims=("Registration is open.", "Only the eastern region is eligible."))
        result, _ = self.verify(assessment(claims=(True, True)), runtime=runtime)
        self.assertEqual(result, [])

    def test_omitted_known_required_claim_fails_closed(self):
        runtime = contract(required_claims=("Registration is open.", "Only the eastern region is eligible."))
        payload = assessment(complete=False, claims=(True, False), violations=("required_claim_missing",))
        result, _ = self.verify(payload, runtime=runtime)
        self.assertTrue(result)

    def test_required_claim_accounting_cannot_be_missing_duplicate_or_extra(self):
        runtime = contract(required_claims=("Registration is open.", "The eastern region is eligible."))
        for claims in (
            [{"index": 1, "fulfilled": True}],
            [{"index": 1, "fulfilled": True}, {"index": 1, "fulfilled": True}],
            [{"index": 1, "fulfilled": True}, {"index": 2, "fulfilled": True}, {"index": 3, "fulfilled": True}],
            [{"index": True, "fulfilled": True}, {"index": 2, "fulfilled": True}],
        ):
            with self.subTest(claims=claims):
                payload = assessment(claims=(True, True))
                payload["required_claim_assessments"] = claims
                result, _ = self.verify(payload, runtime=runtime)
                self.assertTrue(result)

    def test_global_positive_cannot_override_negative_required_claim(self):
        payload = assessment(claims=(False,))
        result, _ = self.verify(payload, runtime=contract(required_claims=("Registration is open.",)))
        self.assertTrue(result)

    def test_global_positive_cannot_override_missing_request_predicate(self):
        payload = assessment()
        payload["request_fulfilled"] = False
        result, _ = self.verify(payload)
        self.assertTrue(result)

    def test_global_positive_cannot_override_violation_or_incomplete_outcome(self):
        for payload in (
            assessment(violations=("current_predicate_missing",)),
            assessment(outcome="incomplete"),
        ):
            with self.subTest(payload=payload):
                result, _ = self.verify(payload)
                self.assertTrue(result)

    def test_false_global_with_all_positive_substate_is_also_inconsistent(self):
        payload = assessment()
        payload["completed"] = False
        result, _ = self.verify(payload)
        self.assertTrue(result)

    def test_typed_verdict_and_status_are_strict(self):
        for key, value in (
            ("completed", "true"), ("request_fulfilled", 1),
            ("outcome", "probably_answered"), ("violations", "none"),
        ):
            with self.subTest(key=key):
                payload = assessment()
                payload[key] = value
                result, _ = self.verify(payload)
                self.assertTrue(result)

    def test_missing_or_unexpected_verifier_fields_are_not_accepted(self):
        for payload in (
            {key: value for key, value in assessment().items() if key != "request_fulfilled"},
            assessment() | {"extra": "Annotation text is not authority"},
        ):
            with self.subTest(payload=payload):
                result, _ = self.verify(payload)
                self.assertTrue(result)

    def test_verifier_exception_and_malformed_output_fail_without_leaking(self):
        for client in (Client(error=RuntimeError("private service content")), Client(raw="malformed private annotation")):
            with self.subTest(client=client):
                stream = io.StringIO()
                with redirect_stdout(stream):
                    result, _ = self.verify(client=client)
                self.assertTrue(result)
                self.assertNotIn("private", " ".join(result) + stream.getvalue())

    def test_only_allowlisted_violation_identifiers_are_transportable(self):
        result, _ = self.verify(assessment(complete=False, violations=("private excerpt from model",)))
        self.assertTrue(result)
        self.assertNotIn("private", " ".join(result))

    def test_out_of_scope_contracts_do_not_add_a_semantic_call(self):
        for runtime in (
            contract(intent="share_opinion"), contract(intent="recommendation_request"),
            contract(authority="public_web", epistemic_mode="consequential_advice"),
            contract(authority="public_web", epistemic_mode="media_public_grounded"),
            contract(authority="model_knowledge", epistemic_mode="stable_model_knowledge"),
            contract(intent="casual_conversation", authority="live_conversation", epistemic_mode="conversation"),
            contract(authority="deterministic_core", epistemic_mode="deterministic_result"),
        ):
            with self.subTest(runtime=runtime):
                result, client = self.verify(runtime=runtime)
                self.assertEqual(result, [])
                self.assertEqual(client.calls, [])

    def test_empty_subset_or_missing_packet_cannot_be_published(self):
        for args in ({"draft": ""}, {"current": ""}, {"packet": "{}"}):
            with self.subTest(args=args):
                result, client = self.verify(**args)
                self.assertTrue(result)
                self.assertEqual(client.calls, [])

    def test_source_packet_and_subset_remain_distinct_immutable_inputs(self):
        payload = assessment()
        original = copy.deepcopy(payload)
        result, client = self.verify(payload)
        self.assertEqual(result, [])
        self.assertEqual(payload, original)
        self.assertEqual(client.calls[0]["messages"][-2]["content"], PACKET)
        self.assertIn("RETAINED VERIFIER-SUPPORTED SUBSET", client.calls[0]["messages"][-1]["content"])
        self.assertIn("never evidence", client.calls[0]["messages"][0]["content"])
        self.assertEqual(client.calls[0]["format"], PUBLIC_FACTUAL_COMPLETION_RESPONSE_SCHEMA)

    def test_no_replacement_or_rewrite_is_created_by_completion_helper(self):
        text = "Archived clients need a migration check."
        result, client = self.verify(assessment(complete=False, violations=("incomplete_request",)), draft=text)
        self.assertTrue(result)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["messages"][-1]["content"], "RETAINED VERIFIER-SUPPORTED SUBSET:\n" + text)
        self.assertFalse(hasattr(result, "accepted_sentences"))

    def test_evergreen_without_typed_completion_obligations_preserves_legacy_call_budget(self):
        packet = json.loads(PACKET)
        packet["freshness_required"] = False
        result, client = self.verify(
            packet=json.dumps(packet), current="Which export formats does Morrow support?",
            draft="Morrow supports portable export.",
        )
        self.assertEqual(result, [])
        self.assertEqual(client.calls, [])

    def test_explicit_required_claims_trigger_completion_even_for_evergreen_evidence(self):
        packet = json.loads(PACKET)
        packet["freshness_required"] = False
        result, client = self.verify(
            assessment(claims=(True,)), packet=json.dumps(packet),
            runtime=contract(required_claims=("Morrow supports portable export.",)),
            current="Which export formats does Morrow support?", draft="Morrow supports portable export.",
        )
        self.assertEqual(result, [])
        self.assertEqual(len(client.calls), 1)

    def test_typed_current_state_obligation_cannot_be_erased_by_a_weaker_packet(self):
        packet = json.loads(PACKET)
        packet["freshness_required"] = False
        result, client = self.verify(
            assessment(complete=False, violations=("current_predicate_missing",)),
            packet=json.dumps(packet), authority_context={"freshness_required": True},
            draft="Archived clients need a migration check.",
        )
        self.assertTrue(result)
        self.assertEqual(len(client.calls), 1)

    def test_weaker_authority_snapshot_cannot_erase_retained_packet_freshness(self):
        result, client = self.verify(authority_context={"freshness_required": False})
        self.assertEqual(result, [])
        self.assertEqual(len(client.calls), 1)

    def test_malformed_packet_or_freshness_state_never_silently_skips_a_known_obligation(self):
        cases = (
            {"packet": "broken transport", "authority_context": {"freshness_required": True}},
            {"packet": json.dumps({"sources": [], "freshness_required": True})},
            {"packet": json.dumps({"sources": [{}], "freshness_required": "false"})},
            {"authority_context": {"freshness_required": "false"}},
        )
        for args in cases:
            with self.subTest(args=args):
                result, client = self.verify(**args)
                self.assertTrue(result)
                self.assertEqual(client.calls, [])

    def test_existing_raw_packet_shape_and_envelope_have_equivalent_completion_requirements(self):
        raw = json.loads(PACKET)
        envelope = "CORE PUBLIC FACTUAL EVIDENCE:\n" + PACKET
        for packet in (raw, envelope):
            with self.subTest(packet=packet):
                result, client = self.verify(packet=packet)
                self.assertEqual(result, [])
                self.assertEqual(len(client.calls), 1)

    def test_applicability_depends_only_on_retained_contract_and_evidence_obligations(self):
        evergreen = json.loads(PACKET)
        evergreen["freshness_required"] = False
        self.assertFalse(requires_public_factual_salvage_completion(contract(), evergreen))
        self.assertTrue(requires_public_factual_salvage_completion(contract(), PACKET))
        self.assertTrue(requires_public_factual_salvage_completion(
            contract(required_claims=("Morrow supports portable export.",)), evergreen,
        ))
        self.assertFalse(requires_public_factual_salvage_completion(contract(intent="share_opinion"), PACKET))

    def test_unknown_completion_obligation_requires_fail_closed_check(self):
        unknown = json.loads(PACKET)
        del unknown["freshness_required"]
        self.assertTrue(requires_public_factual_salvage_completion(contract(), unknown))
        result, client = self.verify(packet=unknown)
        self.assertTrue(result)
        self.assertEqual(client.calls, [])

    def test_invalid_applicability_input_is_not_an_exemption(self):
        for runtime, packet in ((None, PACKET), (contract(), "invalid packet")):
            with self.subTest(runtime=runtime):
                self.assertTrue(requires_public_factual_salvage_completion(runtime, packet))


if __name__ == "__main__":
    unittest.main()
