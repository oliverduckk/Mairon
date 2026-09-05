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
import core.workflows.application_launch as application_launch

from desktop_agent import (
    create_desktop_agent_server,
)


def run():
    # --------------------------------------------------
    # 1. Real workflow crosses the authenticated agent boundary.
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

        assert action == "launch_application"

        return {
            "success": True,
            "status": "launch_requested",
            "target_id": args[
                "app_name"
            ],
            "message": (
                "Calculator launch requested."
            ),
        }

    secret = (
        "phase9-2-test-secret-"
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
            application_launch
            .launch_approved_application(
                "calculator"
            )
        )

        assert result.success is True
        assert result.status == "launched"

        assert calls == [
            (
                "launch_application",
                {
                    "app_name": "calculator",
                },
            )
        ]

        assert (
            result.data[
                "agent_result"
            ][
                "status"
            ]
            == "launch_requested"
        )

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
    # 2. No agent means no silent local fallback.
    # --------------------------------------------------

    original_call = (
        application_launch
        .launch_application_via_agent
    )

    try:
        application_launch.launch_application_via_agent = (
            lambda app_name: {
                "success": False,
                "status": "agent_unavailable",
                "message": (
                    "Mairon Desktop Agent is not reachable."
                ),
            }
        )

        unavailable = (
            application_launch
            .launch_approved_application(
                "calculator"
            )
        )

        assert unavailable.success is False

        assert (
            unavailable.status
            == "desktop_agent_unavailable"
        )

        assert (
            "Desktop Agent isn't running"
            in unavailable.error
        )

    finally:
        application_launch.launch_application_via_agent = (
            original_call
        )

    print(
        "Mairon Phase 9.2 launch-application agent routing tests: PASS"
    )


if __name__ == "__main__":
    run()
