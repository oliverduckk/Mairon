import ast
import sys
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SRC_DIR),
    )


def run():
    app_path = (
        SRC_DIR
        / "desktop_app.py"
    )

    source = app_path.read_text(
        encoding="utf-8",
    )

    ast.parse(
        source,
        filename=str(
            app_path
        ),
    )

    # --------------------------------------------------
    # 1. Message bodies are selectable/copyable Text widgets.
    # --------------------------------------------------

    bubble_start = source.index(
        "class RoundedMessageBubble("
    )

    bubble_end = source.index(
        "class ThemedScrollbar(",
        bubble_start,
    )

    bubble_source = source[
        bubble_start:
        bubble_end
    ]

    assert (
        "self.message_text = tk.Text("
        in bubble_source
    )

    assert (
        'state="disabled"'
        in bubble_source
    )

    assert (
        'cursor="xterm"'
        in bubble_source
    )

    assert (
        '"<Control-c>"'
        in bubble_source
    )

    assert (
        "def _copy_message_selection("
        in bubble_source
    )

    assert (
        "def _sync_text_height("
        in bubble_source
    )

    # The old non-selectable body Label must be gone.
    assert (
        "self.message_label = tk.Label("
        not in bubble_source
    )

    # --------------------------------------------------
    # 2. Semantic title completion refreshes UI event-driven.
    # --------------------------------------------------

    debug_start = source.index(
        '        elif kind == "debug":'
    )

    result_start = source.index(
        "    # --------------------------------------------------\n"
        "    # Result rendering",
        debug_start,
    )

    debug_source = source[
        debug_start:
        result_start
    ]

    assert (
        "[Session] Semantic title:"
        in debug_source
    )

    assert (
        "self._refresh_current_chat_title()"
        in debug_source
    )

    assert (
        "self._refresh_recent_chats()"
        in debug_source
    )

    # VS/PowerShell development runs should expose service diagnostics.
    assert (
        "print("
        in debug_source
    )

    print(
        "Mairon Phase 10.6.2.3 title-event/selectable-text tests: PASS"
    )


if __name__ == "__main__":
    run()
