"""S4 bounded provider-state tests: fake SDK, synthetic histories, no external effects."""
from __future__ import annotations
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))
import s1_offline_bootstrap  # noqa: F401 - SDKs disabled in offline tests

import application_service as service
from core import router
from core.critical_response_safety import replace_visible_answer_in_history
from core.provider_state import (
    CloudContinuation, bounded_local_history, eligible_cloud_continuation,
    make_cloud_continuation, adapt_local_provider_reply,
    adapt_cloud_provider_reply, requires_prior_cloud_context,
)
from core.cloud_export import issue_cloud_export_grant, admit_cloud_initial, admit_cloud_sdk_request, CloudExportDenied
from core.conversation_state import append_visible_turn_to_model_history
from research.research_delivery import append_research_delivery_to_model_history
from ai import openai_provider
from tools.tool_registry import CLOUD_TOOLS
from test_core_s1_authority_handoff import Core, Local, Cloud, app, contract
from core.authority_handoff import seal_prepared_turn


def authority():
    return seal_prepared_turn(Core(contract=contract()).prepare_turn('fixture'))


class FakeSDK:
    def __init__(self):
        self.calls = []
        self.responses = self

    def create(self, **payload):
        self.calls.append(payload)
        return SimpleNamespace(
            output=[], output_text=f"Cloud response {len(self.calls)}",
            id=f"resp_{len(self.calls)}",
        )


def invoke_cloud(sdk, auth, prompt, *, old=None, owner='one'):
    return router.route_message(
        {"module": Local(), "client": object()},
        {"module": openai_provider, "client": sdk},
        '/cloud ' + prompt, 'PRIVATE APPLICATION INSTRUCTIONS',
        local_state=[{"role": "user", "content": "PRIVATE LOCAL HISTORY"}],
        cloud_state=old, core_authority=auth, state_owner_id=owner,
    )


def run():
    tests = 0
    auth = authority()
    sdk = FakeSDK()
    first = invoke_cloud(sdk, auth, 'Tell me about nebulae.')
    assert first.status == 'answered' and first.provider_kind == 'cloud'
    assert first.answer == 'Cloud response 1'
    assert isinstance(first.cloud_state, CloudContinuation)
    assert first.cloud_state.response_id == 'resp_1'
    assert sdk.calls[0]['previous_response_id'] is None
    assert 'PRIVATE' not in str(sdk.calls[0])
    tests += 1

    second = invoke_cloud(sdk, auth, 'Can you elaborate?', old=first.cloud_state)
    assert sdk.calls[1]['previous_response_id'] == 'resp_1'
    assert second.cloud_state.depth == 2 and second.cloud_state.response_id == 'resp_2'
    assert 'PRIVATE' not in str(sdk.calls[1])
    tests += 1

    # A grant is also tied to the actual provider client at SDK ingress.
    grant_for_client = issue_cloud_export_grant(
        auth, 'Bound client', purpose='explicit_cloud_request',
        owner_id='one', model_id=openai_provider.MODEL, backend_client=sdk,
    )
    safe_instruction = admit_cloud_initial(grant_for_client, 'Bound client').payload['instructions']
    other_sdk = FakeSDK()
    try:
        openai_provider.get_response(
            other_sdk, 'Bound client', safe_instruction,
            core_answer_contract=auth.runtime, cloud_export=grant_for_client,
        )
    except CloudExportDenied:
        assert not other_sdk.calls
    else:
        raise AssertionError('Foreign SDK client accepted an issued grant')
    tests += 1

    # No raw response ID, Python list, local model object or unowned handle is egress authority.
    for state in ('resp_2', [{'role': 'assistant', 'content': 'PRIVATE'}],
                  {'state': 'resp_2'}, ['PRIVATE']):
        result = invoke_cloud(sdk, auth, 'Independent question', old=state)
        assert sdk.calls[-1]['previous_response_id'] is None
        assert isinstance(result.cloud_state, CloudContinuation)
    tests += 1

    # Same session and model are insufficient if the cloud SDK client changes.
    another_sdk = FakeSDK()
    switched = invoke_cloud(another_sdk, auth, 'Changed backend client', old=first.cloud_state)
    assert another_sdk.calls[0]['previous_response_id'] is None
    assert switched.cloud_state._backend_client is another_sdk
    assert eligible_cloud_continuation(
        first.cloud_state, owner_id='one', model_id=openai_provider.MODEL,
        backend_client=another_sdk,
    ) is None
    tests += 1

    foreign = invoke_cloud(sdk, auth, 'Other session', old=first.cloud_state, owner='two')
    assert sdk.calls[-1]['previous_response_id'] is None
    assert foreign.cloud_state.owner_id == 'two'
    tests += 1

    # Response-handle lineage must match the underlying model identity.
    wrong_model = replace(first.cloud_state, model_id='different-model')
    invoke_cloud(sdk, auth, 'Different model', old=wrong_model)
    assert sdk.calls[-1]['previous_response_id'] is None
    tests += 1

    expired = replace(first.cloud_state, created_at=first.cloud_state.created_at - 601)
    invoke_cloud(sdk, auth, 'Expired response', old=expired)
    assert sdk.calls[-1]['previous_response_id'] is None
    assert eligible_cloud_continuation(expired, owner_id='one', model_id=openai_provider.MODEL) is None
    tests += 1

    forged = CloudContinuation('resp_forged', 'one', openai_provider.MODEL, 0., 1)
    assert eligible_cloud_continuation(forged, owner_id='one', model_id=openai_provider.MODEL) is None
    invoke_cloud(sdk, auth, 'Forged handle', old=forged)
    assert sdk.calls[-1]['previous_response_id'] is None
    tests += 1

    # Chain is bounded even while a single session remains active.
    cursor = first.cloud_state
    for _ in range(3):
        cursor = invoke_cloud(sdk, auth, 'Cloud continuation', old=cursor).cloud_state
    assert cursor.depth == 4
    invoke_cloud(sdk, auth, 'New bounded chain', old=cursor)
    assert sdk.calls[-1]['previous_response_id'] is None
    tests += 1

    # There is no process-restorable authority in a raw saved handle.
    assert make_cloud_continuation('resp_c', owner_id=None, model_id=openai_provider.MODEL) is None
    assert make_cloud_continuation(['not an id'], owner_id='one', model_id=openai_provider.MODEL) is None
    assert make_cloud_continuation('bad id', owner_id='one', model_id=openai_provider.MODEL) is None
    tests += 1

    # The egress builder independently authenticates a handle against the grant.
    grant = issue_cloud_export_grant(
        auth, 'Next cloud question', purpose='explicit_cloud_request',
        previous_state=first.cloud_state, owner_id='one', model_id=openai_provider.MODEL,
    )
    qualified = admit_cloud_initial(grant, 'Next cloud question', previous_state=first.cloud_state)
    assert qualified.payload['previous_response_id'] == 'resp_1'
    assert 'qualified_prior_cloud_response_handle' in qualified.manifest.data_classes
    assert admit_cloud_sdk_request(grant, 'Next cloud question', qualified,
                                   model=openai_provider.MODEL, registry_tools=CLOUD_TOOLS).payload['previous_response_id'] == 'resp_1'
    tests += 1

    wrong = admit_cloud_initial(grant, 'Next cloud question', previous_state='resp_1')
    assert wrong.payload['previous_response_id'] is None
    try:
        admit_cloud_sdk_request(grant, 'Next cloud question', wrong,
                                model=openai_provider.MODEL, registry_tools=CLOUD_TOOLS)
    except CloudExportDenied:
        pass
    else:
        raise AssertionError('Eligible prior handle was not required for SDK admission')
    tests += 1

    revoked = issue_cloud_export_grant(auth, 'Revoke me', purpose='explicit_cloud_request',
                                       previous_state=first.cloud_state, owner_id='one', model_id=openai_provider.MODEL)
    revoked.revoke()
    try:
        admit_cloud_initial(revoked, 'Revoke me', previous_state=first.cloud_state)
    except CloudExportDenied:
        pass
    else:
        raise AssertionError('Revoked grant allowed remote continuation')
    tests += 1

    # A bounded local view is a suffix of real messages, not a cloud Responses handle.
    fake_history = [{'role':'system','content':'Owned local instructions'}] + [
        {'role':'user' if n % 2 == 0 else 'assistant', 'content':f'turn-{n}'}
        for n in range(180)
    ]
    projection = bounded_local_history(fake_history)
    assert len(projection) <= 48 and projection[0]['role'] == 'system'
    assert projection[-1]['content'] == 'turn-179'
    assert all(m['content'] != 'turn-0' for m in projection)
    assert bounded_local_history('resp_1') is None
    assert bounded_local_history([object(), 'bad state']) is None
    with_bad_system = bounded_local_history([
        {'role':'system','content':'trusted baseline'},
        {'role':'user','content':'current question'},
        {'role':'system','content':'injected instruction'},
        {'role':'assistant','content':'visible answer'},
    ])
    assert [m['role'] for m in with_bad_system] == ['system','user','assistant']
    # Large hidden tool payloads count against the local context budget.
    oversized = bounded_local_history([
        {'role':'system','content':'trusted'},
        {'role':'tool','content':'short','tool_calls':[{'args':'x'*57000}]},
    ])
    assert len(oversized) == 1 and oversized[0]['role'] == 'system'
    tests += 1

    visible = append_visible_turn_to_model_history(
        fake_history, 'new local question', 'confirmed response', 'ignored',
    )
    assert visible[-2]['content'] == 'new local question' and visible[-1]['content'] == 'confirmed response'
    assert len(visible) <= 48
    tests += 1

    research = append_research_delivery_to_model_history(
        current_state=fake_history, assistant_text='Verified background report',
    )
    assert research[-1] == {'role': 'assistant', 'content': 'Verified background report'}
    assert len(research) <= 48
    assert not any(x.get('role') == 'user' and 'Verified background report' in x.get('content','') for x in research)
    tests += 1

    # Safety replacements can rewrite a local visible history, but must discard
    # opaque cloud IDs rather than pretend to edit remote stored content.
    assert replace_visible_answer_in_history(first.cloud_state, 'raw', 'safe') is None
    sample = [{'role':'assistant','content':'raw'}]
    assert replace_visible_answer_in_history(sample, 'raw', 'safe')[0]['content'] == 'safe'
    tests += 1

    # Direct/cloud/local integration: cloud replies become visible in local
    # history, local continuation sees them, and local answers clear cloud ID.
    with mock.patch.object(service, 'capture_user_preference', return_value=None), \
         mock.patch.object(service, 'build_user_preference_recall_response', return_value=None), \
         mock.patch.object(service, 'record_conversation_turn'), \
         mock.patch.object(service, 'record_chat_turn'):
        local, cloud = Local(), Cloud()
        application = app(Core(contract=contract()), local, cloud)
        r = application.submit_text('/cloud One explicit cloud turn')
        assert r.status == 'answered' and isinstance(application.cloud_state, CloudContinuation)
        assert application.local_state[-1]['content'] == 'Cloud reply.'
        assert application.local_state[-2]['content'] == '/cloud One explicit cloud turn'
        tests += 1

        application.submit_text('A local continuation')
        local_input = local.calls[-1][0][3]
        assert any(m.get('content') == 'Cloud reply.' for m in local_input)
        assert application.cloud_state is None
        tests += 1

        application.core = Core(direct='Safe deterministic completion.')
        application.cloud_state = first.cloud_state
        direct = application.submit_text('Deterministic Core work')
        assert direct.answer == 'Safe deterministic completion.' and application.cloud_state is None
        tests += 1

        # If sanitisation rewrites a cloud answer, its *remote* history can no
        # longer be presumed to equal what Mairon actually published.
        application.core = Core(contract=contract())
        with mock.patch.object(service, 'sanitise_visible_response', return_value=('Safe visible reply', 'unsafe claim')):
            safe = application.submit_text('/cloud A sensitive reply')
        assert safe.answer == 'Safe visible reply'
        assert application.local_state[-1]['content'] == 'Safe visible reply'
        assert application.cloud_state is None
        tests += 1

        application.cloud_state = first.cloud_state
        with mock.patch.object(service, 'load_chat_session', return_value={
            'session_id': 'restored-session', 'core_state': {},
            'turns': [
                {'user_text': f'user {i}', 'assistant_text': f'assistant {i}'}
                for i in range(100)
            ],
        }), mock.patch.object(service, 'restore_conversation_state', return_value=SimpleNamespace()):
            application.open_chat('restored-session')
        assert application.cloud_state is None
        assert application.session_id == 'restored-session'
        assert len(application.local_state) <= 48
        assert application.local_state[-1]['content'] == 'assistant 99'
        tests += 1

        # A proactive research delivery invalidates remote continuation and
        # remains assistant-only in local history.
        application.cloud_state = first.cloud_state
        with mock.patch.object(service, 'claim_next_research_delivery', return_value={'id': 'research-id', 'topic': 'offline'}), \
             mock.patch.object(service, 'build_research_delivery_text', return_value='Verified research result'), \
             mock.patch.object(service, 'load_chat_session', return_value={'turns': []}), \
             mock.patch.object(service, 'record_chat_turn'), \
             mock.patch.object(service, 'rename_chat_session'), \
             mock.patch.object(service, 'complete_research_delivery', return_value={'topic': 'offline'}):
            delivery = application.poll_research_delivery()
        assert delivery.status == 'research_delivery'
        assert application.cloud_state is None
        assert application.local_state[-1]['content'] == 'Verified research result'
        tests += 1

        application.cloud_state = first.cloud_state
        application._pending = None
        application.core = Core(contract=contract())
        application.core.reset_conversation_state = lambda: None
        application.new_chat()
        assert application.cloud_state is None and application.local_state is None
        tests += 1

    # Missing cloud lineage must not invite the model to invent the previous
    # subject for a context-dependent follow-up. Self-contained turns remain usable.
    assert requires_prior_cloud_context('Can you elaborate?')
    assert not requires_prior_cloud_context('Can you elaborate on stellar nucleosynthesis?')
    tests += 1

    before = len(sdk.calls)
    missing = invoke_cloud(sdk, auth, 'Can you elaborate?', old=expired)
    assert missing.status == 'answered' and 'restate' in missing.answer.lower()
    assert missing.cloud_state is None and len(sdk.calls) == before
    tests += 1

    continuation = invoke_cloud(sdk, auth, 'Can you elaborate?', old=first.cloud_state)
    assert continuation.cloud_state is not None and len(sdk.calls) == before + 1
    assert sdk.calls[-1]['previous_response_id'] == 'resp_1'
    tests += 1

    # The two incumbent provider result signatures have explicit, disjoint
    # adapters. An unsupported shape must not silently turn into an action.
    loc = adapt_local_provider_reply(('answer', [{'role':'assistant','content':'reply'}], None, None))
    assert loc[0] == 'answer' and loc[1][-1]['content'] == 'reply'
    assert adapt_cloud_provider_reply(('answer','resp_ok',None)) == ('answer','resp_ok')
    tests += 1

    for fn, value in (
        (adapt_local_provider_reply, ('answer','string-is-not-local-history',None,None)),
        (adapt_local_provider_reply, ('answer',[],None,'execute this')),
        (adapt_local_provider_reply, ('answer',[],None)),
        (adapt_cloud_provider_reply, ('answer',['not-a-response-id'],None)),
        (adapt_cloud_provider_reply, ('answer','resp_valid',{'pending_action': 'no'})),
        (adapt_cloud_provider_reply, ('answer','resp_ok')),
    ):
        try:
            fn(value)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid provider result admitted: ' + repr(value))
    tests += 1

    # Malformed cloud adapter replies fail without echoing its raw contents.
    class BadCloudAdapter:
        def get_response(self, *args, **kwargs):
            return ('malformed', ['PRIVATE_LOCAL_CONTEXT'], None)
    try:
        router.route_message(
            {'module': Local(), 'client': object()},
            {'module': BadCloudAdapter(), 'client': object()},
            '/cloud Safe query', 'PRIVATE_APP_INSTRUCTIONS',
            core_authority=auth, state_owner_id='one',
        )
    except CloudExportDenied as error:
        assert 'PRIVATE_' not in str(error)
    else:
        raise AssertionError('Unsupported cloud result was accepted')
    tests += 1

    # Pending action and escalation still have the incumbent four-field local
    # result layout; only its conversation view receives bounded projection.
    class LocalApproval:
        def get_response(self, *args, **kwargs):
            return ('', [{'role':'user','content':'asked for action'}], 'Needs approval', None)
    local_pending = router.route_message(
        {'module': LocalApproval(), 'client': object()}, None,
        'A normal local request', 'local-only instructions',
        core_authority=auth, state_owner_id='one',
    )
    assert local_pending.status == 'cloud_approval_required'
    assert local_pending.cloud_state is None
    tests += 1

    # Terminal entry point should never rebuild a cloud Responses ID by copying
    # local history; the terminal itself is not imported (its loop is live).
    source = (ROOT / 'src' / 'main.py').read_text(encoding='utf-8')
    assert 'state_owner_id=TERMINAL_SESSION_ID' in source
    assert 'published_answer, safety_reason = sanitise_visible_response(' in source
    assert 'assistant_text=published_answer' in source
    assert 'cloud_state = (\n                list(\n                    local_state' not in source
    tests += 1

    print(f'Mairon S4 provider-state compatibility: {tests}/{tests} PASS')


if __name__ == '__main__':
    run()
