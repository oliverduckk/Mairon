import sys
import threading
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


import core.desktop_agent_client as agent_client
import core.workflows.browser_search as browser_workflow

from core.desktop_agent_protocol import (
    build_request,
    validate_request,
)
from core.web_catalog import (
    build_trusted_site_url,
)
from desktop_agent import (
    create_desktop_agent_server,
)


def run():
    # --------------------------------------------------
    # 1. Protocol accepts only structured trusted-browser args.
    # --------------------------------------------------

    request = validate_request(
        build_request(
            request_id="phase9-4-youtube",
            action="open_trusted_browser_site",
            args={
                "site_id": "youtube",
                "query": "Tame Impala",
            },
        )
    )

    assert request[
        "action"
    ] == "open_trusted_browser_site"

    assert request[
        "args"
    ] == {
        "site_id": "youtube",
        "query": "Tame Impala",
    }

    # Arbitrary URL injection is not part of the protocol.
    try:
        validate_request({
            "version": "1",
            "request_id": "phase9-4-bad-url",
            "action": "open_trusted_browser_site",
            "args": {
                "site_id": "youtube",
                "query": "Tame Impala",
                "url": "https://evil.example/",
            },
        })

    except ValueError:
        pass

    else:
        raise AssertionError(
            "Desktop Agent browser protocol accepted an arbitrary URL."
        )

    # --------------------------------------------------
    # 2. Real workflow crosses authenticated agent boundary.
    # --------------------------------------------------

    calls = []

    def fake_executor(
        action,
        args,
    ):
        calls.append(
            (
                action,
                dict(
                    args
                ),
            )
        )

        assert action == (
            "open_trusted_browser_site"
        )

        url = build_trusted_site_url(
            args[
                "site_id"
            ],
            args.get(
                "query"
            ),
        )

        return {
            "success": True,
            "status": (
                "search_opened"
                if args.get(
                    "query"
                ) is not None
                else "site_opened"
            ),
            "site_id": args[
                "site_id"
            ],
            "query": args.get(
                "query"
            ),
            "browser": "chrome",
            "url": url,
        }

    secret = (
        "phase9-4-test-secret-"
        "abcdefghijklmnopqrstuvwxyz012345"
    )

    server = create_desktop_agent_server(
        host="127.0.0.1",
        port=0,
        secret=secret,
        action_executor=fake_executor,
    )

    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={
            "poll_interval": 0.05,
        },
        daemon=True,
    )

    thread.start()

    original_url = (
        agent_client.get_desktop_agent_url
    )

    original_secret = (
        agent_client.load_or_create_agent_secret
    )

    try:
        host, port = (
            server.server_address
        )

        agent_client.get_desktop_agent_url = (
            lambda: f"http://{host}:{port}"
        )

        agent_client.load_or_create_agent_secret = (
            lambda: secret
        )

        result = (
            browser_workflow.open_browser_action(
                site_id="youtube",
                query="Tame Impala",
            )
        )

        assert result.success is True

        assert result.status == (
            "browser_search_opened"
        )

        assert result.answer_fact == (
            'Searching YouTube for "Tame Impala".'
        )

        assert calls == [
            (
                "open_trusted_browser_site",
                {
                    "site_id": "youtube",
                    "query": "Tame Impala",
                },
            )
        ]

        assert (
            result.evidence.evidence[
                0
            ].provenance
            == "desktop_agent"
        )

    finally:
        agent_client.get_desktop_agent_url = (
            original_url
        )

        agent_client.load_or_create_agent_secret = (
            original_secret
        )

        server.shutdown()
        server.server_close()

        thread.join(
            timeout=2.0
        )

    # --------------------------------------------------
    # 3. Core rejects a mismatched destination returned by Agent.
    # --------------------------------------------------

    original_open_via_agent = (
        browser_workflow
        .open_trusted_browser_site_via_agent
    )

    try:
        browser_workflow.open_trusted_browser_site_via_agent = (
            lambda site_id, query=None: {
                "success": True,
                "status": "search_opened",
                "site_id": site_id,
                "query": query,
                "browser": "chrome",
                "url": "https://evil.example/",
            }
        )

        mismatch = (
            browser_workflow.open_browser_action(
                site_id="youtube",
                query="Tame Impala",
            )
        )

        assert mismatch.success is False

        assert mismatch.status == (
            "browser_destination_mismatch"
        )

    finally:
        browser_workflow.open_trusted_browser_site_via_agent = (
            original_open_via_agent
        )

    # --------------------------------------------------
    # 4. Agent outage fails closed with no local browser fallback.
    # --------------------------------------------------

    try:
        browser_workflow.open_trusted_browser_site_via_agent = (
            lambda site_id, query=None: {
                "success": False,
                "status": "agent_unavailable",
                "message": (
                    "Mairon Desktop Agent is not reachable."
                ),
            }
        )

        unavailable = (
            browser_workflow.open_browser_action(
                site_id="youtube",
                query=None,
            )
        )

        assert unavailable.success is False

        assert unavailable.status == (
            "desktop_agent_unavailable"
        )

        assert (
            "Desktop Agent isn't running"
            in unavailable.error
        )

    finally:
        browser_workflow.open_trusted_browser_site_via_agent = (
            original_open_via_agent
        )

    print(
        "Mairon Phase 9.4 trusted-browser agent routing tests: PASS"
    )


if __name__ == "__main__":
    run()
