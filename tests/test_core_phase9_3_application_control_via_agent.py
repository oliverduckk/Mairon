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
import core.workflows.application_control as control_module

from core.desktop_agent_protocol import (
    build_request,
    validate_request,
)
from desktop_agent import (
    create_desktop_agent_server,
)


def run():
    # --------------------------------------------------
    # 1. Protocol explicitly allows bounded close/focus requests.
    # --------------------------------------------------

    close_request = validate_request(
        build_request(
            request_id="phase9-3-close",
            action="close_application",
            args={
                "app_name": "spotify",
            },
        )
    )

    assert close_request[
        "action"
    ] == "close_application"

    assert close_request[
        "args"
    ] == {
        "app_name": "spotify",
    }

    focus_request = validate_request(
        build_request(
            request_id="phase9-3-focus",
            action="focus_application",
            args={
                "app_name": "discord",
            },
        )
    )

    assert focus_request[
        "action"
    ] == "focus_application"

    assert focus_request[
        "args"
    ] == {
        "app_name": "discord",
    }

    # Arbitrary execution remains impossible through either action.
    for action in (
        "close_application",
        "focus_application",
    ):
        try:
            validate_request({
                "version": "1",
                "request_id": (
                    f"phase9-3-bad-{action}"
                ),
                "action": action,
                "args": {
                    "app_name": "spotify",
                    "command": "whoami",
                },
            })

        except ValueError:
            pass

        else:
            raise AssertionError(
                f"{action} accepted an arbitrary command argument."
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

        app_name = args[
            "app_name"
        ]

        if action == "close_application":
            return {
                "success": True,
                "status": (
                    "terminated"
                    if app_name == "discord"
                    else "close_requested"
                ),
                "target_id": app_name,
                "close_behavior": (
                    "quit_process"
                    if app_name == "discord"
                    else "graceful_window"
                ),
            }

        if action == "focus_application":
            return {
                "success": True,
                "status": "focused",
                "target_id": app_name,
            }

        raise AssertionError(
            "Unexpected Phase 9.3 action reached executor."
        )

    secret = (
        "phase9-3-test-secret-"
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

        graceful = (
            control_module
            .control_approved_application(
                app_name="spotify",
                action="close",
            )
        )

        assert graceful.success is True
        assert graceful.status == "closed"
        assert graceful.answer_fact == (
            "Spotify window's closed."
        )

        assert (
            graceful.evidence.evidence[
                0
            ].provenance
            == "desktop_agent"
        )

        tray = (
            control_module
            .control_approved_application(
                app_name="discord",
                action="close",
            )
        )

        assert tray.success is True
        assert tray.status == "closed"
        assert tray.answer_fact == (
            "Discord's closed."
        )

        focused = (
            control_module
            .control_approved_application(
                app_name="discord",
                action="focus",
            )
        )

        assert focused.success is True
        assert focused.status == "focused"
        assert focused.answer_fact == (
            "Discord's in front."
        )

        assert calls == [
            (
                "close_application",
                {
                    "app_name": "spotify",
                },
            ),
            (
                "close_application",
                {
                    "app_name": "discord",
                },
            ),
            (
                "focus_application",
                {
                    "app_name": "discord",
                },
            ),
        ]

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
    # 3. Agent outage fails closed: no in-process fallback.
    # --------------------------------------------------

    original_close_via_agent = (
        control_module.close_application_via_agent
    )

    original_focus_via_agent = (
        control_module.focus_application_via_agent
    )

    try:
        control_module.close_application_via_agent = (
            lambda app_name: {
                "success": False,
                "status": "agent_unavailable",
                "message": (
                    "Mairon Desktop Agent is not reachable."
                ),
            }
        )

        control_module.focus_application_via_agent = (
            lambda app_name: {
                "success": False,
                "status": "agent_unavailable",
                "message": (
                    "Mairon Desktop Agent is not reachable."
                ),
            }
        )

        close_unavailable = (
            control_module
            .control_approved_application(
                app_name="spotify",
                action="close",
            )
        )

        assert close_unavailable.success is False

        assert (
            close_unavailable.status
            == "desktop_agent_unavailable"
        )

        assert (
            "Desktop Agent isn't running"
            in close_unavailable.error
        )

        focus_unavailable = (
            control_module
            .control_approved_application(
                app_name="discord",
                action="focus",
            )
        )

        assert focus_unavailable.success is False

        assert (
            focus_unavailable.status
            == "desktop_agent_unavailable"
        )

        assert (
            "Desktop Agent isn't running"
            in focus_unavailable.error
        )

    finally:
        control_module.close_application_via_agent = (
            original_close_via_agent
        )

        control_module.focus_application_via_agent = (
            original_focus_via_agent
        )

    print(
        "Mairon Phase 9.3 application-control agent routing tests: PASS"
    )


if __name__ == "__main__":
    run()
