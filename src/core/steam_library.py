import difflib
import os
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional


def _decode_vdf_string(
    token: str,
) -> str:
    value = str(
        token
        or ""
    )

    if (
        len(
            value
        ) >= 2
        and value[0] == '"'
        and value[-1] == '"'
    ):
        value = value[
            1:-1
        ]

    value = value.replace(
        r"\\",
        "\\",
    )

    value = value.replace(
        r"\"",
        '"',
    )

    return value


def _tokenise_keyvalues(
    text: str,
) -> List[str]:
    """
    Minimal Valve KeyValues tokenizer for the text VDF/ACF files Steam uses
    for libraryfolders.vdf and appmanifest_*.acf.
    """

    source = re.sub(
        r"//[^\n\r]*",
        "",
        str(
            text
            or ""
        ),
    )

    return re.findall(
        r'"(?:\\.|[^"\\])*"|[{}]',
        source,
    )


def parse_keyvalues_text(
    text: str,
) -> Dict[str, object]:
    tokens = _tokenise_keyvalues(
        text
    )

    index = 0

    def parse_object():
        nonlocal index

        result = {}

        while index < len(
            tokens
        ):
            token = tokens[
                index
            ]

            if token == "}":
                index += 1
                return result

            if token == "{":
                index += 1
                continue

            key = _decode_vdf_string(
                token
            )

            index += 1

            if index >= len(
                tokens
            ):
                result[
                    key
                ] = ""
                break

            next_token = tokens[
                index
            ]

            if next_token == "{":
                index += 1

                result[
                    key
                ] = parse_object()

                continue

            result[
                key
            ] = _decode_vdf_string(
                next_token
            )

            index += 1

        return result

    return parse_object()


def _registry_steam_paths() -> List[Path]:
    if os.name != "nt":
        return []

    try:
        import winreg
    except Exception:
        return []

    candidates = []

    probes = (
        (
            winreg.HKEY_CURRENT_USER,
            r"Software\Valve\Steam",
            "SteamPath",
            0,
        ),
        (
            winreg.HKEY_CURRENT_USER,
            r"Software\Valve\Steam",
            "InstallPath",
            0,
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Valve\Steam",
            "InstallPath",
            getattr(
                winreg,
                "KEY_WOW64_32KEY",
                0,
            ),
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Valve\Steam",
            "InstallPath",
            getattr(
                winreg,
                "KEY_WOW64_64KEY",
                0,
            ),
        ),
    )

    for hive, key_path, value_name, view_flag in probes:
        try:
            with winreg.OpenKey(
                hive,
                key_path,
                0,
                winreg.KEY_READ
                | view_flag,
            ) as key:
                value, _ = (
                    winreg.QueryValueEx(
                        key,
                        value_name,
                    )
                )

        except OSError:
            continue

        value = str(
            value
            or ""
        ).strip()

        if value:
            candidates.append(
                Path(
                    value
                )
            )

    return candidates


def _steam_root_candidates() -> List[Path]:
    candidates = []

    override = str(
        os.environ.get(
            "MAIRON_STEAM_ROOT",
            "",
        )
        or ""
    ).strip()

    if override:
        candidates.append(
            Path(
                override
            )
        )

    candidates.extend(
        _registry_steam_paths()
    )

    for raw in (
        r"%ProgramFiles(x86)%\Steam",
        r"%ProgramFiles%\Steam",
        r"%LOCALAPPDATA%\Steam",
    ):
        expanded = os.path.expandvars(
            raw
        )

        if (
            expanded
            and "%"
            not in expanded
        ):
            candidates.append(
                Path(
                    expanded
                )
            )

    deduped = []

    seen = set()

    for candidate in candidates:
        key = str(
            candidate
        ).strip().lower()

        if (
            not key
            or key in seen
        ):
            continue

        seen.add(
            key
        )

        deduped.append(
            candidate
        )

    return deduped


def find_steam_root() -> Optional[Path]:
    for candidate in _steam_root_candidates():
        if (
            candidate.is_dir()
            and (
                candidate
                / "steamapps"
            ).is_dir()
        ):
            return candidate

    return None


def _library_roots_from_index(
    steam_root: Path,
) -> List[Path]:
    roots = [
        steam_root
    ]

    index_path = (
        steam_root
        / "steamapps"
        / "libraryfolders.vdf"
    )

    if not index_path.is_file():
        return roots

    try:
        parsed = parse_keyvalues_text(
            index_path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )
    except OSError:
        return roots

    libraryfolders = parsed.get(
        "libraryfolders"
    )

    if not isinstance(
        libraryfolders,
        dict,
    ):
        return roots

    for value in libraryfolders.values():
        if not isinstance(
            value,
            dict,
        ):
            continue

        path_value = str(
            value.get(
                "path"
            )
            or ""
        ).strip()

        if not path_value:
            continue

        roots.append(
            Path(
                path_value
            )
        )

    deduped = []
    seen = set()

    for root in roots:
        key = str(
            root
        ).strip().lower()

        if key in seen:
            continue

        seen.add(
            key
        )

        deduped.append(
            root
        )

    return deduped


def _read_manifest(
    manifest_path: Path,
    library_root: Path,
) -> Optional[dict]:
    try:
        parsed = parse_keyvalues_text(
            manifest_path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )
    except OSError:
        return None

    app_state = parsed.get(
        "AppState"
    )

    if not isinstance(
        app_state,
        dict,
    ):
        return None

    appid = str(
        app_state.get(
            "appid"
        )
        or ""
    ).strip()

    name = str(
        app_state.get(
            "name"
        )
        or ""
    ).strip()

    installdir = str(
        app_state.get(
            "installdir"
        )
        or ""
    ).strip()

    if (
        not appid.isdigit()
        or not name
        or not installdir
    ):
        return None

    install_path = (
        library_root
        / "steamapps"
        / "common"
        / installdir
    )

    # Presence of the manifest alone can represent an incomplete/moved app.
    # Core only advertises games whose local install directory still exists.
    if not install_path.is_dir():
        return None

    return {
        "appid": appid,
        "name": name,
        "installdir": installdir,
        "install_path": str(
            install_path
        ),
        "library_root": str(
            library_root
        ),
        "manifest_path": str(
            manifest_path
        ),
    }


def discover_installed_steam_games(
    steam_root: Optional[Path] = None,
) -> List[dict]:
    root = (
        Path(
            steam_root
        )
        if steam_root is not None
        else find_steam_root()
    )

    if (
        root is None
        or not root.is_dir()
    ):
        return []

    games = []

    for library_root in _library_roots_from_index(
        root
    ):
        steamapps = (
            library_root
            / "steamapps"
        )

        if not steamapps.is_dir():
            continue

        for manifest_path in sorted(
            steamapps.glob(
                "appmanifest_*.acf"
            )
        ):
            game = _read_manifest(
                manifest_path=manifest_path,
                library_root=library_root,
            )

            if game is not None:
                games.append(
                    game
                )

    by_appid = {}

    for game in games:
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


def normalise_game_title(
    value: str,
) -> str:
    text = unicodedata.normalize(
        "NFKD",
        str(
            value
            or ""
        ),
    )

    text = text.replace(
        "™",
        "",
    ).replace(
        "®",
        "",
    ).replace(
        "©",
        "",
    )

    text = text.casefold()

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _title_similarity(
    query: str,
    candidate: str,
) -> float:
    query_norm = normalise_game_title(
        query
    )

    candidate_norm = normalise_game_title(
        candidate
    )

    if (
        not query_norm
        or not candidate_norm
    ):
        return 0.0

    if query_norm == candidate_norm:
        return 1.0

    ratio = difflib.SequenceMatcher(
        None,
        query_norm,
        candidate_norm,
    ).ratio()

    query_tokens = set(
        query_norm.split()
    )

    candidate_tokens = set(
        candidate_norm.split()
    )

    if (
        query_tokens
        and query_tokens.issubset(
            candidate_tokens
        )
    ):
        coverage = (
            len(
                query_norm
            )
            / max(
                len(
                    candidate_norm
                ),
                1,
            )
        )

        ratio = max(
            ratio,
            min(
                0.94,
                0.80
                + (
                    0.14
                    * coverage
                ),
            ),
        )

    return ratio


def resolve_installed_steam_game(
    requested_title: str,
    games: Optional[List[dict]] = None,
) -> dict:
    installed = (
        list(
            games
        )
        if games is not None
        else discover_installed_steam_games()
    )

    query = str(
        requested_title
        or ""
    ).strip()

    if not query:
        return {
            "status": "invalid_query",
            "match": None,
            "candidates": [],
        }

    query_norm = normalise_game_title(
        query
    )

    exact = [
        game
        for game in installed
        if normalise_game_title(
            game.get(
                "name"
            )
        )
        == query_norm
    ]

    if len(
        exact
    ) == 1:
        return {
            "status": "matched",
            "match": exact[
                0
            ],
            "score": 1.0,
            "candidates": exact,
        }

    scored = []

    for game in installed:
        score = _title_similarity(
            query,
            str(
                game.get(
                    "name"
                )
                or ""
            ),
        )

        scored.append(
            (
                score,
                game,
            )
        )

    scored.sort(
        key=lambda item: (
            item[
                0
            ],
            str(
                item[
                    1
                ].get(
                    "name"
                )
                or ""
            ).lower(),
        ),
        reverse=True,
    )

    candidates = [
        {
            **game,
            "score": round(
                score,
                4,
            ),
        }
        for score, game in scored[:3]
    ]

    if not scored:
        return {
            "status": "not_found",
            "match": None,
            "candidates": [],
        }

    best_score, best_game = scored[
        0
    ]

    second_score = (
        scored[
            1
        ][
            0
        ]
        if len(
            scored
        ) > 1
        else 0.0
    )

    # Conservative fuzzy launch boundary: high-confidence winner and a clear
    # margin over the next installed title. Wrong-game launches are worse than
    # asking Oliver to be more specific.
    if (
        best_score >= 0.88
        and (
            best_score
            - second_score
        ) >= 0.08
    ):
        return {
            "status": "matched",
            "match": best_game,
            "score": round(
                best_score,
                4,
            ),
            "candidates": candidates,
        }

    if best_score >= 0.65:
        return {
            "status": "ambiguous",
            "match": None,
            "score": round(
                best_score,
                4,
            ),
            "candidates": candidates,
        }

    return {
        "status": "not_found",
        "match": None,
        "score": round(
            best_score,
            4,
        ),
        "candidates": candidates,
    }
