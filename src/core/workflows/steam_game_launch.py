from core.evidence import (
    Evidence,
    EvidenceBundle,
)
from core.steam_library import (
    discover_installed_steam_games,
    resolve_installed_steam_game,
)
from core.workflow_result import (
    WorkflowResult,
)
from core.steam_alias_store import (
    delete_steam_game_alias,
    get_steam_game_alias,
)
from tools.desktop_tools import (
    launch_steam_game_appid,
)


def launch_installed_steam_game(
    requested_title: str,
) -> WorkflowResult:
    """
    Resolve a requested title against local Steam manifests, then launch the
    verified AppID through Steam.

    Qwen does not choose the AppID.
    """

    title = str(
        requested_title
        or ""
    ).strip()

    installed = (
        discover_installed_steam_games()
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
            candidates[:3]
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
        "[Tool] Mairon Core required: launch_steam_game_appid"
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
            status="unexpected_tool_result",
            error=(
                "The Steam launch layer returned an unexpected result."
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
        return WorkflowResult(
            success=False,
            status="steam_launch_failed",
            error=(
                result.get(
                    "message"
                )
                or (
                    f"I couldn't launch {game_name} through Steam."
                )
            ),
            data={
                "requested_title": title,
                "match": match,
                "tool_result": result,
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
                f"{appid} from local Steam manifests and requested launch "
                "through Steam."
            ),
            provenance="desktop_tool",
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
            "tool_result": result,
        },
    )
