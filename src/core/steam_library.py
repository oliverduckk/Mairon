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


def derive_game_title_acronym(
    value: str,
) -> str:
    """
    Derive a conservative shorthand from an installed Steam title.

    Examples:
      Counter-Strike 2 -> cs2
      Grand Theft Auto V -> gtav
      AdVenture Capitalist -> ac

    The alias is derived from the verified installed title; it is never a
    hard-coded game-name mapping.
    """

    normalised = normalise_game_title(
        value
    )

    tokens = [
        token
        for token in normalised.split()
        if token
    ]

    if len(
        tokens
    ) < 2:
        return ""

    parts = []

    for token in tokens:
        if token.isdigit():
            parts.append(
                token
            )
        else:
            parts.append(
                token[
                    0
                ]
            )

    return "".join(
        parts
    ).lower()


def derive_game_title_aliases(
    value: str,
) -> List[str]:
    """
    Derive conservative shorthand aliases from a verified installed title.

    Example:
      Counter-Strike 2 -> ["cs2", "cs"]
      Left 4 Dead 2    -> ["l4d2", "l4d"]

    Numeric-suffix removal is allowed only as a secondary alias and Core still
    requires that alias to resolve uniquely among installed games.
    """

    primary = derive_game_title_acronym(
        value
    )

    if not primary:
        return []

    aliases = [
        primary
    ]

    if re.search(
        r"\d+$",
        primary,
    ):
        without_suffix = re.sub(
            r"\d+$",
            "",
            primary,
        )

        if (
            len(
                without_suffix
            ) >= 2
            and without_suffix
            not in aliases
        ):
            aliases.append(
                without_suffix
            )

    return aliases



def _resolve_unique_acronym_match(
    query: str,
    installed: List[dict],
) -> Optional[dict]:
    query_norm = normalise_game_title(
        query
    ).replace(
        " ",
        "",
    )

    if (
        len(
            query_norm
        ) < 2
        or len(
            query_norm
        ) > 12
    ):
        return None

    matches = []

    for game in installed:
        aliases = derive_game_title_aliases(
            str(
                game.get(
                    "name"
                )
                or ""
            )
        )

        if query_norm in aliases:
            matches.append(
                game
            )

    if len(
        matches
    ) == 1:
        return {
            "status": "matched",
            "match": matches[
                0
            ],
            "score": 1.0,
            "match_type": "derived_acronym",
            "candidates": matches,
        }

    if len(
        matches
    ) > 1:
        return {
            "status": "ambiguous",
            "match": None,
            "score": 1.0,
            "match_type": "derived_acronym",
            "candidates": matches[
                :3
            ],
        }

    return None



def _selection_ordinal(
    value: str,
) -> Optional[int]:
    text = normalise_game_title(
        value
    )

    mapping = {
        "first": 0,
        "1st": 0,
        "second": 1,
        "2nd": 1,
        "third": 2,
        "3rd": 2,
    }

    for token, index in mapping.items():
        if re.search(
            rf"\b{re.escape(token)}\b",
            text,
        ):
            return index

    numeric = re.search(
        r"\b(?:number|option)?\s*([1-3])\b",
        text,
    )

    if numeric:
        return int(
            numeric.group(
                1
            )
        ) - 1

    return None


def resolve_steam_candidate_confirmation(
    user_text: str,
    candidates: List[dict],
) -> Optional[dict]:
    """
    Resolve a user's clarification against only the verified ambiguity set.

    This is deterministic Core state resolution; the language model does not
    choose which installed game the user meant.
    """

    raw = str(
        user_text
        or ""
    ).strip()

    candidate_list = [
        candidate
        for candidate in list(
            candidates
            or []
        )
        if isinstance(
            candidate,
            dict,
        )
        and str(
            candidate.get(
                "appid",
                "",
            )
            or ""
        ).strip().isdigit()
        and str(
            candidate.get(
                "name",
                "",
            )
            or ""
        ).strip()
    ]

    if (
        not raw
        or not candidate_list
    ):
        return None

    # A fresh unrelated explicit launch remains a new command unless its target
    # actually resolves to one of the pending candidates.
    cleaned = re.sub(
        r"^\s*(?:i\s+mean|i\s+meant|it's|its|the\s+game\s+is)\s+",
        "",
        raw,
        flags=re.IGNORECASE,
    ).strip()

    cleaned = re.sub(
        r"^\s*(?:open|launch|start|play)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    ordinal = _selection_ordinal(
        cleaned
    )

    if (
        ordinal is not None
        and 0 <= ordinal < len(
            candidate_list
        )
    ):
        return candidate_list[
            ordinal
        ]

    query_norm = normalise_game_title(
        cleaned
    )

    # Remove selector filler while retaining meaningful title words.
    query_tokens = [
        token
        for token in query_norm.split()
        if token
        not in {
            "the",
            "one",
            "game",
            "please",
            "yeah",
            "yep",
            "that",
            "this",
        }
    ]

    if not query_tokens:
        return None

    query_compact = " ".join(
        query_tokens
    )

    exact = [
        candidate
        for candidate in candidate_list
        if normalise_game_title(
            str(
                candidate.get(
                    "name",
                    "",
                )
                or ""
            )
        )
        == query_compact
    ]

    if len(
        exact
    ) == 1:
        return exact[
            0
        ]

    token_subset = []

    query_set = set(
        query_tokens
    )

    for candidate in candidate_list:
        name_norm = normalise_game_title(
            str(
                candidate.get(
                    "name",
                    "",
                )
                or ""
            )
        )

        name_tokens = set(
            name_norm.split()
        )

        if (
            query_set
            and query_set.issubset(
                name_tokens
            )
        ):
            token_subset.append(
                candidate
            )

    if len(
        token_subset
    ) == 1:
        return token_subset[
            0
        ]

    substring = [
        candidate
        for candidate in candidate_list
        if query_compact
        in normalise_game_title(
            str(
                candidate.get(
                    "name",
                    "",
                )
                or ""
            )
        )
    ]

    if len(
        substring
    ) == 1:
        return substring[
            0
        ]

    scored = []

    for candidate in candidate_list:
        name = str(
            candidate.get(
                "name",
                "",
            )
            or ""
        )

        score = _title_similarity(
            query_compact,
            name,
        )

        scored.append(
            (
                score,
                candidate,
            )
        )

    scored.sort(
        key=lambda item: item[
            0
        ],
        reverse=True,
    )

    if not scored:
        return None

    best_score, best = scored[
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

    if (
        best_score >= 0.82
        and (
            best_score
            - second_score
        ) >= 0.08
    ):
        return best

    return None



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
            "match_type": "exact",
            "candidates": exact,
        }

    acronym_resolution = (
        _resolve_unique_acronym_match(
            query=query,
            installed=installed,
        )
    )

    if acronym_resolution is not None:
        return acronym_resolution

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
