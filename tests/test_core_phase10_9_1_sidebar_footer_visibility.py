from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"


def run() -> None:
    source = (SRC_ROOT / "desktop_app.py").read_text(encoding="utf-8")
    compile(source, "desktop_app.py", "exec")
    tree = ast.parse(source)

    desktop = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "MaironDesktopApp"
    )
    build_sidebar = next(
        node
        for node in desktop.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_build_sidebar"
    )
    method = ast.get_source_segment(source, build_sidebar) or ""

    # The permanent system controls must live in a dedicated bottom footer so
    # reducing window height shrinks the scrollable history rather than hiding
    # Themes/Diagnostics below the visible edge.
    assert "sidebar_footer = tk.Frame(" in method
    assert "self.sidebar_footer = sidebar_footer" in method
    assert 'side="bottom"' in method
    assert 'fill="x"' in method

    # The history area remains the flexible middle region.
    history_anchor = method.index("history_viewport = tk.Frame(")
    footer_anchor = method.index("sidebar_footer = tk.Frame(")
    assert footer_anchor < history_anchor
    history_pack = method[history_anchor: method.index("self.recent_chats_canvas =", history_anchor)]
    assert 'fill="both"' in history_pack
    assert "expand=True" in history_pack

    # Footer-owned controls stay reachable independent of history length.
    assert 'self._sidebar_item(\n            sidebar_footer,\n            "▣  Files"' in method
    assert 'tk.Label(\n            sidebar_footer,\n            text="SYSTEM"' in method
    assert 'self.agent_label = tk.Label(\n            sidebar_footer,' in method
    assert 'self.model_label = tk.Label(\n            sidebar_footer,' in method
    assert 'self._build_diagnostics_toggle(\n            sidebar_footer\n        )' in method
    assert 'self._sidebar_item(\n            sidebar_footer,\n            "⚙  Themes"' in method
    assert 'tk.Label(\n            sidebar_footer,\n            text="v0.1 • Phase 10"' in method

    print("Mairon Phase 10.9.1 responsive sidebar footer tests: PASS")


if __name__ == "__main__":
    run()
