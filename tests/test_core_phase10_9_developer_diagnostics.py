from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"


def _read(relative: str) -> str:
    return (SRC_ROOT / relative).read_text(encoding="utf-8")


def run() -> None:
    app_source = _read("application_service.py")
    desktop_source = _read("desktop_app.py")

    compile(app_source, "application_service.py", "exec")
    compile(desktop_source, "desktop_app.py", "exec")

    app_tree = ast.parse(app_source)
    desktop_tree = ast.parse(desktop_source)

    application_turn = next(
        node
        for node in app_tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "ApplicationTurn"
    )
    turn_fields = {
        stmt.target.id
        for stmt in application_turn.body
        if isinstance(stmt, ast.AnnAssign)
        and isinstance(stmt.target, ast.Name)
    }
    assert "diagnostics" in turn_fields

    app_class = next(
        node
        for node in app_tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "MaironApplication"
    )
    builder = next(
        node
        for node in app_class.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_build_turn_diagnostics"
    )
    arg_names = {
        arg.arg
        for arg in (
            list(builder.args.args)
            + list(builder.args.kwonlyargs)
        )
    }
    assert {
        "intent",
        "authority",
        "route_mode",
        "workflow",
        "model_used",
        "agent_action",
        "status",
        "channel",
        "response_seconds",
    }.issubset(arg_names)
    assert not {
        "user_text",
        "answer",
        "prompt",
        "evidence",
        "messages",
        "reasoning",
        "chain_of_thought",
    }.intersection(arg_names)

    pending = next(
        node
        for node in app_tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "_PendingApproval"
    )
    pending_fields = {
        stmt.target.id
        for stmt in pending.body
        if isinstance(stmt, ast.AnnAssign)
        and isinstance(stmt.target, ast.Name)
    }
    assert {
        "intent",
        "authority",
        "route_mode",
        "workflow",
        "agent_action",
    }.issubset(pending_fields)

    # Diagnostics must not require optional fields on lightweight Core decision
    # objects used by fallbacks/tests. Missing workflow_result means no workflow.
    submit_method = next(
        node
        for node in app_class.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "submit_text"
    )
    submit_text = ast.get_source_segment(
        app_source,
        submit_method,
    ) or ""
    assert 'getattr(\n                core_decision,\n                "workflow_result",\n                None,' in submit_text
    assert "core_decision.workflow_result" not in submit_text

    assert "self.diagnostics_visible = False" in desktop_source
    assert "panel.grid_remove()" in desktop_source
    assert 'text="⌁  Diagnostics"' in desktop_source
    assert "self._toggle_diagnostics" in desktop_source

    for label in (
        "Intent",
        "Authority",
        "Mode",
        "Workflow",
        "Model",
        "Agent action",
        "Status",
        "Channel",
        "Response",
        "Session",
        "RECENT EVENTS",
    ):
        assert f'"{label}"' in desktop_source

    assert "self._update_turn_diagnostics(" in desktop_source
    assert "result.diagnostics" in desktop_source

    desktop_class = next(
        node
        for node in desktop_tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "MaironDesktopApp"
    )
    record_method = next(
        node
        for node in desktop_class.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_record_diagnostic_event"
    )
    record_text = ast.get_source_segment(
        desktop_source,
        record_method,
    ) or ""
    for prefix in (
        "[Core]",
        "[Context]",
        "[Grounding]",
        "[Research]",
        "[AI]",
        "[Desktop Agent]",
        "[Tool]",
        "[Session]",
        "[Timing]",
    ):
        assert prefix in record_text
    assert "value.startswith" in record_text
    assert "value[:180]" in record_text

    lowered = desktop_source.lower()
    assert "no prompts" in lowered
    assert "hidden model reasoning" in lowered

    print("Mairon Phase 10.9 developer diagnostics tests: PASS")


if __name__ == "__main__":
    run()
