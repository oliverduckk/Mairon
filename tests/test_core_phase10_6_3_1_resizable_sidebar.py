import ast
import json
from pathlib import Path
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"


def _load_pure_sidebar_helpers(source: str, filename: str):
    tree = ast.parse(source, filename=filename)
    wanted = {
        "_clamp_sidebar_width",
        "_load_sidebar_width",
        "_save_sidebar_width",
    }

    helper_nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in wanted
    ]

    namespace = {
        "json": json,
        "Path": Path,
        "DESKTOP_UI_STATE_PATH": Path("unused.json"),
        "DEFAULT_SIDEBAR_WIDTH": 220,
        "MIN_SIDEBAR_WIDTH": 165,
        "MAX_SIDEBAR_WIDTH": 320,
    }

    helper_module = ast.Module(
        body=helper_nodes,
        type_ignores=[],
    )

    exec(
        compile(
            helper_module,
            filename,
            "exec",
        ),
        namespace,
    )

    return namespace


def run():
    app_path = SRC_DIR / "desktop_app.py"
    source = app_path.read_text(encoding="utf-8")
    ast.parse(source, filename=str(app_path))

    # --------------------------------------------------
    # 1. Sidebar width remains a persisted local preference.
    # --------------------------------------------------

    assert "DESKTOP_UI_STATE_PATH" in source
    assert '"desktop_ui_state.json"' in source
    assert "DEFAULT_SIDEBAR_WIDTH = 220" in source
    assert "MIN_SIDEBAR_WIDTH = 165" in source
    assert "MAX_SIDEBAR_WIDTH = 320" in source
    assert "SIDEBAR_SPLITTER_WIDTH = 10" in source

    helpers = _load_pure_sidebar_helpers(
        source,
        str(app_path),
    )

    clamp = helpers["_clamp_sidebar_width"]
    load = helpers["_load_sidebar_width"]
    save = helpers["_save_sidebar_width"]

    assert clamp(80) == 165
    assert clamp(245) == 245
    assert clamp(900) == 320
    assert clamp("bad") == 220

    with tempfile.TemporaryDirectory() as temp_dir:
        state_path = Path(temp_dir) / "desktop_ui_state.json"
        assert load(state_path) == 220
        state_path.write_text("not-json", encoding="utf-8")
        assert load(state_path) == 220

        state_path.write_text(
            json.dumps({"other_setting": True}),
            encoding="utf-8",
        )
        save(278, state_path)
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        assert payload["sidebar_width"] == 278
        assert payload["other_setting"] is True
        assert load(state_path) == 278

        save(999, state_path)
        assert load(state_path) == 320

    # --------------------------------------------------
    # 2. Resizing is delegated to Tk's native PanedWindow sash.
    # --------------------------------------------------

    build_start = source.index("    def _build_body(")
    build_end = source.index("    def _build_sidebar(", build_start)
    build_source = source[build_start:build_end]

    assert "tk.PanedWindow(" in build_source
    assert "orient=tk.HORIZONTAL" in build_source
    assert "opaqueresize=False" in build_source
    assert 'sashcursor="sb_h_double_arrow"' in build_source
    assert "proxybackground=self.theme[" in build_source
    assert "self.sidebar_panes = panes" in build_source
    assert "panes.add(" in build_source
    assert "minsize=MIN_SIDEBAR_WIDTH" in build_source
    assert '"<ButtonRelease-1>"' in build_source
    assert '"<Double-Button-1>"' in build_source

    # The failed custom preview implementation must be gone: it caused
    # duplicate/trailing vertical lines and made the drag target unreliable.
    assert "sidebar_resize_preview" not in source
    assert "_show_sidebar_resize_preview" not in source
    assert "_on_sidebar_resize_drag" not in source
    assert "grab_set()" not in source

    assert "def _restore_sidebar_sash(" in source
    assert "def _on_sidebar_sash_release(" in source
    assert "def _on_sidebar_sash_double_click(" in source
    assert "sash_place(" in source
    assert "sash_coord(" in source

    # Sidebar/main builders can now hand their frames to PanedWindow without
    # also trying to grid those same widgets themselves.
    assert "manage_geometry: bool = True" in source
    assert "self.main_area = main" in source

    # --------------------------------------------------
    # 3. Width is restored at startup and saved on shutdown.
    # --------------------------------------------------

    init_start = source.index("class MaironDesktopApp:")
    init_end = source.index(
        "    # --------------------------------------------------\n    # UI construction",
        init_start,
    )
    init_source = source[init_start:init_end]
    assert "_load_sidebar_width()" in init_source

    close_start = source.index("    def _on_close(")
    close_end = source.index("    @staticmethod", close_start)
    close_source = source[close_start:close_end]
    assert "_save_sidebar_width(" in close_source

    # Previous history/selectable-message functionality remains present.
    assert "Search chats..." in source
    assert "group_chat_sessions(" in source
    assert "self.message_text = tk.Text(" in source
    assert '"displaylines"' in source

    print(
        "Mairon Phase 10.6.3.1 native resizable sidebar tests: PASS"
    )


if __name__ == "__main__":
    run()
