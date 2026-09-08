import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"


def run():
    app_path = SRC_DIR / "desktop_app.py"

    source = app_path.read_text(
        encoding="utf-8",
    )

    ast.parse(
        source,
        filename=str(app_path),
    )

    bubble_start = source.index(
        "class RoundedMessageBubble("
    )

    bubble_end = source.index(
        "class ThemedScrollbar(",
        bubble_start,
    )

    bubble_source = source[
        bubble_start:bubble_end
    ]

    # --------------------------------------------------
    # 1. Message bodies remain read-only selectable Text widgets.
    # --------------------------------------------------

    assert "self.message_text = tk.Text(" in bubble_source
    assert 'state="disabled"' in bubble_source
    assert 'cursor="xterm"' in bubble_source

    # No regression back to the old non-selectable body Label.
    assert "self.message_label = tk.Label(" not in bubble_source

    # --------------------------------------------------
    # 2. Keyboard copy is message-local.
    # --------------------------------------------------

    assert '"<Control-c>"' in bubble_source
    assert '"<Control-C>"' in bubble_source
    assert "def _copy_message_selection(" in bubble_source
    assert "self.clipboard_clear()" in bubble_source
    assert "self.clipboard_append(" in bubble_source

    # --------------------------------------------------
    # 3. Ctrl+A selects only the focused message body.
    # --------------------------------------------------

    assert '"<Control-a>"' in bubble_source
    assert '"<Control-A>"' in bubble_source
    assert "def _select_all_message_text(" in bubble_source
    assert '"sel",' in bubble_source
    assert '"1.0",' in bubble_source
    assert '"end-1c",' in bubble_source

    # --------------------------------------------------
    # 4. Windows right-click exposes Copy without enabling editing.
    # --------------------------------------------------

    assert '"<Button-3>"' in bubble_source
    assert "self._message_context_menu = tk.Menu(" in bubble_source
    assert 'label="Copy"' in bubble_source
    assert 'label="Select All"' in bubble_source
    assert "def _show_message_context_menu(" in bubble_source
    assert ".tk_popup(" in bubble_source

    # Copy must be disabled when there is no active selection instead of
    # silently copying some unrelated/global text.
    assert 'state=(' in bubble_source
    assert 'else "disabled"' in bubble_source

    # The implementation must never temporarily flip the chat message into
    # editable mode for selection/copy operations.
    interaction_start = bubble_source.index(
        "    def _message_selection_text("
    )
    interaction_source = bubble_source[
        interaction_start:
    ]
    assert 'state="normal"' not in interaction_source
    assert "state='normal'" not in interaction_source

    print(
        "Mairon Phase 10.8 selectable/copyable chat message tests: PASS"
    )


if __name__ == "__main__":
    run()
