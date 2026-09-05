import sys
from pathlib import Path
from urllib.parse import (
    parse_qs,
    urlparse,
)


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SRC_DIR),
    )


from core.web_catalog import (
    build_trusted_site_url,
    extract_browser_action_request,
)
from core.intent_router import (
    classify_turn,
)
import core.workflows.browser_search as browser_workflow
from core.orchestrator import (
    MaironCore,
)


def run():
    # --------------------------------------------------
    # 1. Trusted fixed site opens.
    # --------------------------------------------------

    open_cases = (
        (
            "open youtube",
            "youtube",
        ),
        (
            "go to reddit",
            "reddit",
        ),
        (
            "open github",
            "github",
        ),
        (
            "open gmail",
            "gmail",
        ),
    )

    for message, site_id in open_cases:
        turn = classify_turn(
            message
        )

        assert (
            turn.intent
            == "browser_open"
        ), (
            message,
            turn.to_dict(),
        )

        assert (
            turn.entities[
                "browser_site"
            ]
            == site_id
        )

        assert (
            turn.entities[
                "browser"
            ]
            == "chrome"
        )

    # --------------------------------------------------
    # 2. Site-specific search and compound browser workflow.
    # --------------------------------------------------

    search_cases = (
        (
            "search youtube for Tame Impala",
            "youtube",
            "Tame Impala",
        ),
        (
            "open youtube and search for Tame Impala",
            "youtube",
            "Tame Impala",
        ),
        (
            "search reddit for minecraft redstone",
            "reddit",
            "minecraft redstone",
        ),
        (
            "look up Mairon on github",
            "github",
            "Mairon",
        ),
        (
            "open chrome and search for xt50 lenses",
            "google",
            "xt50 lenses",
        ),
        (
            "google Fujifilm XT50 lenses",
            "google",
            "Fujifilm XT50 lenses",
        ),
    )

    for message, site_id, query in search_cases:
        turn = classify_turn(
            message
        )

        assert (
            turn.intent
            == "browser_search"
        ), (
            message,
            turn.to_dict(),
        )

        assert (
            turn.entities[
                "browser_site"
            ]
            == site_id
        )

        assert (
            turn.entities[
                "search_query"
            ]
            == query
        )

    # Gmail is trusted for navigation but not browser search automation.
    assert (
        extract_browser_action_request(
            "search gmail for PayPal"
        )
        is None
    )

    # --------------------------------------------------
    # 3. URL construction keeps query inert.
    # --------------------------------------------------

    malicious_query = (
        'cats & dogs https://evil.example/?x=1'
    )

    youtube_url = build_trusted_site_url(
        "youtube",
        malicious_query,
    )

    parsed = urlparse(
        youtube_url
    )

    assert parsed.scheme == "https"
    assert parsed.netloc == "www.youtube.com"
    assert parsed.path == "/results"

    params = parse_qs(
        parsed.query
    )

    assert params[
        "search_query"
    ] == [
        malicious_query
    ]

    github_url = build_trusted_site_url(
        "github",
        "Mairon repo",
    )

    github_parsed = urlparse(
        github_url
    )

    assert github_parsed.netloc == "github.com"
    assert (
        parse_qs(
            github_parsed.query
        )[
            "q"
        ]
        == [
            "Mairon repo"
        ]
    )

    assert (
        build_trusted_site_url(
            "definitely-not-trusted",
            "test",
        )
        is None
    )

    # --------------------------------------------------
    # 4. Active trusted-site follow-up.
    # --------------------------------------------------

    core = MaironCore()

    original_open_via_agent = (
        browser_workflow.open_trusted_browser_site_via_agent
    )

    calls = []

    try:
        def fake_open_via_agent(
            site_id,
            query=None,
        ):
            calls.append(
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
                "url": build_trusted_site_url(
                    site_id,
                    query,
                ),
            }

        browser_workflow.open_trusted_browser_site_via_agent = (
            fake_open_via_agent
        )

        first = core.prepare_turn(
            "open youtube"
        )

        assert first.direct_response == (
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

        follow = core.prepare_turn(
            "search for Tame Impala"
        )

        assert (
            follow.turn.intent
            == "browser_search"
        )

        assert (
            follow.turn.is_follow_up
            is True
        )

        assert (
            follow.turn.entities[
                "browser_site"
            ]
            == "youtube"
        )

        assert follow.direct_response == (
            'Searching YouTube for "Tame Impala".'
        )

        assert calls == [
            (
                "youtube",
                None,
            ),
            (
                "youtube",
                "Tame Impala",
            ),
        ]

    finally:
        browser_workflow.open_trusted_browser_site_via_agent = (
            original_open_via_agent
        )

    # --------------------------------------------------
    # 5. Bare search with no browser context is NOT hijacked.
    # --------------------------------------------------

    fresh = MaironCore()

    bare = fresh.prepare_turn(
        "search for Tame Impala"
    )

    assert (
        bare.turn.intent
        != "browser_search"
    )

    # --------------------------------------------------
    # 6. Browser context never degrades into generic Chrome close.
    # --------------------------------------------------

    close_candidate = classify_turn(
        "close it",
        conversation_state=(
            core.conversation_state
        ),
    )

    assert (
        close_candidate.intent
        == "browser_context_close_unsupported"
    )

    assert (
        close_candidate.entities[
            "browser_site"
        ]
        == "youtube"
    )

    # Chrome remains the underlying desktop referent for explicit focus/close
    # commands, but deictic browser-close semantics are handled first.
    assert (
        core.conversation_state
        .active_desktop_target
        == "chrome"
    )

    print(
        "Mairon Phase 8.4 trusted browser navigation/search tests: PASS"
    )


if __name__ == "__main__":
    run()
