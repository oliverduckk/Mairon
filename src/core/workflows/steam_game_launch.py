from typing import List

from core.desktop_agent_client import (
    launch_steam_game_appid_via_agent,
    list_installed_steam_games_via_agent,
)
from core.evidence import (
    Evidence,
    EvidenceBundle,
)
from core.steam_library import (
    resolve_installed_steam_game,
)
from core.workflow_result import (
    WorkflowResult,
)
from core.steam_alias_store import (
    delete_steam_game_alias,
    get_steam_game_alias,
)


class DesktopAgentSteamError(
    RuntimeError
):
    def __init__(
        self,
        status: str,
        message: str,
    ):
        super().__init__(
            message
        )

        self.status = str(
            status
            or "steam_agent_failed"
        )

        self.message = str(
            message
            or "Steam desktop action failed."
        )


def _verified_agent_game(
    raw,
):
    if not isinstance(
        raw,
        dict,
    ):
        return None

    appid = str(
        raw.get(
            "appid",
            "",
        )
        or ""
    ).strip()

    name = str(
        raw.get(
            "name",
            "",
        )
        or ""
    ).strip()

    if (
        not appid.isdigit()
        or len(
            appid
        ) > 20
        or not name
        or len(
            name
        ) > 300
    ):
        return None

    verified = {
        "appid": appid,
        "name": name,
    }

    # Preserve useful Agent-observed metadata for evidence/debugging, but Core
    # does not treat these Windows paths as executable authority.
    for key in (
        "installdir",
        "install_path",
        "library_root",
        "manifest_path",
    ):
        value = str(
            raw.get(
                key,
                "",
            )
            or ""
        ).strip()

        if value:
            verified[
                key
            ] = value

    return verified


def discover_installed_steam_games() -> List[dict]:
    """
    Compatibility-shaped Core wrapper around Desktop Agent Steam discovery.

    The Agent reads the Windows Steam manifests. Core accepts only structurally
    valid numeric-AppID/name entries and keeps all title resolution, ambiguity,
    learned aliases, and final AppID choice in Core.
    """

    result = list_installed_steam_games_via_agent()

    if not isinstance(
        result,
        dict,
    ):
        raise DesktopAgentSteamError(
            status="unexpected_agent_result",
            message=(
                "The Windows Desktop Agent returned an unexpected Steam "
                "library result."
            ),
        )

    if result.get(
        "success"
    ) is not True:
        result_status = str(
            result.get(
                "status",
                "",
            )
            or ""
        ).strip()

        if result_status == "agent_unavailable":
            raise DesktopAgentSteamError(
                status="desktop_agent_unavailable",
                message=(
                    "The Windows Desktop Agent isn't running, so I can't "
                    "inspect your installed Steam games right now."
                ),
            )

        raise DesktopAgentSteamError(
            status=(
                result_status
                or "steam_library_failed"
            ),
            message=(
                result.get(
                    "message"
                )
                or "I couldn't inspect the installed Steam library."
            ),
        )

    raw_games = result.get(
        "games",
        [],
    )

    if not isinstance(
        raw_games,
        list,
    ):
        raise DesktopAgentSteamError(
            status="invalid_agent_steam_library",
            message=(
                "The Windows Desktop Agent returned invalid Steam library "
                "metadata."
            ),
        )

    by_appid = {}

    for raw_game in raw_games:
        game = _verified_agent_game(
            raw_game
        )

        if game is None:
            continue

        by_appid[
            game[
                "appid"
            ]
        ] = game

    return sorted(
        by_appid.values(),
        key=lambda game: (
            game[
                "name"
            ].lower(),
            game[
                "appid"
            ],
        ),
    )


def launch_steam_game_appid(
    appid: str,
):
    """
    Compatibility-shaped execution wrapper.

    Production routes the exact Core-selected numeric AppID through the
    authenticated Windows Desktop Agent. Existing deterministic Phase 8 tests
    may monkeypatch this workflow-local name.
    """

    return launch_steam_game_appid_via_agent(
        appid=appid,
    )


def _agent_confirmed_appid(
    result,
    expected_appid: str,
) -> bool:
    if not isinstance(
        result,
        dict,
    ):
        return False

    actual = str(
        result.get(
            "appid",
            "",
        )
        or ""
    ).strip()

    expected = str(
        expected_appid
        or ""
    ).strip()

    return (
        actual.isdigit()
        and expected.isdigit()
        and actual == expected
    )


def launch_installed_steam_game(
    requested_title: str,
) -> WorkflowResult:
    """
    Resolve a requested title against the Agent-observed installed Steam
    library, then launch the exact Core-selected AppID through the Agent.

    Qwen does not choose the AppID.
    """

    title = str(
        requested_title
        or ""
    ).strip()

    try:
        installed = (
            discover_installed_steam_games()
        )

    except DesktopAgentSteamError as exc:
        return WorkflowResult(
            success=False,
            status=exc.status,
            error=exc.message,
            data={
                "requested_title": title,
            },
        )

    if not installed:
        return WorkflowResult(
            success=False,
            status="steam_library_unavailable",
            error=(
                "I couldn't find any installed Steam games on this desktop."
            ),
            data={
                "requested_title": title,
            },
        )

    alias_entry = get_steam_game_alias(
        title
    )

    resolution = None

    if alias_entry is not None:
        alias_appid = str(
            alias_entry.get(
                "appid",
                "",
            )
            or ""
        ).strip()

        alias_matches = [
            game
            for game in installed
            if str(
                game.get(
                    "appid",
                    "",
                )
                or ""
            ).strip()
            == alias_appid
        ]

        if len(
            alias_matches
        ) == 1:
            resolution = {
                "status": "matched",
                "match": alias_matches[
                    0
                ],
                "score": 1.0,
                "match_type": "learned_alias",
                "candidates": alias_matches,
            }

        else:
            # Stale aliases never override current verified Steam metadata.
            delete_steam_game_alias(
                title
            )

    if resolution is None:
        resolution = (
            resolve_installed_steam_game(
                requested_title=title,
                games=installed,
            )
        )

    status = str(
        resolution.get(
            "status"
        )
        or ""
    )

    if status == "ambiguous":
        candidates = [
            str(
                candidate.get(
                    "name"
                )
                or ""
            ).strip()
            for candidate in resolution.get(
                "candidates",
                [],
            )
            if str(
                candidate.get(
                    "name"
                )
                or ""
            ).strip()
        ]

        candidate_text = ", ".join(
            candidates[
                :3
            ]
        )

        return WorkflowResult(
            success=False,
            status="ambiguous_game",
            error=(
                "I found a few installed Steam games that could match "
                f'"{title}": {candidate_text}. Be a bit more specific.'
            ),
            data={
                "requested_title": title,
                "resolution": resolution,
            },
        )

    if status != "matched":
        return WorkflowResult(
            success=False,
            status="game_not_found",
            error=(
                "I couldn't find an installed Steam game matching "
                f'"{title}".'
            ),
            data={
                "requested_title": title,
                "resolution": resolution,
            },
        )

    match = resolution.get(
        "match"
    )

    if not isinstance(
        match,
        dict,
    ):
        return WorkflowResult(
            success=False,
            status="invalid_game_resolution",
            error=(
                "Steam game resolution returned an invalid match."
            ),
            data={
                "requested_title": title,
                "resolution": resolution,
            },
        )

    appid = str(
        match.get(
            "appid"
        )
        or ""
    ).strip()

    game_name = str(
        match.get(
            "name"
        )
        or title
    ).strip()

    print(
        "[Steam] Resolved installed game: "
        f"{game_name} (AppID {appid})"
    )

    print(
        "[Desktop Agent] Core requested Steam AppID launch"
    )

    result = launch_steam_game_appid(
        appid
    )

    if not isinstance(
        result,
        dict,
    ):
        return WorkflowResult(
            success=False,
            status="unexpected_agent_result",
            error=(
                "The Windows Desktop Agent returned an unexpected Steam "
                "launch result."
            ),
            data={
                "requested_title": title,
                "match": match,
                "raw_result": str(
                    result
                ),
            },
        )

    if result.get(
        "success"
    ) is not True:
        result_status = str(
            result.get(
                "status",
                "",
            )
            or ""
        ).strip()

        if result_status == "agent_unavailable":
            workflow_status = (
                "desktop_agent_unavailable"
            )

            error = (
                "The Windows Desktop Agent isn't running, so I can't "
                f"launch {game_name} right now."
            )

        else:
            workflow_status = (
                result_status
                or "steam_launch_failed"
            )

            error = (
                result.get(
                    "message"
                )
                or (
                    f"I couldn't launch {game_name} through Steam."
                )
            )

        return WorkflowResult(
            success=False,
            status=workflow_status,
            error=error,
            data={
                "requested_title": title,
                "match": match,
                "agent_result": result,
            },
        )

    if not _agent_confirmed_appid(
        result,
        appid,
    ):
        return WorkflowResult(
            success=False,
            status="steam_appid_confirmation_mismatch",
            error=(
                "The Windows Desktop Agent did not confirm the exact "
                "Core-selected Steam AppID, so I won't claim the game "
                "launch succeeded."
            ),
            data={
                "requested_title": title,
                "game_name": game_name,
                "appid": appid,
                "agent_result": result,
            },
        )

    evidence = EvidenceBundle(
        authority="desktop",
        success=True,
    )

    evidence.add(
        Evidence(
            claim=(
                f'Core resolved "{game_name}" to installed Steam AppID '
                f"{appid} from Agent-observed Steam metadata, and the Windows "
                "Desktop Agent confirmed the exact AppID launch request."
            ),
            provenance="desktop_agent",
            confidence="verified",
            source_name="steam_local_manifest",
            source_id=appid,
            data={
                "requested_title": title,
                "game_name": game_name,
                "appid": appid,
                "manifest_path": match.get(
                    "manifest_path"
                ),
            },
        )
    )

    return WorkflowResult(
        success=True,
        status="steam_game_launch_requested",
        answer_fact=(
            f"Launching {game_name} through Steam."
        ),
        evidence=evidence,
        data={
            "requested_title": title,
            "game_name": game_name,
            "appid": appid,
            "match": match,
            "agent_result": result,
        },
    )
