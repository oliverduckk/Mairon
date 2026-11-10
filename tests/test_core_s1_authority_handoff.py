"""S1 offline contract, failure and compatibility checks (no real integrations).

Run as: python tests/test_core_s1_authority_handoff.py
The test-only SDK stubs deliberately prevent model, OAuth and web calls.
"""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))
import s1_offline_bootstrap  # noqa: F401

import application_service as app_module
from application_service import MaironApplication
from core import router
from core.cloud_export import issue_cloud_export_grant, admit_cloud_initial
from core.authority_handoff import (
    CoreAuthorityUnavailable, prepare_core_turn, seal_prepared_turn,
)
from core.answer_contract import AnswerContract
from core.answer_contract_runtime import (
    coerce_answer_contract_runtime, runtime_from_legacy_text,
)
from core.evidence import Evidence, EvidenceBundle
from ai import openai_provider, ollama_provider
import ast


class Core:
    def __init__(self, *, failure=None, direct=None, contract=None, effect=None):
        self.failure = failure
        self.direct = direct
        self.contract = contract
        self.effect = effect
        self.conversation_state = SimpleNamespace(recent_user_turns=[])

    def prepare_turn(self, _text):
        if self.effect:
            self.effect()
        if self.failure:
            raise RuntimeError(self.failure)
        return SimpleNamespace(
            turn=SimpleNamespace(intent=self.contract.intent if self.contract else "test_direct"),
            epistemic_route=SimpleNamespace(
                authority=self.contract.authority if self.contract else "core_test",
                mode=self.contract.epistemic_mode if self.contract else "deterministic",
                verification_required=False,
                private_data_required=False,
                live_data_required=False,
            ),
            answer_contract=self.contract,
            direct_response=self.direct,
            needs_clarification=False,
            clarification_question=None,
            workflow_result=None,
        )


def contract(**overrides):
    fields = dict(
        task="respond", speech_act="question", intent="factual_question",
        subject="Current test", authority="epistemic_fallback",
        epistemic_mode="classify_then_verify",
        allow_recommendations=False, allow_new_factual_claims=True,
        allow_follow_up_question=False,
    )
    fields.update(overrides)
    return AnswerContract(**fields)


class Local:
    def __init__(self, *, pending=None, escalation=None):
        self.calls = []
        self.pending = pending
        self.escalation = escalation

    def get_response(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return "A grounded reply.", ["local-history"], self.escalation, self.pending


class Cloud:
    def __init__(self):
        self.calls = []

    def get_response(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return "Cloud reply.", "resp_123", None


def app(core, local, cloud=None):
    result = MaironApplication(
        user_name="OfflineUser", core=core,
        local_ai={"client": object(), "module": local},
        cloud_ai={"client": object(), "module": cloud} if cloud else None,
        create_providers=False,
    )
    # No local database, title background thread, or model call in this fixture.
    result._schedule_semantic_title_if_first_turn = lambda **_kw: None
    return result


def run():
    checks = 0
    with mock.patch.object(app_module, "capture_user_preference", return_value=None), \
         mock.patch.object(app_module, "build_user_preference_recall_response", return_value=None), \
         mock.patch.object(app_module, "record_conversation_turn"), \
         mock.patch.object(app_module, "record_chat_turn"):

        # 1B:T6 before authority, no provider, cloud or duplicate tool call.
        local, cloud = Local(), Cloud()
        a = app(Core(failure="before authority"), local, cloud)
        outcome = a.submit_text("A test question")
        assert outcome.status == "error" and "outcome needs checking" in outcome.answer
        assert not local.calls and not cloud.calls
        checks += 1

        # 1B:T6 after an effect: no automatic second effect or retry.
        effects = []
        a = app(Core(failure="after effect", effect=lambda: effects.append("one")), local, cloud)
        outcome = a.submit_text("Run my fake operation")
        assert outcome.status == "error" and effects == ["one"]
        assert not local.calls and not cloud.calls
        assert prepare_core_turn(Core(failure="failure"), "x").possible_prior_effect
        checks += 1

        # 1B:T6 failure while rendering a post-Core mandatory contract.
        class BrokenContract(AnswerContract):
            def to_model_instruction(self):
                raise RuntimeError("render failure")

        broken = BrokenContract(**vars(contract()))
        a = app(Core(contract=broken), local, cloud)
        outcome = a.submit_text("A test question")
        assert outcome.status == "error" and not local.calls and not cloud.calls
        checks += 1

        # Existing independently safe deterministic direct outcome remains intact.
        a = app(Core(direct="Direct Core decision."), local, cloud)
        outcome = a.submit_text("A test direct")
        assert outcome.status == "answered" and outcome.answer == "Direct Core decision."
        assert not local.calls and not cloud.calls
        checks += 1

        # 1B:T7 exact typed claim, non-comparison metadata, referents and evidence.
        evidence = EvidenceBundle(authority="verified", success=True)
        evidence.add(Evidence(
            claim="Proof source is recorded.", provenance="tool_verified",
            confidence="high", source_name="fixture", source_id="source-7",
            data={"nested": [42, "original"]},
        ))
        c = contract()
        c.required_claims.append("The required result is recorded.")
        c.forbidden_behaviours.append("No fabricated history.")
        c.resolved_referents["it"] = "a fixture referent"
        c.metadata["non_comparison"] = {"record": 1, "flags": [True, False]}
        c.evidence = evidence
        sealed = seal_prepared_turn(Core(contract=c).prepare_turn("question"))
        runtime = sealed.runtime
        assert sealed.contract is c and sealed.evidence is evidence
        assert runtime.original_evidence is evidence
        assert runtime.required_claims == ("The required result is recorded.",)
        assert runtime.verified_evidence_claims == ("Proof source is recorded.",)
        assert runtime.resolved_referents["it"] == "a fixture referent"
        assert runtime.metadata["non_comparison"] == {"record": 1, "flags": [True, False]}
        assert "No fabricated history." in runtime.forbidden_behaviours
        assert runtime.allow_new_factual_claims and not runtime.allow_recommendations
        checks += 1

        # Legacy parsing is not trusted to recreate full metadata/lineage.
        legacy = runtime_from_legacy_text(c.to_model_instruction())
        assert legacy is not None and legacy.source == "legacy_text"
        assert legacy.original_evidence is None
        assert "non_comparison" not in legacy.metadata
        assert legacy.required_claims != runtime.required_claims
        assert coerce_answer_contract_runtime(None) is None
        checks += 1

        # 1B:T7 trusted router must reject null and forged/legacy authority.
        try:
            router.route_message({"module":local,"client":object()}, None, "x", "prompt", core_authority=None)
        except CoreAuthorityUnavailable:
            pass
        else:
            raise AssertionError("missing Core authority passed")
        assert not local.calls
        checks += 1

        # Local route receives the structured runtime; model text is separate.
        clean = contract()
        a = app(Core(contract=clean), local, cloud)
        outcome = a.submit_text("A test question")
        assert outcome.status == "answered" and outcome.answer == "A grounded reply."
        assert len(local.calls) == 1 and not cloud.calls
        assert local.calls[-1][1]["core_answer_contract"].source == "structured"
        checks += 1

        # 1B:T9 cloud three-field result for eligible /cloud requests.
        a = app(Core(contract=contract()), Local(), cloud)
        outcome = a.submit_text("/cloud A test question")
        assert outcome.status == "answered" and outcome.answer == "Cloud reply."
        assert len(cloud.calls) == 1 and a.cloud_state == "resp_123"
        checks += 1

        # Cloud mandatory verified claims / private workflows are unsupported.
        restricted = contract()
        restricted.required_claims.append("Required verified result")
        restricted_a = app(Core(contract=restricted), Local(), Cloud())
        denied = restricted_a.submit_text("/cloud A test question")
        assert denied.status == "error" and not restricted_a.cloud_ai["module"].calls
        checks += 1

        # Non-comparison metadata is also mandatory and unsupported in cloud.
        metadata_only = contract()
        metadata_only.metadata["required_data"] = {"origin": "fixture"}
        denied_a = app(Core(contract=metadata_only), Local(), Cloud())
        denied = denied_a.submit_text("/cloud A test question")
        assert denied.status == "error" and not denied_a.cloud_ai["module"].calls
        checks += 1

        # Malformed required field disagreement is not permissively repaired.
        wrong = contract(authority="unknown")
        try:
            seal_prepared_turn(Core(contract=wrong).prepare_turn("q"))
        except CoreAuthorityUnavailable:
            pass
        else:
            raise AssertionError("unknown authority admitted")
        checks += 1

        # 1B:T9 local four-field pending-action stays pending until approval.
        pending_action = {
            "type": "create_calendar_event", "summary": "Fixture",
            "start_time": "2026-11-10T10:00:00", "end_time": "2026-11-10T11:00:00",
        }
        calendar_contract = contract(intent="calendar_event_creation_request")
        pending_local = Local(pending=pending_action)
        a = app(Core(contract=calendar_contract), pending_local)
        approval = a.submit_text("Please create an appointment")
        assert approval.status == "action_approval_required" and a.has_pending_approval
        refused = a.resolve_pending_approval(False)
        assert refused.status == "answered" and not a.has_pending_approval
        assert not hasattr(pending_local, "executed")
        checks += 1

        # Actual approval is fake and goes through the original approval branch.
        a = app(Core(contract=calendar_contract), Local(pending=pending_action))
        assert a.submit_text("Please create an appointment").status == "action_approval_required"
        with mock.patch.object(router, "execute_approved_action", return_value={"success": True}) as execute, \
             mock.patch.object(router, "format_action_result", return_value="Approved fixture action."):
            accepted = a.resolve_pending_approval(True)
        assert execute.call_count == 1 and accepted.status == "answered"
        checks += 1

        # Cloud approval and decline both retain the original typed authority.
        prompt = "Please derive a rigorous formal proof of a byzantine distributed system consensus protocol with comprehensive analysis"
        a = app(Core(contract=contract()), Local(), Cloud())
        first = a.submit_text(prompt)
        assert first.status == "cloud_approval_required"
        approved = a.resolve_pending_approval(True)
        assert approved.status == "answered" and approved.answer == "Cloud reply."
        checks += 1
        a = app(Core(contract=contract()), Local(), Cloud())
        assert a.submit_text(prompt).status == "cloud_approval_required"
        declined = a.resolve_pending_approval(False)
        assert declined.status == "answered" and declined.answer == "A grounded reply."
        assert a.local_ai["module"].calls[-1][1]["allow_cloud_escalation"] is False
        checks += 1

        # 1B:T9 fake Responses API: one function call, one follow-up, 3 fields.
        outputs = []
        class Responses:
            def create(self, **kw):
                outputs.append(kw)
                if len(outputs) == 1:
                    return SimpleNamespace(
                        id="one", output=[SimpleNamespace(
                            type="function_call", name="get_weather", arguments='{"location":"Sydney"}',
                            call_id="c1",
                        )], output_text="",
                    )
                return SimpleNamespace(id="two",output=[],output_text="Done")
        cloud_authority = seal_prepared_turn(Core(contract=contract()).prepare_turn("weather"))
        export_grant = issue_cloud_export_grant(
            cloud_authority, "weather", purpose="explicit_cloud_request",
        )
        cloud_instructions = admit_cloud_initial(export_grant, "weather").payload["instructions"]
        with mock.patch.object(openai_provider, "execute_tool", return_value={"success":True}):
            response = openai_provider.get_response(
                SimpleNamespace(responses=Responses()), "weather", cloud_instructions,
                core_answer_contract=cloud_authority.runtime, cloud_export=export_grant,
            )
        assert response == ("Done", "two", None)
        assert len(outputs) == 2 and outputs[1]["previous_response_id"] == "one"
        checks += 1

        # Provider ingress must reject an explicitly supplied weaker contract
        # before background worker startup / model calls.
        with mock.patch.object(ollama_provider, "ensure_background_research_worker_started") as worker:
            try:
                ollama_provider._get_response_impl(
                    object(), "request", "prompt", core_answer_contract=legacy,
                )
            except ValueError:
                pass
            else:
                raise AssertionError("legacy contract promoted at local provider ingress")
            worker.assert_not_called()
        checks += 1

        # Cloud provider itself also refuses an impossible required-claim turn,
        # before an SDK request can be issued.
        class NoRequest:
            def create(self, **_kwargs):
                raise AssertionError("Cloud SDK must not be invoked")
        try:
            openai_provider.get_response(
                SimpleNamespace(responses=NoRequest()), "request", "prompt",
                core_answer_contract=runtime,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("cloud required-claim obligation admitted")
        checks += 1

        # The terminal cannot be imported offline (voice SDKs/hardware), but
        # AST checks guard both terminal handoff sites and their no-fallback path.
        terminal = ast.parse((PROJECT_ROOT / "src" / "main.py").read_text())
        calls = [node for node in ast.walk(terminal) if isinstance(node, ast.Call)]
        names = [node for node in calls if isinstance(node.func, ast.Name)]
        assert any(node.func.id == "prepare_core_turn" for node in names)
        assert not any(isinstance(node.func, ast.Attribute) and node.func.attr == "prepare_turn" for node in calls)
        route_calls = [node for node in names if node.func.id == "route_message"]
        assert len(route_calls) == 1 and any(kw.arg == "core_authority" for kw in route_calls[0].keywords)
        assert any(node.func.id == "seal_prepared_turn" for node in names)
        checks += 1

    print(f"Mairon S1 offline authority handoff: {checks}/{checks} PASS")


if __name__ == "__main__":
    run()
