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
import core.workflows.steam_game_launch as steam_workflow

from core.desktop_agent_protocol import (
    build_request,
    validate_request,
)
from desktop_agent import (
    create_desktop_agent_server,
)


def run():
    # --------------------------------------------------
    # 1. Steam Agent protocol is narrow and numeric-AppID-only.
    # --------------------------------------------------

    listed = validate_request(
        build_request(
            request_id="phase9-6-list",
            action="list_installed_steam_games",
            args={},
        )
    )

    assert listed[
        "args"
    ] == {}

    launch = validate_request(
        build_request(
            request_id="phase9-6-launch",
            action="launch_steam_game_appid",
            args={
                "appid": "123456",
            },
        )
    )

    assert launch[
        "args"
    ] == {
        "appid": "123456",
    }

    for bad_args in (
        {
            "appid": "123 & calc.exe",
        },
        {
            "appid": "123456",
            "command": "powershell",
        },
    ):
        try:
            validate_request({
                "version": "1",
                "request_id": "phase9-6-bad",
                "action": "launch_steam_game_appid",
                "args": bad_args,
            })

        except ValueError:
            pass

        else:
            raise AssertionError(
                "Steam Agent protocol accepted unsafe launch arguments."
            )

    # --------------------------------------------------
    # 2. Real workflow lists through Agent, resolves in Core, then launches
    #    the exact resolved numeric AppID back through Agent.
    # --------------------------------------------------

    calls = []

    games = [
        {
            "appid": "123456",
            "name": "Phase Nine Test Game",
            "installdir": "PhaseNine",
            "install_path": r"D:\SteamLibrary\steamapps\common\PhaseNine",
            "library_root": r"D:\SteamLibrary",
            "manifest_path": (
                r"D:\SteamLibrary\steamapps\appmanifest_123456.acf"
            ),
        },
        {
            "appid": "222222",
            "name": "Different Installed Game",
            "installdir": "Different",
            "install_path": r"D:\SteamLibrary\steamapps\common\Different",
            "library_root": r"D:\SteamLibrary",
            "manifest_path": (
                r"D:\SteamLibrary\steamapps\appmanifest_222222.acf"
            ),
        },
    ]

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

        if action == "list_installed_steam_games":
            return {
                "success": True,
                "status": "steam_library_listed",
                "count": len(
                    games
                ),
                "games": list(
                    games
                ),
            }

        if action == "launch_steam_game_appid":
            return {
                "success": True,
                "status": "steam_launch_requested",
                "appid": args[
                    "appid"
                ],
                "message": (
                    "Steam game launch requested."
                ),
            }

        raise AssertionError(
            f"Unexpected Phase 9.6 Agent action: {action}"
        )

    secret = (
        "phase9-6-test-secret-"
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

    original_alias = (
        steam_workflow.get_steam_game_alias
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

        steam_workflow.get_steam_game_alias = (
            lambda title: None
        )

        result = (
            steam_workflow.launch_installed_steam_game(
                "Phase Nine Test Game"
            )
        )

        assert result.success is True

        assert result.status == (
            "steam_game_launch_requested"
        )

        assert result.data[
            "appid"
        ] == "123456"

        assert result.answer_fact == (
            "Launching Phase Nine Test Game through Steam."
        )

        assert calls == [
            (
                "list_installed_steam_games",
                {},
            ),
            (
                "launch_steam_game_appid",
                {
                    "appid": "123456",
                },
            ),
        ]

        assert (
            result.evidence.evidence[
                0
            ].provenance
            == "desktop_agent"
        )

    finally:
        steam_workflow.get_steam_game_alias = (
            original_alias
        )

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
    # 3. Core rejects a successful Agent reply for the wrong AppID.
    # --------------------------------------------------

    original_discover = (
        steam_workflow.discover_installed_steam_games
    )

    original_launch = (
        steam_workflow.launch_steam_game_appid
    )

    original_alias = (
        steam_workflow.get_steam_game_alias
    )

    try:
        steam_workflow.discover_installed_steam_games = (
            lambda: [
                {
                    "appid": "123456",
                    "name": "Phase Nine Test Game",
                }
            ]
        )

        steam_workflow.get_steam_game_alias = (
            lambda title: None
        )

        steam_workflow.launch_steam_game_appid = (
            lambda appid: {
                "success": True,
                "status": "steam_launch_requested",
                "appid": "999999",
            }
        )

        mismatch = (
            steam_workflow.launch_installed_steam_game(
                "Phase Nine Test Game"
            )
        )

        assert mismatch.success is False

        assert mismatch.status == (
            "steam_appid_confirmation_mismatch"
        )

    finally:
        steam_workflow.discover_installed_steam_games = (
            original_discover
        )

        steam_workflow.launch_steam_game_appid = (
            original_launch
        )

        steam_workflow.get_steam_game_alias = (
            original_alias
        )

    # --------------------------------------------------
    # 4. Agent outage fails closed at Steam-library discovery.
    # --------------------------------------------------

    original_list = (
        steam_workflow.list_installed_steam_games_via_agent
    )

    try:
        steam_workflow.list_installed_steam_games_via_agent = (
            lambda: {
                "success": False,
                "status": "agent_unavailable",
                "message": (
                    "Mairon Desktop Agent is not reachable."
                ),
            }
        )

        unavailable = (
            steam_workflow.launch_installed_steam_game(
                "Phase Nine Test Game"
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
        steam_workflow.list_installed_steam_games_via_agent = (
            original_list
        )

    print(
        "Mairon Phase 9.6 Steam library/launch Agent routing tests: PASS"
    )


if __name__ == "__main__":
    run()
