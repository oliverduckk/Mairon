"""S3 cloud egress tests. Fake Responses API; no network, account or live tools."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
import s1_offline_bootstrap  # noqa: F401 -- prevent SDK access

from core.answer_contract import AnswerContract
from core.authority_handoff import seal_prepared_turn
from core.cloud_export import (
    CloudExportDenied, CloudExportGrant, issue_cloud_export_grant,
    admit_cloud_initial, admit_cloud_tool_followup,
    admit_cloud_tool_definitions, admit_cloud_sdk_request,
    project_cloud_tool_result,
)
from core import router
from core.provider_state import CloudContinuation, eligible_cloud_continuation
from ai import openai_provider
from tools.tool_registry import CLOUD_TOOLS
from tools.tool_admission import provider_turn

PRIVATE = "UNEXPORTED_PRIVATE_CONTEXT_919283"


def authority(*, private=False, evidence=None):
    c = AnswerContract(
        task="respond", speech_act="question", intent="factual_question",
        subject=PRIVATE, authority="test_core", epistemic_mode="classify_then_verify",
        allow_new_factual_claims=True,
    )
    c.evidence = evidence
    return seal_prepared_turn(SimpleNamespace(
        turn=SimpleNamespace(intent="factual_question", requested_action=None),
        epistemic_route=SimpleNamespace(
            authority="test_core", mode="classify_then_verify",
            verification_required=False, private_data_required=private,
            live_data_required=False,
        ), answer_contract=c,
    ))


class FakeResponses:
    def __init__(self, tool_call=None, callback=None):
        self.calls = []
        self.tool_call = tool_call
        self.callback = callback
        self.responses = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.callback:
            self.callback(len(self.calls))
        return SimpleNamespace(
            id="resp_safe_one" if len(self.calls) == 1 else "resp_safe_two",
            output=[self.tool_call] if len(self.calls) == 1 and self.tool_call else [],
            output_text="cloud answer",
        )


class FakeCloudAdapter:
    def __init__(self):
        self.calls = []
    def get_response(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return ("cloud answer", "resp_accepted", None)


def rejected(callback):
    try:
        callback()
    except CloudExportDenied:
        return
    raise AssertionError("Unadmitted payload reached the cloud boundary")


def run():
    checks = 0
    auth = authority()
    prompt = "What causes the aurora borealis?"
    grant = issue_cloud_export_grant(auth, prompt, purpose="explicit_cloud_request")
    admitted = admit_cloud_initial(grant, prompt)
    assert admitted.payload["input"] == prompt
    assert admitted.payload["previous_response_id"] is None
    assert admitted.manifest.data_classes == ("user_current_prompt", "reviewed_cloud_instructions")
    assert admitted.manifest.total_bytes > 0
    assert PRIVATE not in json.dumps(admitted.payload)
    checks += 1

    # App instruction, previous cloud handle, and nested history never export.
    adapter = FakeCloudAdapter()
    result = router.route_message(
        {"module": object(), "client": object()},
        {"module": adapter, "client": object()},
        "/cloud " + prompt, "application instructions: " + PRIVATE,
        local_state=[{"role": "user", "content": PRIVATE}],
        cloud_state=[{"role": "assistant", "content": PRIVATE}],
        core_authority=auth,
        state_owner_id="s3-fixture-session",
    )
    assert result.answer == "cloud answer" and isinstance(result.cloud_state, CloudContinuation)
    assert result.cloud_state.response_id == "resp_accepted"
    assert eligible_cloud_continuation(
        result.cloud_state, owner_id="s3-fixture-session", model_id="gpt-5.6-luna",
    ) is result.cloud_state
    args, kw = adapter.calls[0]
    assert args[1] == prompt and args[3] is None
    assert PRIVATE not in args[2] and PRIVATE not in str(args)
    assert kw["cloud_export"].purpose == "explicit_cloud_request"
    checks += 1

    # Cloud approval similarly carries only the approved prompt, not surrounding
    # private app instructions, saved state, or UI conversation context.
    adapter = FakeCloudAdapter()
    approved = router.approve_cloud_escalation(
        {"module": adapter, "client": object()}, prompt,
        "private instructions " + PRIVATE,
        local_state=[PRIVATE], cloud_state="unqualified_prior_cloud_handle",
        core_authority=auth,
    )
    assert approved.answer == "cloud answer"
    args, kw = adapter.calls[0]
    assert args[1] == prompt and PRIVATE not in str(args)
    assert args[3] is None and kw["cloud_export"].purpose == "approved_cloud_escalation"
    checks += 1

    # Grant cannot be inferred from a valid Core contract or a model string.
    client = FakeResponses()
    rejected(lambda: openai_provider.get_response(
        client, prompt, admitted.payload["instructions"],
        core_answer_contract=auth.runtime,
    ))
    assert client.calls == []
    checks += 1

    rejected(lambda: openai_provider.get_response(
        client, prompt, "APP PERSONAL INFORMATION " + PRIVATE,
        cloud_export=grant, core_answer_contract=auth.runtime,
    ))
    assert client.calls == []
    checks += 1

    # SDK request gets only the admitted current text, neutral instructions and
    # neutral public tool schemas, not the original personalised descriptions.
    client = FakeResponses()
    with provider_turn(auth):
        answer, state, escalation = openai_provider.get_response(
            client, prompt, admitted.payload["instructions"],
            previous_response_id=[{"role": "user", "content": PRIVATE}],
            core_answer_contract=auth.runtime, cloud_export=grant,
        )
    assert answer == "cloud answer" and state == "resp_safe_one" and escalation is None
    request = client.calls[0]
    assert request["previous_response_id"] is None
    assert PRIVATE not in json.dumps(request)
    assert "Oliver" not in json.dumps(request["tools"])
    assert len(request["tools"]) == 3
    checks += 1

    # Invalid or expired scopes deny before any SDK request.
    rejected(lambda: issue_cloud_export_grant(auth, prompt, purpose="other"))
    rejected(lambda: issue_cloud_export_grant(authority(private=True), prompt,
                                              purpose="explicit_cloud_request"))
    rejected(lambda: admit_cloud_initial(grant, "altered prompt"))
    forged = CloudExportGrant("explicit_cloud_request", grant.prompt_digest, object(), grant._created)
    rejected(lambda: admit_cloud_initial(forged, prompt))
    checks += 1
    expired = issue_cloud_export_grant(auth, prompt, purpose="explicit_cloud_request")
    expired._created -= 601
    rejected(lambda: admit_cloud_initial(expired, prompt))
    revoked = issue_cloud_export_grant(auth, prompt, purpose="explicit_cloud_request")
    revoked.revoke()
    rejected(lambda: admit_cloud_initial(revoked, prompt))
    checks += 1

    # Recognised secrets and oversize prompts cannot be exported, regardless
    # of whether /cloud was typed or an escalation approved.
    for secret in ("api_key=TOPSECRET12345", "Bearer verylongBearerSecret",
                   "-----BEGIN PRIVATE KEY-----", "password: long12345"):
        rejected(lambda secret=secret: issue_cloud_export_grant(
            auth, "Please analyse " + secret, purpose="explicit_cloud_request"
        ))
    rejected(lambda: issue_cloud_export_grant(auth, "x" * 12001,
                                               purpose="explicit_cloud_request"))
    checks += 1

    # Public result is a FIELD-LEVEL projection; no nested unknown metadata or
    # private tool payload can slip through via json.dumps(tool_result).
    weather = {"success": True, "location": {"name": "Sydney", "country": "Australia",
               "auth_token": PRIVATE}, "current": {"temperature_c": 24,
               "conditions": "Sunny", "private_account": PRIVATE},
               "metadata": {"credentials": PRIVATE}}
    projected = project_cloud_tool_result("get_weather", weather)
    assert '"temperature_c": 24' in projected and PRIVATE not in projected
    assert "auth_token" not in projected and "private_account" not in projected
    checks += 1

    public_search = {"success": True, "query": "public science", "metadata": PRIVATE,
                     "results": [{"title": "Science", "url": "https://example.org/solar",
                                  "content": "A public page", "score": 0.9,
                                  "headers": {"authorization": PRIVATE}}]}
    search_json = project_cloud_tool_result("web_search", public_search)
    assert "A public page" in search_json and PRIVATE not in search_json
    assert "headers" not in search_json
    checks += 1

    good_page = project_cloud_tool_result("web_read", {"success": True,
        "url": "https://example.com/docs", "content": "Public reference text.",
        "cookies": PRIVATE})
    assert "Public reference text" in good_page and PRIVATE not in good_page
    checks += 1

    # Denied private tool, raw error or exception response is not echoed.
    for name in ("list_memories", "read_email", "launch_application"):
        value = project_cloud_tool_result(name, {"success": True, "memory": PRIVATE})
        assert json.loads(value)["success"] is False and PRIVATE not in value
    failed = project_cloud_tool_result("web_search", {
        "success": False, "message": PRIVATE, "credentials": {"key": PRIVATE},
    })
    assert not json.loads(failed)["success"] and PRIVATE not in failed
    checks += 1

    # Invalid or credential-bearing public fields cause a *denial*, not a
    # fallback to full serialization or printing rejected input.
    for bad_result in (
        {"success": True, "results": [{"title": "safe", "content": "api_key=secret1234"}]},
        {"success": True, "results": [{"url": "https://example.org/p?token=secret1234"}]},
        {"success": True, "results": "non-list"},
    ):
        rejected(lambda bad_result=bad_result: project_cloud_tool_result(
            "web_search", bad_result))
    rejected(lambda: project_cloud_tool_result("web_read", [PRIVATE]))
    checks += 1

    # Function result follow-up includes ONLY its admitted projection.  It
    # references the response created in this same permitted cloud turn.
    tool = SimpleNamespace(type="function_call", name="get_weather",
                           call_id="call_public1", arguments='{"location":"Sydney"}')
    client = FakeResponses(tool)
    full = issue_cloud_export_grant(auth, prompt, purpose="explicit_cloud_request")
    safe_instructions = admit_cloud_initial(full, prompt).payload["instructions"]
    with mock.patch.object(openai_provider, "execute_tool", return_value=weather), provider_turn(auth):
        response = openai_provider.get_response(
            client, prompt, safe_instructions, cloud_export=full,
        )
    assert response == ("cloud answer", "resp_safe_two", None)
    assert len(client.calls) == 2
    second = client.calls[1]
    assert second["previous_response_id"] == "resp_safe_one"
    assert second["input"][0]["type"] == "function_call_output"
    assert PRIVATE not in json.dumps(second)
    assert "private_account" not in second["input"][0]["output"]
    checks += 1

    # Grant can be revoked by policy between SDK calls; then the second request
    # must not execute. The public result is never transmitted.
    revocable = issue_cloud_export_grant(auth, prompt, purpose="explicit_cloud_request")
    client = FakeResponses(tool)
    with mock.patch.object(openai_provider, "execute_tool", side_effect=lambda *a: (
        revocable.revoke() or {"success": True, "location": {"name": "Sydney"}}
    )), provider_turn(auth):
        rejected(lambda: openai_provider.get_response(
            client, prompt, admit_cloud_initial(
                issue_cloud_export_grant(auth, prompt, purpose="explicit_cloud_request"), prompt
            ).payload["instructions"], cloud_export=revocable,
        ))
    assert len(client.calls) == 1
    checks += 1

    # Source tool schemas must be verified before exposure.  No newly registered
    # tool or private description can be exported by mutating the source list.
    reviewed = admit_cloud_tool_definitions(CLOUD_TOOLS)
    assert {x["name"] for x in reviewed} == {"web_search", "web_read", "get_weather"}
    assert all("Oliver" not in json.dumps(x) for x in reviewed)
    rejected(lambda: admit_cloud_tool_definitions(CLOUD_TOOLS + [
        {"name": "read_email", "description": PRIVATE}
    ]))
    checks += 1

    # Invalid response IDs and function-call identifiers cannot be included.
    rejected(lambda: admit_cloud_tool_followup(
        grant, prompt, tool_name="get_weather", tool_result=weather,
        response_id="resp_1", call_id="bad id " + PRIVATE,
    ))
    rejected(lambda: admit_cloud_tool_followup(
        grant, prompt, tool_name="get_weather", tool_result=weather,
        response_id=[PRIVATE], call_id="call1",
    ))
    checks += 1

    # Full outbound admission includes the tool declarations, model and every
    # other SDK field, with no extra application instructions.
    clean_grant = issue_cloud_export_grant(auth, prompt, purpose="explicit_cloud_request")
    clean_initial = admit_cloud_initial(clean_grant, prompt)
    final = admit_cloud_sdk_request(
        clean_grant, prompt, clean_initial, model=openai_provider.MODEL,
        registry_tools=CLOUD_TOOLS,
    )
    assert set(final.payload) == {
        "model", "tools", "parallel_tool_calls", "input",
        "instructions", "previous_response_id",
    }
    assert set(final.manifest.field_names) == set(final.payload)
    assert "reviewed_public_tool_schemas" in final.manifest.data_classes
    assert PRIVATE not in json.dumps(final.payload)
    checks += 1

    # A caller cannot tamper with an admitted object after its digest is sealed
    # to smuggle new data into the SDK builder.
    tampered = admit_cloud_initial(clean_grant, prompt)
    tampered.payload["input"] = PRIVATE
    rejected(lambda: admit_cloud_sdk_request(
        clean_grant, prompt, tampered, model=openai_provider.MODEL,
        registry_tools=CLOUD_TOOLS,
    ))
    checks += 1

    # One grant covers at most one initial request and one follow-up, not a
    # fresh unbounded export on repeated provider invocation.
    once = issue_cloud_export_grant(auth, prompt, purpose="explicit_cloud_request")
    safe = admit_cloud_initial(once, prompt).payload["instructions"]
    consumed_client = FakeResponses()
    openai_provider.get_response(consumed_client, prompt, safe, cloud_export=once)
    rejected(lambda: openai_provider.get_response(
        consumed_client, prompt, safe, cloud_export=once,
    ))
    assert len(consumed_client.calls) == 1
    checks += 1

    # Failures must not echo private user data into diagnostic exception texts.
    try:
        issue_cloud_export_grant(auth, "password: SECRET999", purpose="approved_cloud_escalation")
        raise AssertionError("expected denial")
    except CloudExportDenied as err:
        assert "SECRET999" not in str(err)
    checks += 1

    # Provider/SDK exceptions can contain raw request bodies.  Neither route
    # may propagate that sensitive exception text to application diagnostics.
    class LeakyCloud:
        def get_response(self, *args, **kwargs):
            raise RuntimeError("Provider payload echoed: " + PRIVATE)
    for approved_route in (False, True):
        try:
            if approved_route:
                router.approve_cloud_escalation(
                    {"module": LeakyCloud(), "client": object()}, prompt,
                    "private " + PRIVATE, core_authority=auth,
                )
            else:
                router.route_message(
                    {"module": object(), "client": object()},
                    {"module": LeakyCloud(), "client": object()},
                    "/cloud " + prompt, "private " + PRIVATE,
                    core_authority=auth,
                )
            raise AssertionError("expected cloud failure")
        except CloudExportDenied as err:
            assert PRIVATE not in str(err)
    checks += 1

    # Also sanitise a raw SDK exception at provider ingress, not only in router.
    class LeakySDK:
        def create(self, **_kwargs):
            raise RuntimeError("SDK sent secret " + PRIVATE)
    fresh = issue_cloud_export_grant(auth, prompt, purpose="explicit_cloud_request")
    safe = admit_cloud_initial(fresh, prompt).payload["instructions"]
    try:
        openai_provider.get_response(
            SimpleNamespace(responses=LeakySDK()), prompt, safe,
            cloud_export=fresh,
        )
        raise AssertionError("expected SDK failure")
    except CloudExportDenied as err:
        assert PRIVATE not in str(err)
    checks += 1

    print(f"Mairon S3 cloud export admission: {checks}/{checks} PASS")


if __name__ == "__main__":
    run()
