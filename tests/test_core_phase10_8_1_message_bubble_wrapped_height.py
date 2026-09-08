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

    sync_start = bubble_source.index(
        "    def _sync_text_height("
    )

    sync_end = bubble_source.index(
        "    def _sync_height(",
        sync_start,
    )

    sync_source = bubble_source[
        sync_start:sync_end
    ]

    # Tk Text.count(..., "displaylines") counts visual-line transitions
    # between indices.  The occupied line count therefore has to include the
    # starting display line as well; otherwise every wrapped bubble is one
    # line too short and the final visual line can be clipped.
    assert '"displaylines"' in sync_source
    assert "+ 1" in sync_source

    # Height still follows the measured wrapped display-line count rather than
    # falling back to a hard-coded number of rows.
    assert "height=display_lines" in sync_source

    # Phase 10.8's read-only/selectable message body must remain intact.
    assert "self.message_text = tk.Text(" in bubble_source
    assert 'state="disabled"' in bubble_source
    assert '"<Control-c>"' in bubble_source
    assert '"<Button-3>"' in bubble_source

    print(
        "Mairon Phase 10.8.1 wrapped message bubble height tests: PASS"
    )


if __name__ == "__main__":
    run()
