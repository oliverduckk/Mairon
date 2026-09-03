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


from core.intent_router import (
    classify_turn,
)
from core.workflow_result import (
    WorkflowResult,
)
import core.orchestrator as orchestrator_module
from core.orchestrator import (
    MaironCore,
)
from tools import desktop_tools


def run():
    # --------------------------------------------------
    # 1. Compound Chrome search is a first-class deterministic intent.
    # --------------------------------------------------

    turn = classify_turn(
        "Open Chrome and search for RTX 5080 benchmarks"
    )

    assert turn.intent == (
        "browser_search"
    )

    assert turn.entities[
        "browser"
    ] == "chrome"

    assert turn.entities[
        "search_query"
    ] == (
        "RTX 5080 benchmarks"
    )

    # Existing short form.
    google_turn = classify_turn(
        "Google best ramen in Sydney"
    )

    assert google_turn.intent == (
        "browser_search"
    )

    assert google_turn.entities[
        "search_query"
    ] == (
        "best ramen in Sydney"
    )

    # --------------------------------------------------
    # 2. Query becomes URL data, never shell text.
    # --------------------------------------------------

    original_find_chrome = (
        desktop_tools._find_chrome
    )

    original_launch_process = (
        desktop_tools._launch_process
    )

    original_os_name = (
        desktop_tools.os.name
    )

    commands = []

    try:
        desktop_tools.os.name = "nt"

        desktop_tools._find_chrome = (
            lambda: r"C:\Chrome\chrome.exe"
        )

        def fake_launch_process(
            command,
        ):
            commands.append(
                list(
                    command
                )
            )

            return {
                "success": True,
            }

        desktop_tools._launch_process = (
            fake_launch_process
        )

        result = (
            desktop_tools
            .open_chrome_search(
                'cats & dogs "test"'
            )
        )

        assert result[
            "success"
        ] is True

        assert len(
            commands
        ) == 1

        assert commands[
            0
        ][
            0
        ] == r"C:\Chrome\chrome.exe"

        url = commands[
            0
        ][
            1
        ]

        assert url.startswith(
            "https://www.google.com/search?"
        )

        assert (
            "q=cats+%26+dogs+%22test%22"
            in url
        )

    finally:
        desktop_tools._find_chrome = (
            original_find_chrome
        )

        desktop_tools._launch_process = (
            original_launch_process
        )

        desktop_tools.os.name = (
            original_os_name
        )

    # --------------------------------------------------
    # 3. Full Core path is model-free and makes Chrome the active referent.
    # --------------------------------------------------

    original_workflow = (
        orchestrator_module.open_browser_search
    )

    try:
        def fake_workflow(
            query,
        ):
            return WorkflowResult(
                success=True,
                status="browser_search_opened",
                answer_fact=(
                    f'Searching Chrome for "{query}".'
                ),
                data={
                    "query": query,
                },
            )

        orchestrator_module.open_browser_search = (
            fake_workflow
        )

        core = MaironCore()

        decision = core.prepare_turn(
            "Open Chrome and search for Mairon project"
        )

        assert decision.direct_response == (
            'Searching Chrome for "Mairon project".'
        )

        assert (
            core.conversation_state
            .active_desktop_target
            == "chrome"
        )

    finally:
        orchestrator_module.open_browser_search = (
            original_workflow
        )

    print(
        "Mairon Phase 8.3 deterministic browser search tests: PASS"
    )


if __name__ == "__main__":
    run()
