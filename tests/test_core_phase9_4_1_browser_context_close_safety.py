import sys
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(
    SRC_DIR
) not in sys.path:
    sys.path.insert(
        0,
        str(
            SRC_DIR
        ),
    )


import core.orchestrator as orchestrator_module
import core.workflows.browser_search as browser_workflow

from core.intent_router import (
    classify_turn,
)
from core.orchestrator import (
    MaironCore,
)
from core.web_catalog import (
    build_trusted_site_url,
)


def run():
    core = MaironCore()

    original_open_via_agent = (
        browser_workflow
        .open_trusted_browser_site_via_agent
    )

    original_control = (
        orchestrator_module
        .control_approved_application
    )

    browser_calls = []
    desktop_control_calls = []

    try:
        def fake_open_via_agent(
            site_id,
            query=None,
        ):
            browser_calls.append(
                (
                    site_id,
                    query,
                )
            )

            return {
                "success": True,
                "status": (
                    "search_opened"
                    if query is not None
                    else "site_opened"
                ),
                "site_id": site_id,
                "query": query,
                "browser": "chrome",
                "url": build_trusted_site_url(
                    site_id,
                    query,
                ),
            }

        def forbidden_desktop_control(
            *args,
            **kwargs,
        ):
            desktop_control_calls.append(
                (
                    args,
                    kwargs,
                )
            )

            raise AssertionError(
                "Deictic browser close reached generic desktop control."
            )

        browser_workflow.open_trusted_browser_site_via_agent = (
            fake_open_via_agent
        )

        orchestrator_module.control_approved_application = (
            forbidden_desktop_control
        )

        # --------------------------------------------------
        # 1. Establish one verified active browser context.
        # --------------------------------------------------

        opened = core.prepare_turn(
            "open youtube"
        )

        assert opened.direct_response == (
            "YouTube's open."
        )

        assert (
            core.conversation_state
            .active_browser_site
            == "youtube"
        )

        assert (
            core.conversation_state
            .active_desktop_target
            == "chrome"
        )

        # --------------------------------------------------
        # 2. "close it" resolves to browser-context safety, not Chrome close.
        # --------------------------------------------------

        candidate = classify_turn(
            "close it",
            conversation_state=(
                core.conversation_state
            ),
        )

        assert (
            candidate.intent
            == "browser_context_close_unsupported"
        )

        assert candidate.is_follow_up is True

        assert (
            candidate.entities[
                "browser_site"
            ]
            == "youtube"
        )

        closed = core.prepare_turn(
            "close it"
        )

        assert (
            closed.turn.intent
            == "browser_context_close_unsupported"
        )

        assert closed.workflow_result is None

        assert closed.direct_response == (
            "I can't safely close just that YouTube browser context yet "
            "without risking your other Chrome tabs, so I left Chrome alone."
        )

        assert desktop_control_calls == []

        # The refused action must not falsely erase the still-active browser
        # context. A subsequent bare search may continue on YouTube.
        assert (
            core.conversation_state
            .active_browser_site
            == "youtube"
        )

        # --------------------------------------------------
        # 3. Explicit trusted-site close gets the same safe treatment.
        # --------------------------------------------------

        explicit_site = core.prepare_turn(
            "close youtube"
        )

        assert (
            explicit_site.turn.intent
            == "browser_context_close_unsupported"
        )

        assert desktop_control_calls == []

        # --------------------------------------------------
        # 4. Explicit "close chrome" remains an intentional app-level action.
        # --------------------------------------------------

        explicit_chrome = classify_turn(
            "close chrome",
            conversation_state=(
                core.conversation_state
            ),
        )

        assert (
            explicit_chrome.intent
            == "close_application"
        )

        assert (
            explicit_chrome.entities[
                "app_name"
            ]
            == "chrome"
        )

        # --------------------------------------------------
        # 5. Browser navigation itself still crossed the browser lane only.
        # --------------------------------------------------

        assert browser_calls == [
            (
                "youtube",
                None,
            )
        ]

    finally:
        browser_workflow.open_trusted_browser_site_via_agent = (
            original_open_via_agent
        )

        orchestrator_module.control_approved_application = (
            original_control
        )

    print(
        "Mairon Phase 9.4.1 browser-context close safety tests: PASS"
    )


if __name__ == "__main__":
    run()
