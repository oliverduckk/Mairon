import os
import sys
import tempfile
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


from core.desktop_agent_client import (
    launch_application_via_agent,
    ping_desktop_agent,
)
from core.desktop_agent_protocol import (
    build_request,
    validate_request,
)


# desktop_agent.py lives directly under src/.
from desktop_agent import (
    create_desktop_agent_server,
)


def run():
    # --------------------------------------------------
    # 1. Protocol refuses arbitrary actions/command execution.
    # --------------------------------------------------

    safe = validate_request(
        build_request(
            request_id="test-safe",
            action="launch_application",
            args={
                "app_name": "calculator",
            },
        )
    )

    assert safe[
        "action"
    ] == "launch_application"

    try:
        validate_request({
            "version": "1",
            "request_id": "bad-action",
            "action": "run_command",
            "args": {
                "command": "calc.exe",
            },
        })

    except ValueError:
        pass

    else:
        raise AssertionError(
            "Desktop Agent accepted an arbitrary action."
        )

    try:
        validate_request({
            "version": "1",
            "request_id": "bad-args",
            "action": "launch_application",
            "args": {
                "app_name": "calculator",
                "command": "whoami",
            },
        })

    except ValueError:
        pass

    else:
        raise AssertionError(
            "Desktop Agent accepted an arbitrary command argument."
        )

    # --------------------------------------------------
    # 2. Authenticated localhost ping works.
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

        if action == "ping":
            return {
                "success": True,
                "status": "pong",
                "agent": "test_desktop",
            }

        if action == "launch_application":
            return {
                "success": True,
                "status": "launched",
                "app_name": args[
                    "app_name"
                ],
            }

        raise AssertionError(
            "Unexpected action reached executor."
        )

    secret = (
        "phase9-test-secret-"
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

    try:
        host, port = (
            server.server_address
        )

        base_url = (
            f"http://{host}:{port}"
        )

        pong = ping_desktop_agent(
            base_url=base_url,
            secret=secret,
            timeout=2.0,
        )

        assert pong[
            "success"
        ] is True

        assert pong[
            "status"
        ] == "pong"

        # --------------------------------------------------
        # 3. Wrong secret is rejected before executor.
        # --------------------------------------------------

        before = list(
            calls
        )

        unauthorized = (
            ping_desktop_agent(
                base_url=base_url,
                secret="wrong-secret-value",
                timeout=2.0,
            )
        )

        assert unauthorized[
            "success"
        ] is False

        assert unauthorized[
            "status"
        ] == "unauthorized"

        assert calls == before

        # --------------------------------------------------
        # 4. One allowlisted application action crosses boundary.
        # --------------------------------------------------

        result = (
            launch_application_via_agent(
                "calculator",
                base_url=base_url,
                secret=secret,
                timeout=2.0,
            )
        )

        assert result[
            "success"
        ] is True

        assert result[
            "app_name"
        ] == "calculator"

        assert (
            "launch_application",
            {
                "app_name": "calculator",
            },
        ) in calls

    finally:
        server.shutdown()
        server.server_close()
        thread.join(
            timeout=2.0
        )

    # --------------------------------------------------
    # 5. Phase 9.1 may never bind the agent to the LAN.
    # --------------------------------------------------

    try:
        create_desktop_agent_server(
            host="0.0.0.0",
            port=0,
            secret=secret,
            action_executor=fake_executor,
        )

    except ValueError:
        pass

    else:
        raise AssertionError(
            "Phase 9.1 Desktop Agent was allowed to bind to the LAN."
        )

    print(
        "Mairon Phase 9.1 Desktop Agent boundary tests: PASS"
    )


if __name__ == "__main__":
    run()
