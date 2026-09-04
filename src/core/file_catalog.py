import os
import re
from pathlib import Path
from typing import Dict, List, Optional


MAX_QUERY_LENGTH = 240
MAX_RESULTS = 12
MAX_SCANNED_ENTRIES = 30000
MAX_DEPTH = 8

SAFE_OPEN_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".ppt",
    ".pptx",
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".log",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".xml",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".zip",
}

CODE_OR_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".log",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".xml",
}

NEVER_OPEN_EXTENSIONS = {
    ".exe",
    ".com",
    ".bat",
    ".cmd",
    ".ps1",
    ".psm1",
    ".vbs",
    ".vbe",
    ".jscript",
    ".scr",
    ".msi",
    ".msp",
    ".dll",
    ".sys",
    ".reg",
    ".lnk",
    ".url",
    ".pem",
    ".key",
    ".pfx",
    ".p12",
    ".kdbx",
}

PRUNED_DIRECTORY_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".idea",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

SENSITIVE_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials.json",
    "token.json",
    "secrets.json",
}

SENSITIVE_RELATIVE_PREFIXES = {
    "data/private",
    "data/google",
}

TRUSTED_FOLDER_ALIASES = {
    "documents": (
        "documents",
        "my documents",
        "documents folder",
    ),
    "desktop": (
        "desktop",
        "my desktop",
        "desktop folder",
    ),
    "pictures": (
        "pictures",
        "my pictures",
        "pictures folder",
        "photos folder",
    ),
    "screenshots": (
        "screenshots",
        "screenshots folder",
        "my screenshots",
    ),
}


def _normalise_text(
    value: str,
) -> str:
    text = str(
        value
        or ""
    ).strip().lower()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text


def _existing_directory(
    path: Path,
) -> Optional[Path]:
    try:
        resolved = path.expanduser().resolve()
    except Exception:
        return None

    if not resolved.is_dir():
        return None

    return resolved


def _dedupe_paths(
    values: List[Path],
) -> List[Path]:
    seen = set()
    result = []

    for path in values:
        try:
            key = str(
                path.resolve()
            ).lower()
        except Exception:
            continue

        if key in seen:
            continue

        seen.add(
            key
        )
        result.append(
            path
        )

    return result


def get_trusted_folder_paths() -> Dict[str, Path]:
    """
    Resolve stable user-facing folder aliases.

    Only folders that actually exist are returned.
    """

    home = Path.home()

    candidates = {
        "documents": home / "Documents",
        "desktop": home / "Desktop",
        "pictures": home / "Pictures",
        "screenshots": home / "Pictures" / "Screenshots",
    }

    result = {}

    for key, candidate in candidates.items():
        existing = _existing_directory(
            candidate
        )

        if existing is not None:
            result[
                key
            ] = existing

    return result


def get_approved_file_roots() -> List[Path]:
    """
    Return the filesystem roots Mairon may search for local files.

    Defaults:
      - Documents
      - Downloads
      - Desktop
      - Pictures
      - Mairon project

    Additional roots may be supplied explicitly through MAIRON_FILE_ROOTS,
    separated using the platform path separator (`;` on Windows).
    """

    home = Path.home()

    candidates = [
        home / "Documents",
        home / "Downloads",
        home / "Desktop",
        home / "Pictures",
    ]

    project_root = os.environ.get(
        "MAIRON_PROJECT_ROOT",
        r"C:\Projects\Mairon",
    )

    if project_root:
        candidates.append(
            Path(
                project_root
            )
        )

    extra = str(
        os.environ.get(
            "MAIRON_FILE_ROOTS",
            "",
        )
        or ""
    ).strip()

    if extra:
        for raw_path in extra.split(
            os.pathsep
        ):
            value = str(
                raw_path
                or ""
            ).strip()

            if value:
                candidates.append(
                    Path(
                        value
                    )
                )

    existing = []

    for candidate in candidates:
        path = _existing_directory(
            candidate
        )

        if path is not None:
            existing.append(
                path
            )

    return _dedupe_paths(
        existing
    )


def resolve_trusted_folder_alias(
    text: str,
) -> Optional[dict]:
    value = _normalise_text(
        text
    )

    paths = get_trusted_folder_paths()

    for folder_id, aliases in (
        TRUSTED_FOLDER_ALIASES.items()
    ):
        if folder_id not in paths:
            continue

        for alias in aliases:
            if value == _normalise_text(
                alias
            ):
                return {
                    "folder_id": folder_id,
                    "display_name": (
                        "Screenshots"
                        if folder_id == "screenshots"
                        else folder_id.title()
                    ),
                    "path": str(
                        paths[
                            folder_id
                        ]
                    ),
                }

    return None


def _path_within_root(
    path: Path,
    root: Path,
) -> bool:
    try:
        path.resolve().relative_to(
            root.resolve()
        )
        return True
    except Exception:
        return False


def is_path_within_approved_roots(
    path: Path,
    roots: Optional[List[Path]] = None,
) -> bool:
    roots = (
        roots
        if roots is not None
        else get_approved_file_roots()
    )

    return any(
        _path_within_root(
            path,
            root,
        )
        for root in roots
    )


def _relative_to_matching_root(
    path: Path,
    roots: List[Path],
) -> Optional[Path]:
    for root in roots:
        try:
            return path.resolve().relative_to(
                root.resolve()
            )
        except Exception:
            continue

    return None


def is_sensitive_local_path(
    path: Path,
    roots: Optional[List[Path]] = None,
) -> bool:
    roots = (
        roots
        if roots is not None
        else get_approved_file_roots()
    )

    name = path.name.lower()

    if name in SENSITIVE_FILE_NAMES:
        return True

    if path.suffix.lower() in NEVER_OPEN_EXTENSIONS:
        return True

    relative = _relative_to_matching_root(
        path,
        roots,
    )

    if relative is None:
        return True

    relative_text = str(
        relative
    ).replace(
        "\\",
        "/",
    ).lower()

    for prefix in SENSITIVE_RELATIVE_PREFIXES:
        if (
            relative_text == prefix
            or relative_text.startswith(
                prefix + "/"
            )
        ):
            return True

    return False


def is_safe_openable_file(
    path: Path,
    roots: Optional[List[Path]] = None,
) -> bool:
    roots = (
        roots
        if roots is not None
        else get_approved_file_roots()
    )

    try:
        resolved = path.resolve()
    except Exception:
        return False

    if not resolved.is_file():
        return False

    if not is_path_within_approved_roots(
        resolved,
        roots,
    ):
        return False

    if is_sensitive_local_path(
        resolved,
        roots,
    ):
        return False

    return (
        resolved.suffix.lower()
        in SAFE_OPEN_EXTENSIONS
    )


def _normalise_filename_for_match(
    value: str,
) -> str:
    text = str(
        value
        or ""
    ).strip().lower()

    text = re.sub(
        r"[_\-]+",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text


def _query_score(
    query: str,
    path: Path,
) -> int:
    q = _normalise_filename_for_match(
        query
    )

    filename = _normalise_filename_for_match(
        path.name
    )

    stem = _normalise_filename_for_match(
        path.stem
    )

    if not q:
        return 0

    if q == filename:
        return 100

    if q == stem:
        return 96

    if filename.startswith(
        q
    ):
        return 88

    if stem.startswith(
        q
    ):
        return 85

    query_tokens = {
        token
        for token in q.split()
        if token
    }

    target_tokens = {
        token
        for token in (
            filename
            + " "
            + stem
        ).split()
        if token
    }

    if (
        query_tokens
        and query_tokens.issubset(
            target_tokens
        )
    ):
        return 78

    if q in filename:
        return 68

    if q in stem:
        return 65

    return 0


def _should_prune_directory(
    directory_name: str,
) -> bool:
    value = str(
        directory_name
        or ""
    ).strip().lower()

    if not value:
        return True

    return (
        value in PRUNED_DIRECTORY_NAMES
        or value.startswith(
            "."
        )
    )


def search_local_files(
    query: str,
    roots: Optional[List[Path]] = None,
    max_results: int = MAX_RESULTS,
) -> List[dict]:
    """
    Search only approved roots and return deterministic ranked file matches.

    Search is filename/metadata based. File contents are not read.
    """

    query_value = str(
        query
        or ""
    ).strip()

    if (
        not query_value
        or len(
            query_value
        ) > MAX_QUERY_LENGTH
    ):
        return []

    roots = (
        roots
        if roots is not None
        else get_approved_file_roots()
    )

    roots = _dedupe_paths(
        [
            root
            for root in roots
            if root.is_dir()
        ]
    )

    matches = []
    scanned = 0

    for root in roots:
        root_parts = len(
            root.parts
        )

        for current_dir, dirnames, filenames in os.walk(
            root
        ):
            current = Path(
                current_dir
            )

            depth = (
                len(
                    current.parts
                )
                - root_parts
            )

            if depth >= MAX_DEPTH:
                dirnames[:] = []
            else:
                dirnames[:] = [
                    name
                    for name in dirnames
                    if not _should_prune_directory(
                        name
                    )
                ]

            for filename in filenames:
                scanned += 1

                if scanned > MAX_SCANNED_ENTRIES:
                    break

                path = current / filename

                if not is_safe_openable_file(
                    path,
                    roots,
                ):
                    continue

                score = _query_score(
                    query_value,
                    path,
                )

                if score <= 0:
                    continue

                try:
                    stat = path.stat()
                    modified = float(
                        stat.st_mtime
                    )
                except Exception:
                    modified = 0.0

                matches.append({
                    "path": str(
                        path.resolve()
                    ),
                    "name": path.name,
                    "extension": path.suffix.lower(),
                    "score": score,
                    "modified": modified,
                    "root": str(
                        root
                    ),
                })

            if scanned > MAX_SCANNED_ENTRIES:
                break

        if scanned > MAX_SCANNED_ENTRIES:
            break

    matches.sort(
        key=lambda item: (
            -int(
                item[
                    "score"
                ]
            ),
            -float(
                item[
                    "modified"
                ]
            ),
            str(
                item[
                    "name"
                ]
            ).lower(),
        )
    )

    return matches[
        :max(
            1,
            min(
                int(
                    max_results
                ),
                MAX_RESULTS,
            ),
        )
    ]


def _strip_possessive_file_prefix(
    value: str,
) -> str:
    text = str(
        value
        or ""
    ).strip()

    text = re.sub(
        r"^(?:my|the)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text.strip()


def _looks_file_specific(
    query: str,
) -> bool:
    value = _normalise_text(
        query
    )

    if not value:
        return False

    if re.search(
        r"\.[a-z0-9]{1,8}$",
        value,
        flags=re.IGNORECASE,
    ):
        return True

    return bool(
        re.search(
            r"\b(?:"
            r"file|document|doc|pdf|spreadsheet|sheet|presentation|slides|"
            r"image|photo|picture|screenshot|resume|cv|assignment|rubric|"
            r"report|essay|notes|code|script"
            r")\b",
            value,
            flags=re.IGNORECASE,
        )
    )


FIND_LOCAL_FILE_PATTERN = re.compile(
    r"^\s*(?:find|locate|look\s+for|search\s+(?:my\s+)?pc\s+for)\s+"
    r"(?P<query>.+?)\s*[.!?]*$",
    flags=re.IGNORECASE,
)

OPEN_LOCAL_FILE_PATTERN = re.compile(
    r"^\s*(?:open|show|view)\s+(?P<query>.+?)\s*[.!?]*$",
    flags=re.IGNORECASE,
)

OPEN_DEICTIC_FILE_PATTERN = re.compile(
    r"^\s*(?:open|show|view)\s+(?:it|that|this|the\s+file)\s*[.!?]*$",
    flags=re.IGNORECASE,
)


def extract_local_file_action_request(
    text: str,
    conversation_state=None,
) -> Optional[dict]:
    """
    Parse only clearly file/folder-oriented requests.

    Generic "open <noun>" is deliberately NOT treated as a file request,
    because it may be a desktop app or Steam game.
    """

    raw = str(
        text
        or ""
    ).strip()

    if not raw:
        return None

    open_match = OPEN_LOCAL_FILE_PATTERN.match(
        raw
    )

    if open_match:
        candidate = _strip_possessive_file_prefix(
            open_match.group(
                "query"
            )
        )

        folder = resolve_trusted_folder_alias(
            candidate
        )

        if folder is not None:
            return {
                "action": "open_folder",
                "query": candidate,
                "display_name": folder[
                    "display_name"
                ],
                "path": folder[
                    "path"
                ],
                "inherited": False,
            }

    if (
        OPEN_DEICTIC_FILE_PATTERN.match(
            raw
        )
        and conversation_state is not None
    ):
        active_intent = str(
            getattr(
                conversation_state,
                "active_intent",
                "",
            )
            or ""
        ).strip().lower()

        active_path = str(
            getattr(
                conversation_state,
                "active_local_file_path",
                "",
            )
            or ""
        ).strip()

        if (
            active_path
            and active_intent
            in {
                "find_local_file",
                "open_local_file",
            }
        ):
            return {
                "action": "open_file",
                "query": "",
                "path": active_path,
                "display_name": Path(
                    active_path
                ).name,
                "inherited": True,
            }

    find_match = FIND_LOCAL_FILE_PATTERN.match(
        raw
    )

    if find_match:
        query = _strip_possessive_file_prefix(
            find_match.group(
                "query"
            )
        )

        if query:
            return {
                "action": "find_file",
                "query": query,
                "inherited": False,
            }

    if open_match:
        query = _strip_possessive_file_prefix(
            open_match.group(
                "query"
            )
        )

        if _looks_file_specific(
            query
        ):
            return {
                "action": "open_file",
                "query": query,
                "path": None,
                "inherited": False,
            }

    return None
