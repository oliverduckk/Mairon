"""Late lexical repair must preserve Core's established missing-input task."""

import ast
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from core.epistemic_calibration import repair_unjustified_lexical_denial
from core.epistemic_router import classify_factual_authority


def _production_late_repair(user_input, draft_text, core_epistemic_mode):
    # Execute the real provider call expression with the real Core route and
    # calibration function, without importing its tools or contacting a model.
    provider = SRC / "ai" / "ollama_provider.py"
    tree = ast.parse(provider.read_text(encoding="utf-8"))
    direct = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "handle_direct_conversation")
    calls = [node for node in ast.walk(direct)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == "repair_unjustified_lexical_denial"]
    if len(calls) != 1:
        raise AssertionError("expected exactly one late lexical repair call")
    return eval(compile(ast.Expression(calls[0]), str(provider), "eval"), {
        "repair_unjustified_lexical_denial": repair_unjustified_lexical_denial,
        "user_input": user_input,
        "draft_text": draft_text,
        "core_epistemic_mode": core_epistemic_mode,
    })


class MissingAttachmentCalibrationTests(unittest.TestCase):
    def test_missing_screenshot_task_survives_production_late_repair(self):
        prompts = (
            "can u tell me what's wrong in the screenshot i just sent? "
            "...okay i genuinely forgot to attach it",
            "What's a discrepancy in the document? I haven't uploaded it yet.",
            "What's an error in the image? I forgot to attach it.",
        )
        draft = "The attachment doesn't exist in this chat yet; attach it before I can inspect it."
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                mode = classify_factual_authority(prompt)
                self.assertEqual(mode, "insufficient_user_context")
                repaired, changed = _production_late_repair(prompt, draft, mode)
                self.assertFalse(changed)
                self.assertEqual(repaired, draft)

    def test_real_lexical_queries_still_receive_calibrated_uncertainty(self):
        for prompt in (
            "What does quorblax mean?",
            "quick one: what's a dravonetic handshake in computer networking?",
        ):
            with self.subTest(prompt=prompt):
                mode = classify_factual_authority(prompt)
                repaired, changed = _production_late_repair(
                    prompt, "There is no such thing as that term.", mode
                )
                self.assertTrue(changed)
                self.assertIn("not familiar enough", repaired)

    def test_legacy_two_argument_lexical_repair_remains_compatible(self):
        repaired, changed = repair_unjustified_lexical_denial(
            "Define quorblax.", "Quorblax doesn't exist."
        )
        self.assertTrue(changed)
        self.assertIn("quorblax", repaired)


if __name__ == "__main__":
    unittest.main()
