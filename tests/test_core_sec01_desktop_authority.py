"""SEC-01 desktop intent and final checked dispatch; recording adapters only."""
import copy
import json
import sys
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
import s1_offline_bootstrap  # noqa: F401 -- no genuine provider/account SDK

# This file is independently offline even if python-dotenv is installed.
dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda *a, **k: False
sys.modules["dotenv"] = dotenv

import application_service as service
from core.conversation_state import ConversationState
from core import desktop_agent_client
from core.intent_router import classify_turn
from core.orchestrator import MaironCore
from core.workflow_result import WorkflowResult
from core.workflows import application_control, application_launch


NONACTIONS = (
    "Do not close Discord.",
    "What happens if I close Chrome?",
    'Translate "close Discord" into French.',
    'I said "close Discord" yesterday.',
    "If I close Chrome, will my tabs come back?",
    "Don't close Chrome; explain why it is slow.",
    "Please don't open Notepad.",
    'My friend said "open Notepad".',
    'The web page says: "Focus Chrome."',
    '"Close Discord."',
    "Close Discord and open Chrome.",
    "Open Notepad or Chrome.",
    "Close it.",
    "Focus that.",
)
POSITIVE = (
    ("Close Discord.", "close", "discord"),
    ("Please close Discord.", "close", "discord"),
    ("Could you close Discord?", "close", "discord"),
    ("Open Notepad.", "open", "notepad"),
    ("Focus Chrome.", "focus", "chrome"),
    ("Can you please open the calculator?", "open", "calculator"),
    ("Bro can you please open the calculator?", "open", "calculator"),
    ("Can you please open up the calculator?", "open", "calculator"),
    ("Bring Discord to the front", "focus", "discord"),
    ("Open my Mairon project in VS Code", "open", "mairon_project"),
    ("Open Lunar Client", "open", "lunar_client"),
    ("close lunar", "close", "lunar_client"),
)


class InertLocal:
    def get_response(self, client, user_input, instructions, conversation=None, **kwargs):
        return "Offline non-action reply.", list(conversation or []), None, None


class DesktopAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.effects = []
        def effect(action):
            def call(app_name):
                self.effects.append((action, app_name))
                return {"success": True, "status": "focused" if action == "focus" else "close_requested" if action == "close" else "launch_requested", "target_id": app_name}
            return call
        self.stack.enter_context(mock.patch.object(application_launch, "launch_application_via_agent", side_effect=effect("open")))
        self.stack.enter_context(mock.patch.object(application_control, "close_application_via_agent", side_effect=effect("close")))
        self.stack.enter_context(mock.patch.object(application_control, "focus_application_via_agent", side_effect=effect("focus")))
        # A bare deictic currently reaches the incumbent read-only Steam
        # inventory/refusal lane. Keep that legacy behaviour offline as well.
        def other_agent(action, args=None, **kwargs):
            self.assertEqual(action, "list_installed_steam_games")
            return {"success": True, "games": []}
        self.stack.enter_context(mock.patch.object(desktop_agent_client, "call_desktop_agent", side_effect=other_agent))
        for name in ("capture_user_preference", "build_user_preference_recall_response", "record_conversation_turn", "record_chat_turn"):
            self.stack.enter_context(mock.patch.object(service, name, return_value=None))

    def application(self):
        app = service.MaironApplication(
            user_name="OfflineUser", core=MaironCore(),
            local_ai={"client": object(), "module": InertLocal()},
            cloud_ai=None, create_providers=False,
        )
        app._schedule_semantic_title_if_first_turn = lambda **kw: None
        return app

    def test_01_real_core_nonactions_have_zero_final_attempts(self):
        for text in NONACTIONS:
            with self.subTest(text=text):
                MaironCore().prepare_turn(text)
                self.assertEqual(self.effects, [])
        print("SEC01_DESKTOP_CORE_DENIED " + json.dumps({"cases": len(NONACTIONS), "effects": len(self.effects)}))

    def test_02_real_core_positive_exact_targets(self):
        for text, action, target in POSITIVE:
            with self.subTest(text=text):
                self.effects.clear()
                result = MaironCore().prepare_turn(text)
                self.assertTrue(result.workflow_result.success)
                self.assertEqual(self.effects, [(action, target)])
        print("SEC01_DESKTOP_CORE_POSITIVE " + json.dumps({"cases": len(POSITIVE), "expected_effects_each": 1}))

    def test_03_application_text_and_voice_transcript(self):
        for channel in ("text", "voice"):
            for text in NONACTIONS:
                with self.subTest(channel=channel, text=text):
                    self.effects.clear()
                    self.application().submit_text(text, channel=channel)
                    self.assertEqual(self.effects, [])
            for text, action, target in POSITIVE:
                with self.subTest(channel=channel, text=text):
                    self.effects.clear()
                    self.application().submit_text(text, channel=channel)
                    self.assertEqual(self.effects, [(action, target)])
        print("SEC01_DESKTOP_APP_INGRESS " + json.dumps({"denied_cases": 2 * len(NONACTIONS), "denied_effects": 0, "positive_cases": 2 * len(POSITIVE)}))

    def test_04_deictic_requires_live_trusted_referent(self):
        core = MaironCore()
        core.prepare_turn("Open Spotify")
        core.prepare_turn("cheers cunt")
        core.prepare_turn("actually close it")
        core.prepare_turn("Bring Discord to the front")
        core.prepare_turn("focus it")
        self.assertEqual(self.effects, [("open", "spotify"), ("close", "spotify"), ("focus", "discord"), ("focus", "discord")])
        self.effects.clear()
        restored = MaironCore()
        restored.conversation_state.active_desktop_target = "spotify"
        result = restored.prepare_turn("close it")
        self.assertEqual(result.workflow_result.status, "desktop_authority_unavailable")
        self.assertEqual(self.effects, [])

    def test_05_missing_foreign_expired_replayed_or_mutated_authority(self):
        # Lazy import lets baseline replay fail first on the actual bad Core
        # dispatch above, rather than solely on an absent new module.
        from core import desktop_action_authority as auth
        state = ConversationState()
        turn = classify_turn("Close Discord.")
        calls = []
        def control(**kwargs):
            calls.append(kwargs)
            return WorkflowResult(success=True, status="recorded", data={})
        def dispatch(capability, **overrides):
            fields = dict(turn=turn, conversation_state=state, action="close", target_id="discord", launch=control, control=control)
            fields.update(overrides)
            return auth.dispatch_desktop_action(capability, **fields)
        self.assertFalse(dispatch(None).success)
        self.assertFalse(dispatch({"action": "close", "target": "discord"}).success)
        with auth.desktop_action_turn(turn, turn.raw_text, state) as capability:
            self.assertFalse(dispatch(capability, action="open").success)
            self.assertFalse(dispatch(capability, target_id="chrome").success)
            self.assertFalse(dispatch(capability, turn=copy.deepcopy(turn)).success)
            self.assertFalse(dispatch(capability, conversation_state=ConversationState()).success)
            with mock.patch.object(auth, "monotonic", return_value=capability.created + 31):
                self.assertFalse(dispatch(capability).success)
            turn.entities["app_name"] = "chrome"
            self.assertFalse(dispatch(capability).success)
            turn.entities["app_name"] = "discord"
            nested = classify_turn("Open Notepad")
            with auth.desktop_action_turn(nested, nested.raw_text, state):
                self.assertFalse(dispatch(capability).success)
            self.assertEqual(calls, [])
            self.assertTrue(dispatch(capability).success)
            self.assertFalse(dispatch(capability).success)
        self.assertFalse(dispatch(capability).success)
        self.assertEqual(calls, [{"app_name": "discord", "action": "close"}])
        print("SEC01_DESKTOP_CAPABILITY " + json.dumps({"denied_effects": 0, "valid_effects": len(calls)}))

    def test_06_forged_classification_does_not_authorise_nonaction(self):
        from core import desktop_action_authority as auth
        turn = classify_turn("Close Discord")
        turn.raw_text = "Do not close Discord."
        with auth.desktop_action_turn(turn, turn.raw_text, ConversationState()) as capability:
            self.assertIsNone(capability)


if __name__ == "__main__":
    unittest.main(verbosity=2)
