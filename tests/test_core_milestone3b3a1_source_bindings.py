"""Source binding is bounded observation of a selected unchanged answer."""
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core import public_source_bindings as bindings
from research.public_factual_grounding import PUBLIC_FACTUAL_VERIFIER_RESPONSE_SCHEMA


TEXT = "The service permits queued export."
PACKET = json.dumps({"research_kind": "public_factual", "sources": [
    {"source_id": "S1", "title": "Service reference", "url": "https://docs.vendor.example/service",
     "content_excerpt": "The service permits queued export.\nThe public tier does not permit batch export."},
    {"source_id": "S2", "title": "Specialized service guide", "url": "https://research.example/specialized",
     "content_excerpt": "The specialized tier permits batch export."},
]})


def entry(*, index=1, kind="factual", source_ids=None, witnesses=None, provenance="none", scope="supported"):
    return {"index": index, "claim_kind": kind, "source_ids": ["S1"] if source_ids is None else source_ids,
            "witnesses": [{"source_id": "S1", "quote": TEXT}] if witnesses is None else witnesses,
            "provenance_claim": provenance, "scope_status": scope}


class _BoundedChat:
    def __init__(self, owner):
        self.owner = owner

    def chat(self, **kwargs):
        self.owner.calls.append(kwargs)
        if self.owner.error:
            raise self.owner.error
        content = self.owner.payload if isinstance(self.owner.payload, str) else json.dumps(self.owner.payload)
        return SimpleNamespace(message=SimpleNamespace(content=content))

    def close(self):
        self.owner.closed += 1


class _Client:
    def __init__(self, payload=None, error=None):
        self.payload = {"sentences": [entry()]} if payload is None else payload
        self.error = error
        self.calls = []
        self.timeouts = []
        self.closed = 0

    def with_options(self, *, timeout):
        self.timeouts.append(timeout)
        return _BoundedChat(self)


def collect(payload=None, *, text=TEXT, packet=PACKET, error=None, client=None, model="replaceable-local-model",
            user_input="Which export capability is available?"):
    client = client or _Client(payload, error)
    result = bindings.collect_public_source_bindings(
        client=client, model=model, user_input=user_input,
        text=text, evidence_packet=packet,
    )
    return result, client


class PublicSourceBindingTests(unittest.TestCase):
    def test_actual_supported_packet_ids_and_literal_witness_are_retained(self):
        result, client = collect()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["sentences"][0]["source_ids"], ("S1",))
        self.assertEqual(result["sentences"][0]["witnesses"][0]["quote"], TEXT)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.closed, 1)

    def test_core_envelope_binds_exact_draft_and_packet_utf8(self):
        text = "  " + TEXT + "  "
        packet = PACKET + "\n"
        result, _ = collect(text=text, packet=packet)
        self.assertEqual(result["assessed_draft_digest"], hashlib.sha256(text.encode("utf-8")).hexdigest())
        self.assertEqual(result["packet_digest"], hashlib.sha256(packet.encode("utf-8")).hexdigest())
        self.assertEqual(result["assessed_sentences"], (TEXT,))

    def test_snapshot_is_deeply_immutable(self):
        result, _ = collect()
        with self.assertRaises(TypeError):
            result["status"] = "accepted"
        with self.assertRaises(TypeError):
            result["sentences"][0]["scope_status"] = "unsupported"
        with self.assertRaises(TypeError):
            result["sentences"][0]["witnesses"][0]["quote"] = "Invented"

    def test_question_digest_binds_exact_utf8_question_sent_to_annotator(self):
        question = "  Which export capability is available for café accounts?\n"
        result, client = collect(user_input=question)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["assessed_question_digest"], hashlib.sha256(question.encode("utf-8")).hexdigest())
        self.assertEqual(client.calls[0]["messages"][1]["content"], "USER QUESTION DATA:\n" + question)
        with self.assertRaises(TypeError):
            result["assessed_question_digest"] = "substituted"

    def test_changing_only_question_changes_binding_without_changing_other_inputs(self):
        first, _ = collect(user_input="Which export capability is available?")
        second, _ = collect(user_input="Which specialized export capability is available?")
        self.assertNotEqual(first["assessed_question_digest"], second["assessed_question_digest"])
        self.assertEqual(first["assessed_draft_digest"], second["assessed_draft_digest"])
        self.assertEqual(first["packet_digest"], second["packet_digest"])

    def test_empty_question_digest_uses_same_empty_fallback_as_model_input(self):
        result, client = collect(user_input=None)
        self.assertEqual(result["assessed_question_digest"], hashlib.sha256(b"").hexdigest())
        self.assertEqual(client.calls[0]["messages"][1]["content"], "USER QUESTION DATA:\n")

    def test_malformed_other_inputs_still_bind_the_question(self):
        question = "Which capability is available?\n"
        for kwargs in ({"text": None}, {"packet": None}):
            with self.subTest(kwargs=kwargs):
                result, client = collect(user_input=question, **kwargs)
                self.assertEqual(result["status"], "malformed")
                self.assertEqual(result["assessed_question_digest"],
                                 hashlib.sha256(question.encode("utf-8")).hexdigest())
                self.assertEqual(client.calls, [])

    def test_model_cannot_write_the_core_envelope(self):
        payload = {"sentences": [entry()], "status": "complete", "version": 1}
        result, _ = collect(payload)
        self.assertEqual(result["status"], "malformed")
        self.assertEqual(result["sentences"], ())

    def test_separate_annotation_call_does_not_change_legacy_verifier_schema(self):
        before = copy.deepcopy(PUBLIC_FACTUAL_VERIFIER_RESPONSE_SCHEMA)
        _, client = collect()
        self.assertEqual(PUBLIC_FACTUAL_VERIFIER_RESPONSE_SCHEMA, before)
        self.assertIn("sentence_assessments", before["properties"])
        self.assertNotIn("sentences", before["properties"])
        self.assertIn("sentences", client.calls[0]["format"]["properties"])

    def test_call_uses_no_tools_no_research_and_no_answer_repair(self):
        _, client = collect()
        call = client.calls[0]
        self.assertNotIn("tools", call)
        self.assertIs(call["stream"], False)
        self.assertEqual(call["options"]["temperature"], 0)
        self.assertLessEqual(call["options"]["num_predict"], 1200)
        self.assertEqual(call["messages"][2]["content"], PACKET)
        self.assertIn("S1: " + TEXT, call["messages"][3]["content"])
        self.assertEqual(len(client.calls), 1)

    def test_source_scope_annotation_can_preserve_structural_mismatch(self):
        record = entry(source_ids=["S2"], witnesses=[{"source_id": "S2", "quote": "The specialized tier permits batch export."}],
                       scope="unsupported")
        result, _ = collect({"sentences": [record]}, text="The service permits batch export.")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["sentences"][0]["scope_status"], "unsupported")

    def test_unresolved_scope_annotation_does_not_invent_certainty(self):
        result, _ = collect({"sentences": [entry(scope="uncertain")]})
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["sentences"][0]["scope_status"], "uncertain")

    def test_truthful_uncertainty_sentence_needs_no_factual_witness(self):
        record = entry(kind="limitation", source_ids=[], witnesses=[], scope="not_applicable")
        result, _ = collect({"sentences": [record]}, text="I cannot establish that from the available material.")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["sentences"][0]["claim_kind"], "limitation")

    def test_nonfactual_research_offer_does_not_create_a_job(self):
        record = entry(kind="non_factual", source_ids=[], witnesses=[], scope="not_applicable")
        result, client = collect({"sentences": [record]}, text="Would you like me to investigate further?")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(client.calls), 1)
        self.assertNotIn("tools", client.calls[0])

    def test_identity_only_read_can_defer_read_authority_to_canonical_core_state(self):
        result, _ = collect({"sentences": [entry(witnesses=[], provenance="read", scope="not_applicable")]},
                            text="I loaded https://docs.vendor.example/service.")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["sentences"][0]["witnesses"], ())

    def test_source_assertion_requires_content_witness(self):
        result, _ = collect({"sentences": [entry(witnesses=[], provenance="source_assertion")]})
        self.assertEqual(result["status"], "malformed")

    def test_unlisted_source_id_cannot_be_added_by_model(self):
        result, _ = collect({"sentences": [entry(source_ids=["S99"])]})
        self.assertEqual(result["status"], "malformed")
        self.assertEqual(result["issues"], ("binding_source_ids",))

    def test_candidate_prose_cannot_be_used_as_literal_source_evidence(self):
        invented = "The service guarantees instant delivery."
        result, _ = collect({"sentences": [entry(witnesses=[{"source_id": "S1", "quote": invented}])]}, text=invented)
        self.assertEqual(result["status"], "malformed")
        self.assertEqual(result["issues"], ("binding_literal_witness",))

    def test_witness_must_belong_to_declared_source(self):
        result, _ = collect({"sentences": [entry(witnesses=[{"source_id": "S2", "quote": "The specialized tier permits batch export."}])]})
        self.assertEqual(result["status"], "malformed")

    def test_whitespace_normalization_does_not_change_literal_quote_identity(self):
        result, _ = collect({"sentences": [entry(witnesses=[{"source_id": "S1", "quote": "The service\n permits   queued export."}])]})
        self.assertEqual(result["status"], "complete")

    def test_case_change_is_not_a_literal_quote(self):
        result, _ = collect({"sentences": [entry(witnesses=[{"source_id": "S1", "quote": TEXT.upper()}])]})
        self.assertEqual(result["status"], "malformed")

    def test_factual_claim_without_any_source_fails_observationally(self):
        result, _ = collect({"sentences": [entry(source_ids=[], witnesses=[])]})
        self.assertEqual(result["status"], "malformed")

    def test_every_declared_factual_support_source_requires_witness(self):
        result, _ = collect({"sentences": [entry(source_ids=["S1", "S2"])]})
        self.assertEqual(result["status"], "malformed")
        self.assertEqual(result["issues"], ("binding_factual_witness",))

    def test_duplicate_unknown_or_boolean_sentence_index_is_malformed(self):
        for records in ([entry(), entry()], [entry(index=2)], [entry(index=True)]):
            with self.subTest(records=records):
                result, _ = collect({"sentences": records})
                self.assertEqual(result["status"], "malformed")

    def test_missing_sentence_binding_is_incomplete(self):
        result, _ = collect(text=TEXT + " The service has a public tier.")
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(len(result["sentences"]), 1)

    def test_enum_unknown_type_or_extra_field_is_malformed(self):
        for field, value in (("claim_kind", "verified"), ("scope_status", []),
                             ("provenance_claim", "official"), ("unexpected", "answer")):
            record = entry()
            record[field] = value
            with self.subTest(field=field):
                result, _ = collect({"sentences": [record]})
                self.assertEqual(result["status"], "malformed")

    def test_json_truncation_or_wrong_top_level_is_malformed(self):
        for payload in ('{"sentences": [', '[]', 'null', 'plain answer'):
            with self.subTest(payload=payload):
                result, _ = collect(payload)
                self.assertEqual(result["status"], "malformed")

    def test_duplicate_packet_source_id_is_malformed_before_model_call(self):
        packet = json.loads(PACKET)
        packet["sources"][1]["source_id"] = "S1"
        result, client = collect(packet=json.dumps(packet))
        self.assertEqual(result["status"], "malformed")
        self.assertEqual(client.calls, [])

    def test_sentence_limit_abstains_without_model_call(self):
        result, client = collect(text=" ".join(TEXT for _ in range(17)))
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["issues"], ("binding_input_limit",))
        self.assertEqual(client.calls, [])

    def test_output_budget_is_capped_for_maximum_supported_sentences(self):
        result, client = collect({"sentences": [entry(index=index) for index in range(1, 17)]},
                                 text=" ".join(TEXT for _ in range(16)))
        self.assertEqual(result["status"], "complete")
        self.assertEqual(client.calls[0]["options"]["num_predict"], 1200)

    def test_timeout_copy_is_separate_and_closed_without_mutating_original(self):
        result, client = collect()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(client.timeouts, [bindings.BINDING_TIMEOUT_SECONDS])
        self.assertEqual(client.closed, 1)
        self.assertFalse(hasattr(client, "timeout"))

    def test_unknown_client_timeout_capability_abstains_without_call(self):
        class Unsupported:
            def chat(self, **kwargs):
                raise AssertionError("Unbounded client must not be invoked")
        result, _ = collect(client=Unsupported())
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["issues"], ("binding_timeout_capability",))

    def test_timeout_copy_returning_original_is_not_used(self):
        class Same(_Client):
            def with_options(self, **kwargs):
                return self
        result, client = collect(client=Same())
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(client.calls, [])

    def test_timeout_error_is_bounded_unavailable_without_error_prose(self):
        result, client = collect(error=TimeoutError("Private source content and request detail"))
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["issues"], ("binding_transport",))
        self.assertNotIn("Private", repr(result))
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.closed, 1)

    def test_actual_sdk_clone_uses_existing_endpoint_and_keeps_original_timeout(self):
        try:
            from ollama import Client
        except ImportError:
            self.skipTest("Ollama SDK unavailable for constructor-only timeout test")
        original = Client(host="http://127.0.0.1:13456", timeout=7.0, headers={"x-neutral-runtime": "configured"})
        owner = _Client()
        copied = _BoundedChat(owner)
        copied._client = SimpleNamespace(close=copied.close)
        before = original._client.timeout
        try:
            with patch.object(bindings, "_new_local_client", return_value=copied) as constructor:
                result, _ = collect(client=original)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(original._client.timeout, before)
            kwargs = constructor.call_args.kwargs
            self.assertEqual(kwargs["host"], str(original._client.base_url))
            self.assertEqual(kwargs["headers"]["x-neutral-runtime"], "configured")
            self.assertEqual(kwargs["timeout"].read, bindings.BINDING_TIMEOUT_SECONDS)
            self.assertEqual(kwargs["timeout"].connect, 5.0)
            self.assertEqual(len(owner.calls), 1)
            self.assertEqual(owner.closed, 1)
        finally:
            original._client.close()

    def test_unencodable_text_is_unavailable_without_touching_client(self):
        result, client = collect(text=TEXT + "\ud800")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
