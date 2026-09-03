import sys
import tempfile
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
from core.steam_library import (
    discover_installed_steam_games,
    resolve_installed_steam_game,
)
from core.workflow_result import (
    WorkflowResult,
)
import core.orchestrator as orchestrator_module
from core.orchestrator import (
    MaironCore,
)
from tools import desktop_tools


def _write_manifest(
    library_root,
    appid,
    name,
    installdir,
):
    steamapps = (
        library_root
        / "steamapps"
    )

    steamapps.mkdir(
        parents=True,
        exist_ok=True,
    )

    install_path = (
        steamapps
        / "common"
        / installdir
    )

    install_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest = (
        steamapps
        / f"appmanifest_{appid}.acf"
    )

    manifest.write_text(
        '"AppState"\n'
        '{\n'
        f'    "appid" "{appid}"\n'
        f'    "name" "{name}"\n'
        f'    "installdir" "{installdir}"\n'
        '    "StateFlags" "4"\n'
        '}\n',
        encoding="utf-8",
    )


def run():
    # --------------------------------------------------
    # 1. Discover installed games across multiple Steam libraries.
    # --------------------------------------------------

    with tempfile.TemporaryDirectory() as temp:
        root = Path(
            temp
        ) / "Steam"

        extra = Path(
            temp
        ) / "GamesSSD"

        (
            root
            / "steamapps"
        ).mkdir(
            parents=True
        )

        (
            extra
            / "steamapps"
        ).mkdir(
            parents=True
        )

        library_index = (
            root
            / "steamapps"
            / "libraryfolders.vdf"
        )

        escaped_extra = str(
            extra
        ).replace(
            "\\",
            "\\\\",
        )

        library_index.write_text(
            '"libraryfolders"\n'
            '{\n'
            '    "0"\n'
            '    {\n'
            f'        "path" "{str(root).replace(chr(92), chr(92)+chr(92))}"\n'
            '    }\n'
            '    "1"\n'
            '    {\n'
            f'        "path" "{escaped_extra}"\n'
            '    }\n'
            '}\n',
            encoding="utf-8",
        )

        _write_manifest(
            root,
            "111",
            "Test Game",
            "TestGame",
        )

        _write_manifest(
            extra,
            "222",
            "Another Game 2",
            "AnotherGame2",
        )

        games = (
            discover_installed_steam_games(
                steam_root=root
            )
        )

        assert {
            game[
                "appid"
            ]
            for game in games
        } == {
            "111",
            "222",
        }

        exact = (
            resolve_installed_steam_game(
                "Test Game",
                games=games,
            )
        )

        assert exact[
            "status"
        ] == "matched"

        assert exact[
            "match"
        ][
            "appid"
        ] == "111"

        fuzzy = (
            resolve_installed_steam_game(
                "Another Game 2",
                games=games,
            )
        )

        assert fuzzy[
            "match"
        ][
            "appid"
        ] == "222"

    # --------------------------------------------------
    # 2. Existing named desktop app wins over generic game candidate.
    # --------------------------------------------------

    steam_client = classify_turn(
        "Open Steam"
    )

    assert steam_client.intent == (
        "launch_application"
    )

    game_turn = classify_turn(
        "Open Test Game"
    )

    assert game_turn.intent == (
        "launch_steam_game"
    )

    assert game_turn.entities[
        "steam_game_title"
    ] == "Test Game"

    # Obvious file opens are not stolen by Steam-game routing.
    file_turn = classify_turn(
        "Open report.pdf"
    )

    assert file_turn.intent != (
        "launch_steam_game"
    )

    # --------------------------------------------------
    # 3. Steam URI layer accepts only numeric Core-selected AppIDs.
    # --------------------------------------------------

    original_launch_uri = (
        desktop_tools._launch_uri
    )

    original_os_name = (
        desktop_tools.os.name
    )

    uris = []

    try:
        desktop_tools.os.name = "nt"

        def fake_launch_uri(
            uri,
        ):
            uris.append(
                uri
            )

            return {
                "success": True,
            }

        desktop_tools._launch_uri = (
            fake_launch_uri
        )

        result = (
            desktop_tools
            .launch_steam_game_appid(
                "123456"
            )
        )

        assert result[
            "success"
        ] is True

        assert uris == [
            "steam://run/123456"
        ]

        rejected = (
            desktop_tools
            .launch_steam_game_appid(
                "123 & calc.exe"
            )
        )

        assert rejected[
            "success"
        ] is False

        assert uris == [
            "steam://run/123456"
        ]

    finally:
        desktop_tools._launch_uri = (
            original_launch_uri
        )

        desktop_tools.os.name = (
            original_os_name
        )

    # --------------------------------------------------
    # 4. Full Core game-launch route is deterministic and clears stale
    #    desktop-app referents.
    # --------------------------------------------------

    original_workflow = (
        orchestrator_module
        .launch_installed_steam_game
    )

    try:
        def fake_workflow(
            requested_title,
        ):
            return WorkflowResult(
                success=True,
                status="steam_game_launch_requested",
                answer_fact=(
                    f"Launching {requested_title} through Steam."
                ),
                data={
                    "requested_title": requested_title,
                    "appid": "111",
                },
            )

        orchestrator_module.launch_installed_steam_game = (
            fake_workflow
        )

        core = MaironCore()

        # Establish an older desktop referent first.
        core.conversation_state.remember_desktop_target(
            "chrome"
        )

        decision = core.prepare_turn(
            "Open Test Game"
        )

        assert decision.direct_response == (
            "Launching Test Game through Steam."
        )

        assert (
            core.conversation_state
            .active_desktop_target
            is None
        )

        assert (
            core.conversation_state
            .active_steam_game_title
            == "Test Game"
        )

    finally:
        orchestrator_module.launch_installed_steam_game = (
            original_workflow
        )

    print(
        "Mairon Phase 8.3 installed Steam game launch tests: PASS"
    )


if __name__ == "__main__":
    run()
