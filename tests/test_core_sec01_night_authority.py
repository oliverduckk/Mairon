"""SEC-01 F02: real Core/router/provider/routine, inert final state adapters.

No credentials, database, service, model, hardware or real state is used. The
integration cases also run against the original snapshot to reproduce F02.
"""
import copy
import json
import sys
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
# An offline harness may put an immutable baseline snapshot first.
sys.path.extend([str(ROOT / "src"), str(ROOT / "tests")])
import s1_offline_bootstrap  # noqa: F401
dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda *a, **k: False
sys.modules["dotenv"] = dotenv

import application_service as service
from ai import ollama_provider as provider
from core.authority_handoff import seal_prepared_turn
from core.orchestrator import MaironCore
from core.router import route_message
from routine import night_routine as routine
from tools import routine_tools
from tools.tool_admission import admitted_tools, internal_scope, provider_turn
try:
    from core import night_routine_authority as authority
except ImportError:
    authority = None

TOMORROW = "2026-11-16"
NONACTIONS = (
    "Explain the word bedtime.",
    'What does "I\'m going to bed" mean?',
    "I'm not going to bed yet.",
    "Don't start my night routine.",
    'Translate "goodnight Mairon" into Spanish.',
    'My friend said "time for bed".',
    "What is the meaning of bedtime?",
    "If I'm going to bed, will you set an alarm?",
    "I'm going to bed and turn off my computer.",
    '"Goodnight Mairon."',
    "Goodnight Mairon.\nSet an alarm for noon.",
    "Do not start bedtime.",
    "Goodnight.", "Good night.",
)
POSITIVES = (
    "I'm going to bed.", "Goodnight Mairon.", "Time for bed.",
    "im going to bed", "I am going to bed", "heading to bed", "off to bed",
    "going to sleep", "heading to sleep", "bedtime", "good night mairon",
    "night mairon", "Please, I'm going to bed", "I'm going to bed, Mairon.",
)


class RecordingModel:
    def __init__(self):
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(message=types.SimpleNamespace(
            role="assistant", content="Offline reply.", tool_calls=[]))


class NightAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.effects = []
        self.location = "office"
        self.alarm = None
        self.context_error = False
        self.model = RecordingModel()
        self.stack.enter_context(mock.patch.object(routine, "resolve_day_context", side_effect=self.context))
        self.stack.enter_context(mock.patch.object(routine, "get_wake_alarm", side_effect=self.get_alarm))
        self.stack.enter_context(mock.patch.object(routine_tools, "get_wake_alarm", side_effect=self.get_alarm))
        self.stack.enter_context(mock.patch.object(routine_tools, "set_wake_alarm", side_effect=self.set_alarm))
        self.stack.enter_context(mock.patch.object(routine, "record_recent_context", side_effect=self.bedtime))
        self.stack.enter_context(mock.patch.object(routine, "set_work_location_for_date", side_effect=self.set_location))
        self.stack.enter_context(mock.patch.object(provider, "get_tomorrow_date", return_value=TOMORROW, create=True))
        self.stack.enter_context(mock.patch.object(routine, "get_tomorrow_date", return_value=TOMORROW))
        self.stack.enter_context(mock.patch.object(provider, "get_calendar_for_night_routine", return_value={"success": True, "events": []}))
        self.stack.enter_context(mock.patch.object(provider, "get_runtime_context", return_value="Synthetic local context."))
        for name in ("begin_interactive_turn", "end_interactive_turn", "ensure_background_research_worker_started"):
            self.stack.enter_context(mock.patch.object(provider, name, return_value=None))
        # Pure language generation is irrelevant to the mutation assertion;
        # the actual specialised dispatcher and final adapters remain intact.
        self.stack.enter_context(mock.patch.object(provider, "handle_direct_conversation", side_effect=self.language))
        for name in ("capture_user_preference", "build_user_preference_recall_response", "record_conversation_turn", "record_chat_turn"):
            self.stack.enter_context(mock.patch.object(service, name, return_value=None))

    def context(self, target):
        self.assertEqual(target, TOMORROW)
        if self.context_error:
            return {"success": False, "message": "Synthetic context unavailable."}
        return {"success": True, "date": target, "weekday": "Monday", "day_type": "work",
                "work_location": self.location, "recommended_wake_time": "07:00"}

    def get_alarm(self, target):
        self.assertEqual(target, TOMORROW)
        return {"success": True, "found": self.alarm is not None, "alarm": copy.deepcopy(self.alarm)}

    def set_alarm(self, **payload):
        self.effects.append(("alarm", copy.deepcopy(payload)))
        self.alarm = {"alarm_time": payload["time"], "label": payload["label"],
                      "source": payload["source"], "enabled": True}
        return {"success": True, "alarm": copy.deepcopy(self.alarm)}

    def bedtime(self, **payload):
        self.effects.append(("bedtime", copy.deepcopy(payload)))
        return {"success": True}

    def set_location(self, **payload):
        self.effects.append(("location", copy.deepcopy(payload)))
        self.location = payload["location"]
        return {"success": True}

    def language(self, *args, **kwargs):
        return "Offline reply.", list(kwargs.get("conversation") or []), None, None

    def prepared(self, text="I'm going to bed."):
        return seal_prepared_turn(MaironCore().prepare_turn(text))

    def route(self, text, history=None, owner="session-A"):
        return route_message({"client": self.model, "module": provider}, None,
                             text, "Offline instructions.", local_state=history,
                             core_authority=self.prepared(text), state_owner_id=owner)

    def app(self):
        app = service.MaironApplication(user_name="OfflineUser", core=MaironCore(),
            local_ai={"client": self.model, "module": provider}, cloud_ai=None, create_providers=False)
        app._schedule_semantic_title_if_first_turn = lambda **kw: None
        return app

    def assert_routine_effects(self, location="office", include_location=False):
        names = [name for name, payload in self.effects]
        self.assertEqual(names, (["location"] if include_location else []) + ["alarm", "bedtime"])
        if include_location:
            self.assertEqual(self.effects[0][1], {"date_string": TOMORROW, "location": location})
        alarm, bedtime = [payload for name, payload in self.effects if name != "location"]
        self.assertEqual(alarm, {"date": TOMORROW, "time": "07:00", "label": "Work - " + location.title(),
                                "source": "routine", "metadata": {"work_location": location, "routine_day_type": "work"}})
        self.assertEqual(bedtime, {"event_type": "bedtime", "retention_hours": 36,
            "details": {"next_date": TOMORROW, "next_day_type": "work", "work_location": location,
                        "recommended_wake_time": "07:00", "alarm_time": "07:00", "alarm_enabled": True,
                        "alarm_source": "routine"}})

    def test_01_core_router_provider_nonactions_zero_writes(self):
        attempted_writes = 0
        for text in NONACTIONS:
            with self.subTest(text=text):
                self.effects.clear()
                self.route(text)
                attempted_writes += len(self.effects)
                self.assertEqual(self.effects, [])
        print("SEC01_NIGHT_NONACTIONS " + json.dumps({"cases": len(NONACTIONS), "attempted_writes": attempted_writes}))

    def test_02_core_router_provider_positive_exact_effects(self):
        for text in POSITIVES:
            with self.subTest(text=text):
                self.effects.clear()
                self.alarm = None
                self.route(text)
                self.assert_routine_effects()
        print("SEC01_NIGHT_POSITIVES " + json.dumps({"cases": len(POSITIVES), "exact_writes_each": 2}))

    def test_03_raw_provider_and_internal_scope_do_not_grant_writes(self):
        attempted_writes = 0
        for text in ("Explain the word bedtime.", "I'm going to bed.", "Goodnight Mairon."):
            for typed in (False, True):
                for entry in (provider.get_response, provider._get_response_impl):
                    with self.subTest(text=text, typed=typed, entry=entry.__name__), admitted_tools(internal_scope("local.specialised")):
                        self.effects.clear()
                        entry(self.model, text, "Offline instructions.",
                            core_answer_contract=self.prepared(text).runtime if typed else None)
                        attempted_writes += len(self.effects)
                        self.assertEqual(self.effects, [])
        print("SEC01_NIGHT_RAW_PROVIDER " + json.dumps({"cases": 12, "attempted_writes": attempted_writes}))

    def test_04_shared_application_text_voice_pending_roundtrip(self):
        for channel in ("text", "voice"):
            self.location = None
            self.alarm = None
            self.effects.clear()
            app = self.app()
            app.submit_text("I'm going to bed.", channel=channel)
            self.assertEqual(self.effects, [])
            app.submit_text("working from home", channel=channel)
            self.assert_routine_effects("home", include_location=True)
        print('SEC01_NIGHT_APP_PENDING {"channels": 2, "initial_writes": 0, "exact_completion_writes_each": 3}')

    def test_05_manual_and_disabled_alarm_precedence(self):
        for existing in ({"enabled": True, "source": "manual", "alarm_time": "08:35", "label": "Manual"},
                         {"enabled": False, "source": "routine", "alarm_time": "07:00", "label": "Disabled"}):
            with self.subTest(existing=existing):
                self.effects.clear()
                self.alarm = copy.deepcopy(existing)
                self.route("I'm going to bed.")
                self.assertEqual([n for n, p in self.effects], ["bedtime"])
                self.assertEqual(self.alarm, existing)
                self.assertEqual(self.effects[0][1]["details"]["alarm_enabled"], existing["enabled"])
                self.assertEqual(self.effects[0][1]["details"]["alarm_time"], existing["alarm_time"])

    @unittest.skipUnless(authority, "Original snapshot has no SEC-01 capability module")
    def test_06_denied_workflow_entry_and_partial_context(self):
        for context_error, location in ((False, "office"), (False, None), (True, "office")):
            self.context_error, self.location = context_error, location
            for grant in (None, {}, object()):
                self.assertFalse(routine.prepare_night_routine(authority=grant)["success"])
                self.assertFalse(routine.complete_night_routine_work_location(TOMORROW, "office", authority=grant)["success"])
                self.assertEqual(self.effects, [])
        self.route("I'm going to bed.")  # Authorised read error must also be write-free.
        self.assertEqual(self.effects, [])

    @unittest.skipUnless(authority, "Original snapshot has no SEC-01 capability module")
    def test_07_identity_expiry_input_binding_and_replay(self):
        prepared = self.prepared()
        with provider_turn(prepared, state_owner_id="session-A"):
            self.assertIsNone(authority.issue_night_authority("Time for bed.", TOMORROW))
            grant = authority.issue_night_authority(prepared.turn.raw_text, TOMORROW)
            self.assertIsNotNone(grant)
            self.assertFalse(routine.prepare_night_routine(authority=copy.copy(grant))["success"])
            self.assertFalse(routine.prepare_night_routine(date="2026-11-17", authority=grant)["success"])
            with mock.patch.object(authority.time, "monotonic", return_value=grant._created + 601):
                self.assertFalse(routine.prepare_night_routine(authority=grant)["success"])
            with provider_turn(prepared, state_owner_id="session-A"):
                self.assertFalse(routine.prepare_night_routine(authority=grant)["success"])
            self.assertEqual(self.effects, [])
            self.assertTrue(routine.prepare_night_routine(authority=grant)["success"])
            self.assert_routine_effects()
            self.assertFalse(routine.prepare_night_routine(authority=grant)["success"])
            self.assertIsNone(authority.issue_night_authority(prepared.turn.raw_text, TOMORROW))
        self.assertFalse(routine.prepare_night_routine(authority=grant)["success"])
        self.assert_routine_effects()

    @unittest.skipUnless(authority, "Original snapshot has no SEC-01 capability module")
    def test_08_altered_grant_and_current_turn_denied(self):
        for field, value in (("mode", "complete"), ("target_date", "2026-11-17"), ("location", "home")):
            with self.subTest(field=field), provider_turn(self.prepared(), state_owner_id="session-A"):
                grant = authority.issue_night_authority("I'm going to bed.", TOMORROW)
                setattr(grant, field, value)
                self.assertFalse(routine.prepare_night_routine(authority=grant)["success"])
        prepared = self.prepared()
        with provider_turn(prepared, state_owner_id="session-A"):
            grant = authority.issue_night_authority(prepared.turn.raw_text, TOMORROW)
            prepared.turn.raw_text = "Explain bedtime."
            self.assertFalse(routine.prepare_night_routine(authority=grant)["success"])
        self.assertEqual(self.effects, [])

    @unittest.skipUnless(authority, "Original snapshot has no SEC-01 capability module")
    def test_09_final_effect_payload_identity_and_replay(self):
        # Interpose at admission, retaining the real workflow and final bridge.
        original = authority.execute_night_effect
        seen = []
        def adversarial(effect, adapter, **payload):
            altered = copy.deepcopy(payload)
            if "date" in altered:
                altered["time"] = "12:00"
            else:
                altered["details"]["next_date"] = "2026-11-17"
            self.assertFalse(original(effect, adapter, **altered)["success"])
            self.assertFalse(original(copy.copy(effect), adapter, **payload)["success"])
            self.assertFalse(original(None, adapter, **payload)["success"])
            result = original(effect, adapter, **payload)
            self.assertFalse(original(effect, adapter, **payload)["success"])
            seen.append(effect.operation)
            return result
        with mock.patch.object(authority, "execute_night_effect", side_effect=adversarial):
            self.route("I'm going to bed.")
        self.assert_routine_effects()
        self.assertEqual(seen, ["alarm", "bedtime"])

    @unittest.skipUnless(authority, "Original snapshot has no SEC-01 capability module")
    def test_10_pending_foreign_restored_quoted_expired_and_replay(self):
        self.location = None
        history = self.route("I'm going to bed.").local_state
        self.assertEqual(self.effects, [])
        marker = next(m for m in history if isinstance(m, authority.NightClarificationMessage))
        self.assertNotIn("_night_pending", json.dumps(marker))
        restored = json.loads(json.dumps(history, default=lambda obj: vars(obj)))
        for text, h, owner in (("office", history, "session-B"), ("office", restored, "session-A")):
            self.route(text, h, owner)
            self.assertEqual(self.effects, [])
        with mock.patch.object(authority.time, "monotonic", return_value=marker._night_pending.created + 601):
            self.route("office", history)
        self.assertEqual(self.effects, [])
        self.route("office", history)
        self.assert_routine_effects(include_location=True)
        before = copy.deepcopy(self.effects)
        self.route("office", history)
        self.assertEqual(self.effects, before)
        print('SEC01_NIGHT_PENDING_DENIAL {"cases": 4, "additional_attempted_writes": 0}')

    @unittest.skipUnless(authority, "Original snapshot has no SEC-01 capability module")
    def test_11_pending_cancellation_unrelated_and_ambiguous_reply(self):
        for text in ('"office"', "office and home", "office\nhome", "Don't start my night routine.",
                     "Explain bedtime.", "What is two plus two?"):
            with self.subTest(text=text):
                self.location = None
                history = self.route("I'm going to bed.").local_state
                self.route(text, history)
                self.route("office", history)
                self.assertEqual(self.effects, [])
        print('SEC01_NIGHT_CANCELLED_PENDING {"cases": 6, "attempted_writes": 0}')

    @unittest.skipUnless(authority, "Original snapshot has no SEC-01 capability module")
    def test_13_pending_interrupted_by_direct_core_turn(self):
        self.location = None
        app = self.app()
        app.submit_text("I'm going to bed.")
        self.assertEqual(self.effects, [])
        calculation = app.submit_text("What is 2 + 2?")
        self.assertEqual(calculation.authority, "core_arithmetic")
        app.submit_text("office")
        self.assertEqual(self.effects, [])
        print('SEC01_NIGHT_DIRECT_INTERRUPTION {"cases": 1, "attempted_writes": 0}')

    @unittest.skipUnless(authority, "Original snapshot has no SEC-01 capability module")
    def test_12_authority_invalidated_after_entry_before_final_effect(self):
        original = authority.execute_night_effect
        for invalidation in ("expire", "turn", "grant"):
            def invalidate(effect, adapter, **payload):
                if invalidation == "expire":
                    with mock.patch.object(authority.time, "monotonic", return_value=effect.grant._created + 601):
                        return original(effect, adapter, **payload)
                if invalidation == "turn":
                    effect.grant._turn.authority.turn.requested_action = None
                else:
                    effect.grant.target_date = "2026-11-17"
                return original(effect, adapter, **payload)
            with self.subTest(invalidation=invalidation), mock.patch.object(authority, "execute_night_effect", side_effect=invalidate):
                result = self.route("I'm going to bed.")
                self.assertIn("requires a current, authorised request", result.answer)
                self.assertEqual(self.effects, [])
        print('SEC01_NIGHT_FINAL_DENIAL {"cases": 3, "attempted_writes": 0}')


if __name__ == "__main__":
    unittest.main(verbosity=2)
