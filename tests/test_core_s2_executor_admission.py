"""S2 offline executor admission / calendar effect tests: no SDK, accounts or real effects."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
import s1_offline_bootstrap  # noqa: F401 -- intentionally inert SDK stand-ins

from core.answer_contract import AnswerContract
from core.authority_handoff import seal_prepared_turn
from core.cloud_export import issue_cloud_export_grant, admit_cloud_initial
from core.action_approval import issue_calendar_ticket
from core import action_manager, router
from core.calendar_proposal_guard import build_calendar_approval_from_user_request
from datetime import datetime
from zoneinfo import ZoneInfo
from ai import openai_provider
from tools import calendar_tools, tool_registry
from tools.tool_admission import (
    admitted_tools, internal_scope, provider_turn, provider_tool_scope,
    run_internal_tool,
)


def authority(intent="factual_question", private=False, action=None):
    c = AnswerContract(
        task="respond", speech_act="question", intent=intent,
        subject="offline fixture", authority="test_core",
        epistemic_mode="classify_then_verify", allow_new_factual_claims=True,
    )
    turn = SimpleNamespace(
        intent=intent, requested_action=action, requires_private_data=private,
    )
    route = SimpleNamespace(
        authority="test_core", mode="classify_then_verify",
        verification_required=False, private_data_required=private,
        live_data_required=False,
    )
    return seal_prepared_turn(SimpleNamespace(
        answer_contract=c, turn=turn, epistemic_route=route,
    ))


def proposed_event():
    return {
        "type": "create_calendar_event", "summary": "Offline fixture appointment",
        "start_time": "2026-11-10T10:00:00", "end_time": "2026-11-10T11:00:00",
        "location": "", "description": "",
    }


class FakeCalendarService:
    def __init__(self):
        self.inserted = []
    def events(self):
        return self
    def insert(self, **kwargs):
        self.inserted.append(kwargs)
        return self
    def execute(self):
        return {"id": "offline_fixture_event"}


class FakeCloud:
    def __init__(self, item):
        self.item = item
        self.requests = []
        self.responses = self
    def create(self, **kwargs):
        self.requests.append(kwargs)
        if len(self.requests) == 1:
            return SimpleNamespace(output=[self.item], id="test_first", output_text="")
        return SimpleNamespace(output=[], id="test_second", output_text="done")


def run():
    n = 0
    with mock.patch.object(tool_registry, "get_weather", return_value={"success": True}) as weather, \
         mock.patch.object(tool_registry, "read_email", return_value={"success": True}) as email, \
         mock.patch.object(tool_registry, "list_memories", return_value={"success": True}) as memory:
        # Denied by default, including no-argument tools. Unknown-name response retained.
        assert tool_registry.execute_tool("get_weather", {"location": "Sydney"})["success"] is False
        assert tool_registry.execute_tool("list_memories", {})["success"] is False
        assert tool_registry.execute_tool("totally_unknown", {})["message"] == "Unknown tool: totally_unknown"
        assert not weather.called and not memory.called
        n += 1

        public = authority()
        scope = provider_tool_scope("local", public, ["get_weather", "read_email", "list_memories"])
        with admitted_tools(scope):
            assert tool_registry.execute_tool("get_weather", {"location": "Sydney"})["success"]
            assert tool_registry.execute_tool("read_email", {"message_id": "private"})["success"] is False
            assert tool_registry.execute_tool("list_memories", {})["success"] is False
        assert weather.call_count == 1 and not email.called and not memory.called
        n += 1

        # Cloud's registered private names cannot be invoked even if a malicious
        # provider returns them, and widening the advertised pool cannot help.
        scope = provider_tool_scope("cloud", public, ["get_weather", "read_email", "list_memories"])
        with admitted_tools(scope):
            assert tool_registry.execute_tool("read_email", {"message_id": "private"})["success"] is False
            assert tool_registry.execute_tool("list_memories", {})["success"] is False
            assert tool_registry.execute_tool("get_weather", {"location": "Sydney"})["success"]
        assert weather.call_count == 2 and not email.called and not memory.called
        n += 1

        # Source schema is enforced at the actual executor: never invoke on bad data.
        with admitted_tools(provider_tool_scope("local", public, ["get_weather"])):
            for bad in ("{", "[]", [], None, 0, {"location": 7},
                        {"location": "Sydney", "secret": "x"}, {}, "null"):
                assert tool_registry.execute_tool("get_weather", bad)["success"] is False, bad
        assert weather.call_count == 2
        n += 1

        # No-arg tool cannot be invoked with a malformed payload or extra field.
        private = authority(private=True)
        scope = provider_tool_scope("local", private, ["list_memories"])
        with admitted_tools(scope):
            for bad in ("{", "[]", [], {"query": "something"}, None):
                assert tool_registry.execute_tool("list_memories", bad)["success"] is False
            assert tool_registry.execute_tool("list_memories", {})["success"]
        assert memory.call_count == 1
        n += 1

        # Even an explicitly named write is impossible without matching Core intent/action.
        write_scope = provider_tool_scope("local", public, ["set_wake_alarm"])
        with admitted_tools(write_scope):
            assert tool_registry.execute_tool("set_wake_alarm", {"date": "2026-11-10", "time": "07:00"})["success"] is False
        n += 1

        # A calendar-only model pool cannot run a registered launch tool.
        calendar_auth = authority(intent="calendar_event_creation_request", private=True)
        calendar_scope = provider_tool_scope("local", calendar_auth, ["request_calendar_event_creation"])
        with admitted_tools(calendar_scope):
            assert tool_registry.execute_tool("launch_application", {"app_name": "notepad"})["success"] is False
        n += 1

        # Trusted scoped research and Core reads retain their existing optional defaults.
        with mock.patch.object(tool_registry, "find_emails", return_value={"success": True}) as find:
            assert run_internal_tool("core.email_search", "find_emails", {"search_text": "fixture"})["success"]
            assert find.call_count == 1
            assert run_internal_tool("core.email_search", "delete_memory", {"query": "fixture"})["success"] is False
            assert find.call_count == 1
        n += 1

        # Strict missing-required, wrong-typed boolean/integer, enum rejection.
        with admitted_tools(provider_tool_scope("local", private, ["get_recent_emails", "get_route"])):
            assert tool_registry.execute_tool("get_recent_emails", {"days": True, "max_results": 5, "unread_only": False})["success"] is False
            assert tool_registry.execute_tool("get_recent_emails", {"days": 1})["success"] is False
            assert tool_registry.execute_tool("get_route", {"origin": "a", "destination": "b", "mode": "wrong"})["success"] is False
        n += 1

        # The actual cloud provider feeds its raw model arguments through the guard.
        for toolname, arguments, allowed in (
            ("list_memories", "{}", False),
            ("read_email", '{"message_id":"private"}', False),
            ("get_weather", '{"location":"Sydney"}', True),
            ("get_weather", "[]", False),
        ):
            call = SimpleNamespace(type="function_call", name=toolname,
                                   arguments=arguments, call_id="c1")
            client = FakeCloud(call)
            grant = issue_cloud_export_grant(
                public, "offline question", purpose="explicit_cloud_request",
            )
            instructions = admit_cloud_initial(grant, "offline question").payload["instructions"]
            with provider_turn(public):
                answer, state, _ = openai_provider.get_response(
                    client, "offline question", instructions, cloud_export=grant,
                )
            assert answer == "done" and state == "test_second"
            assert len(client.requests) == 2
            tool_result = __import__("json").loads(client.requests[1]["input"][0]["output"])
            assert bool(tool_result.get("success")) is allowed, toolname
        assert not email.called and memory.call_count == 1
        n += 1

    event = proposed_event()
    calendar_auth = authority(intent="calendar_event_creation_request", private=True)
    assert issue_calendar_ticket(event, authority()) is None
    assert issue_calendar_ticket({"type": "create_calendar_event", "summary": "missing"}, calendar_auth) is None
    n += 1

    calendar = FakeCalendarService()
    with mock.patch.object(calendar_tools, "create_calendar_service", return_value=calendar), \
         mock.patch.object(calendar_tools, "normalise_event", lambda item: item):
        # The final Google-Calendar effect boundary rejects direct calls too.
        direct = calendar_tools.create_calendar_event(
            event["summary"], event["start_time"], event["end_time"]
        )
        assert direct["success"] is False and not calendar.inserted
        n += 1

        ticket = issue_calendar_ticket(event, calendar_auth)
        assert ticket is not None
        done = action_manager.execute_approved_action(event, approval_ticket=ticket)
        assert done["success"] and len(calendar.inserted) == 1
        assert action_manager.execute_approved_action(event, approval_ticket=ticket)["success"] is False
        assert len(calendar.inserted) == 1
        n += 1

        altered = issue_calendar_ticket(event, calendar_auth)
        other = {**event, "summary": "Tampered title"}
        assert action_manager.execute_approved_action(other, approval_ticket=altered)["success"] is False
        assert len(calendar.inserted) == 1
        n += 1

        expired = issue_calendar_ticket(event, calendar_auth)
        expired._issued_at -= 601
        assert action_manager.execute_approved_action(event, approval_ticket=expired)["success"] is False
        n += 1

        revoked = issue_calendar_ticket(event, calendar_auth)
        revoked.revoke()
        assert action_manager.execute_approved_action(event, approval_ticket=revoked)["success"] is False
        assert action_manager.execute_approved_action(event)["success"] is False
        assert len(calendar.inserted) == 1
        n += 1

        route_ticket = issue_calendar_ticket(event, calendar_auth)
        route_result = router.RouteResult(
            status="action_approval_required", pending_action=dict(event),
            approval_ticket=route_ticket, core_authority=calendar_auth,
        )
        routed = router.approve_pending_action(route_result)
        assert routed.status == "answered" and len(calendar.inserted) == 2
        router.approve_pending_action(route_result)
        assert len(calendar.inserted) == 2
        n += 1

        declined_ticket = issue_calendar_ticket(event, calendar_auth)
        declined = router.RouteResult(
            status="action_approval_required", pending_action=dict(event),
            approval_ticket=declined_ticket, core_authority=calendar_auth,
        )
        router.decline_pending_action(declined)
        assert action_manager.execute_approved_action(event, approval_ticket=declined_ticket)["success"] is False
        assert len(calendar.inserted) == 2
        n += 1

    # A real Core-validated calendar proposal uses None for absent optionals.
    # It must still succeed after exact approval without a live account.
    proposal = build_calendar_approval_from_user_request(
        user_input=(
            "actually add a mock interview practice block to my calendar "
            "for Wednesday from 7pm to 7:30pm"
        ),
        now=datetime(2026, 10, 1, 16, 54, tzinfo=ZoneInfo("Australia/Sydney")),
    )
    assert proposal is not None
    assert proposal.action["location"] is None and proposal.action["description"] is None
    fresh_service = FakeCalendarService()
    with mock.patch.object(calendar_tools, "create_calendar_service", return_value=fresh_service), \
         mock.patch.object(calendar_tools, "normalise_event", lambda item: item):
        ticket = issue_calendar_ticket(proposal.action, calendar_auth)
        assert ticket is not None
        result = action_manager.execute_approved_action(proposal.action, approval_ticket=ticket)
        assert result["success"] and len(fresh_service.inserted) == 1
    n += 1

    print(f"Mairon S2 offline executor admission: {n}/{n} PASS")


if __name__ == "__main__":
    run()
