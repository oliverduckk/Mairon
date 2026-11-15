"""SEC-01 real application/Core -> final Desktop Agent transport recording.

No server, SDK, model, device, private store or OS action is used. Text and
already-transcribed voice share the same application ingress under test.
"""
import json
import sys
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
import s1_offline_bootstrap  # noqa: F401
dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda *args, **kwargs: False
sys.modules["dotenv"] = dotenv

import application_service as service
from core import desktop_agent_client
from core.orchestrator import MaironCore


class InertConversation:
    def get_response(self, client, user_input, instructions, conversation=None, **kwargs):
        return "Offline conversational response.", list(conversation or []), None, None


class ApplicationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.attempts = []
        self.inventory_reads = []
        def record(action, args=None, **kwargs):
            if action == "list_installed_steam_games":
                self.inventory_reads.append(dict(args or {}))
                return {"success": True, "games": []}
            self.attempts.append({"action": action, "args": dict(args or {})})
            return {"success": True, "status": "offline_recorded", "close_behavior": "quit_process"}
        self.stack.enter_context(mock.patch.object(desktop_agent_client, "call_desktop_agent", side_effect=record))
        for name in ("capture_user_preference", "build_user_preference_recall_response", "record_conversation_turn", "record_chat_turn"):
            self.stack.enter_context(mock.patch.object(service, name, return_value=None))

    def app(self):
        app = service.MaironApplication(user_name="OfflineUser", core=MaironCore(),
            local_ai={"client": object(), "module": InertConversation()},
            cloud_ai=None, create_providers=False)
        app._schedule_semantic_title_if_first_turn = lambda **kwargs: None
        return app

    def test_nonactions_have_zero_final_transport_attempts(self):
        cases = (
            "Do not close Discord.", "What happens if I close Chrome?",
            'Translate "close Discord" into French.', 'I said "close Discord" yesterday.',
            "If I close Chrome, will my tabs come back?",
            "Don't close Chrome; explain why it is slow.", "Please don't open Notepad.",
            'An email says "focus Chrome".', 'My friend told me to close Discord.',
            "Close Discord and open Notepad.", "Close Discord or Chrome.",
            "Open it.", "Focus that.", "Close it.",
        )
        for channel in ("text", "voice"):
            for text in cases:
                with self.subTest(channel=channel, text=text):
                    self.app().submit_text(text, channel=channel)
                    self.assertEqual(self.attempts, [])
        print("SEC01_APP_FINAL_DENIED " + json.dumps({"cases": len(cases) * 2, "mutating_attempts": len(self.attempts), "inert_inventory_reads": len(self.inventory_reads)}))

    def test_positive_actions_reach_exact_final_transport_once(self):
        cases = (
            ("Close Discord.", "close_application", "discord"),
            ("Please close Discord.", "close_application", "discord"),
            ("Could you close Discord?", "close_application", "discord"),
            ("Open Notepad.", "launch_application", "notepad"),
            ("Focus Chrome.", "focus_application", "chrome"),
        )
        count = 0
        for channel in ("text", "voice"):
            for text, action, target in cases:
                with self.subTest(channel=channel, text=text):
                    self.attempts.clear()
                    result = self.app().submit_text(text, channel=channel)
                    self.assertEqual(result.status, "answered")
                    self.assertEqual(self.attempts, [{"action": action, "args": {"app_name": target}}])
                    count += 1
        print("SEC01_APP_FINAL_POSITIVE " + json.dumps({"cases": count, "one_exact_effect_each": count}))

    def test_trusted_deictic_and_restored_plain_target(self):
        app = self.app()
        app.submit_text("Open Notepad.")
        self.attempts.clear()
        app.submit_text("Focus it.", channel="voice")
        self.assertEqual(self.attempts, [{"action": "focus_application", "args": {"app_name": "notepad"}}])
        self.attempts.clear()
        fresh = self.app()
        fresh.core.conversation_state.active_desktop_target = "notepad"
        fresh.submit_text("Close it.")
        self.assertEqual(self.attempts, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
