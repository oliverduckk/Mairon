import ctypes
import os
import re
import threading
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional


MAX_QUERY_LENGTH = 240
MAX_RESULTS = 12
MAX_DEPTH = 10
FILE_INDEX_TTL_SECONDS = 300.0

_FILE_INDEX_LOCK = threading.Lock()
_FILE_INDEX_CACHE = {
    "root_key": None,
    "built_at": 0.0,
    "entries": [],
}

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

    # Common local video formats.
    ".mp4",
    ".m4v",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",

    # Common local audio formats.
    ".mp3",
    ".m4a",
    ".aac",
    ".wav",
    ".flac",
    ".ogg",
    ".opus",

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
    "env",
    ".env",
    "__pycache__",
    "node_modules",
    "site-packages",
    ".idea",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
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


WINDOWS_KNOWN_FOLDER_GUIDS = {
    "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
}


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid_from_string(
    value: str,
) -> _GUID:
    guid = _GUID()

    ole32 = ctypes.windll.ole32

    result = ole32.CLSIDFromString(
        ctypes.c_wchar_p(
            value
        ),
        ctypes.byref(
            guid
        ),
    )

    if result != 0:
        raise OSError(
            f"CLSIDFromString failed for {value}: {result}"
        )

    return guid


def _windows_known_folder_path(
    folder_id: str,
) -> Optional[Path]:
    """
    Resolve a Windows Known Folder to its real configured location.

    This follows redirected folders such as Pictures living on D:\\Pictures
    instead of assuming everything is under the user profile on C:.
    """

    if os.name != "nt":
        return None

    guid_text = WINDOWS_KNOWN_FOLDER_GUIDS.get(
        str(
            folder_id
            or ""
        ).strip().lower()
    )

    if not guid_text:
        return None

    try:
        guid = _guid_from_string(
            guid_text
        )

        path_ptr = ctypes.c_wchar_p()

        shell32 = ctypes.windll.shell32

        result = shell32.SHGetKnownFolderPath(
            ctypes.byref(
                guid
            ),
            0,
            None,
            ctypes.byref(
                path_ptr
            ),
        )

        if result != 0:
            return None

        try:
            raw_path = str(
                path_ptr.value
                or ""
            ).strip()

            if not raw_path:
                return None

            return _existing_directory(
                Path(
                    raw_path
                )
            )

        finally:
            ctypes.windll.ole32.CoTaskMemFree(
                path_ptr
            )

    except Exception:
        return None


def _fallback_known_folder_path(
    folder_id: str,
) -> Optional[Path]:
    home = Path.home()

    fallbacks = {
        "desktop": home / "Desktop",
        "documents": home / "Documents",
        "downloads": home / "Downloads",
        "pictures": home / "Pictures",
    }

    candidate = fallbacks.get(
        folder_id
    )

    if candidate is None:
        return None

    return _existing_directory(
        candidate
    )


def get_windows_personal_folder_paths() -> Dict[str, Path]:
    """
    Resolve only the personal folders Mairon is approved to index by default.

    Videos is intentionally excluded because media archives can be enormous
    and are not useful enough to justify indexing by default.
    """

    result = {}

    for folder_id in (
        "desktop",
        "documents",
        "downloads",
        "pictures",
    ):
        path = (
            _windows_known_folder_path(
                folder_id
            )
            or _fallback_known_folder_path(
                folder_id
            )
        )

        if path is not None:
            result[
                folder_id
            ] = path

    return result


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
    Resolve stable user-facing folder aliases from Windows' real configuration.

    Pictures may therefore resolve to D:\\Pictures when the user has redirected
    the Windows Known Folder there.
    """

    paths = get_windows_personal_folder_paths()

    result = {}

    for folder_id in (
        "documents",
        "desktop",
        "pictures",
    ):
        path = paths.get(
            folder_id
        )

        if path is not None:
            result[
                folder_id
            ] = path

    pictures = paths.get(
        "pictures"
    )

    if pictures is not None:
        screenshots = _existing_directory(
            pictures
            / "Screenshots"
        )

        if screenshots is not None:
            result[
                "screenshots"
            ] = screenshots

    return result

def get_approved_file_roots() -> List[Path]:
    """
    Return the filesystem roots Mairon may search for local files.

    Default personal roots come from Windows Known Folders:
      - Desktop
      - Documents
      - Downloads
      - Pictures

    Videos is intentionally NOT indexed by default.

    The Mairon project is also approved explicitly.

    Additional roots may be supplied through MAIRON_FILE_ROOTS, separated
    using the platform path separator (`;` on Windows).
    """

    personal = get_windows_personal_folder_paths()

    project_root = os.environ.get(
        "MAIRON_PROJECT_ROOT",
        r"C:\Projects\Mairon",
    )

    candidates = []

    # High-value explicit project root first.
    if project_root:
        candidates.append(
            Path(
                project_root
            )
        )

    # Personal file locations follow Windows' actual configured paths.
    for folder_id in (
        "desktop",
        "documents",
        "downloads",
        "pictures",
    ):
        path = personal.get(
            folder_id
        )

        if path is not None:
            candidates.append(
                path
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
    """
    Resolve only the semantic trusted-folder identity.

    Core must not resolve the actual Windows Known Folder path. The Windows
    Desktop Agent owns that platform-specific lookup and validates the folder
    again immediately before execution.
    """

    value = _normalise_text(
        text
    )

    for folder_id, aliases in (
        TRUSTED_FOLDER_ALIASES.items()
    ):
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

    query_tokens = [
        token
        for token in q.split()
        if token
    ]

    target_tokens = [
        token
        for token in (
            filename
            + " "
            + stem
        ).split()
        if token
    ]

    query_token_set = set(
        query_tokens
    )

    target_token_set = set(
        target_tokens
    )

    if (
        query_token_set
        and query_token_set.issubset(
            target_token_set
        )
    ):
        return 78

    if q in filename:
        return 68

    if q in stem:
        return 65

    # Conservative typo tolerance.
    #
    # Only enable it for reasonably descriptive queries. Short generic terms
    # such as "pdf", "file" or "doc" must never fuzzily match arbitrary files.
    if (
        len(
            q
        ) >= 8
        and len(
            query_tokens
        ) >= 2
    ):
        stem_ratio = SequenceMatcher(
            None,
            q,
            stem,
        ).ratio()

        filename_ratio = SequenceMatcher(
            None,
            q,
            filename,
        ).ratio()

        ratio = max(
            stem_ratio,
            filename_ratio,
        )

        if ratio >= 0.90:
            return 60

        # Token-by-token typo support for phrases such as
        # "feasability report" -> "feasibility report".
        unmatched = []

        for query_token in query_tokens:
            if query_token in target_token_set:
                continue

            if len(
                query_token
            ) < 5:
                unmatched.append(
                    query_token
                )
                continue

            best = 0.0

            for target_token in target_tokens:
                best = max(
                    best,
                    SequenceMatcher(
                        None,
                        query_token,
                        target_token,
                    ).ratio(),
                )

            if best < 0.84:
                unmatched.append(
                    query_token
                )

        if not unmatched:
            return 58

    return 0

def _should_prune_directory(
    directory_name: str,
    parent: Optional[Path] = None,
) -> bool:
    value = str(
        directory_name
        or ""
    ).strip().lower()

    if not value:
        return True

    if (
        value in PRUNED_DIRECTORY_NAMES
        or value.startswith(
            "."
        )
    ):
        return True

    if parent is not None:
        candidate = parent / directory_name

        try:
            if (
                candidate.is_dir()
                and (
                    candidate
                    / "pyvenv.cfg"
                ).is_file()
            ):
                return True
        except Exception:
            pass

    return False


def _root_cache_key(
    roots: List[Path],
) -> tuple:
    values = []

    for root in roots:
        try:
            values.append(
                str(
                    root.resolve()
                ).lower()
            )
        except Exception:
            values.append(
                str(
                    root
                ).lower()
            )

    return tuple(
        values
    )


def _build_file_index(
    roots: List[Path],
) -> List[dict]:
    """
    Build a lightweight session-local filename index.

    Expensive resolve/stat/safety validation is deferred until a filename
    actually matches a user query.
    """

    entries = []

    for root_index, root in enumerate(
        roots
    ):
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
                        name,
                        parent=current,
                    )
                ]

            for filename in filenames:
                extension = Path(
                    filename
                ).suffix.lower()

                if extension not in SAFE_OPEN_EXTENSIONS:
                    continue

                if filename.lower() in SENSITIVE_FILE_NAMES:
                    continue

                entries.append({
                    "path": str(
                        current
                        / filename
                    ),
                    "name": filename,
                    "extension": extension,
                    "root": str(
                        root
                    ),
                    "root_priority": root_index,
                    "depth": depth,
                })

    return entries



def _file_index_cache_is_current(
    roots: List[Path],
) -> bool:
    root_key = _root_cache_key(
        roots
    )

    now = time.monotonic()

    with _FILE_INDEX_LOCK:
        return (
            _FILE_INDEX_CACHE[
                "root_key"
            ] == root_key
            and (
                now
                - float(
                    _FILE_INDEX_CACHE[
                        "built_at"
                    ]
                )
            ) < FILE_INDEX_TTL_SECONDS
        )


def _get_file_index(
    roots: List[Path],
    force_refresh: bool = False,
) -> List[dict]:
    root_key = _root_cache_key(
        roots
    )

    now = time.monotonic()

    with _FILE_INDEX_LOCK:
        cache_valid = (
            not force_refresh
            and _FILE_INDEX_CACHE[
                "root_key"
            ] == root_key
            and (
                now
                - float(
                    _FILE_INDEX_CACHE[
                        "built_at"
                    ]
                )
            ) < FILE_INDEX_TTL_SECONDS
        )

        if cache_valid:
            return list(
                _FILE_INDEX_CACHE[
                    "entries"
                ]
            )

        entries = _build_file_index(
            roots
        )

        _FILE_INDEX_CACHE[
            "root_key"
        ] = root_key
        _FILE_INDEX_CACHE[
            "built_at"
        ] = time.monotonic()
        _FILE_INDEX_CACHE[
            "entries"
        ] = entries

        return list(
            entries
        )


def clear_file_index_cache() -> None:
    with _FILE_INDEX_LOCK:
        _FILE_INDEX_CACHE[
            "root_key"
        ] = None
        _FILE_INDEX_CACHE[
            "built_at"
        ] = 0.0
        _FILE_INDEX_CACHE[
            "entries"
        ] = []


def _search_index_entries(
    query_value: str,
    roots: List[Path],
    entries: List[dict],
    max_results: int,
) -> List[dict]:
    matches = []

    for entry in entries:
        path = Path(
            entry[
                "path"
            ]
        )

        score = _query_score(
            query_value,
            path,
        )

        if score <= 0:
            continue

        if not is_safe_openable_file(
            path,
            roots,
        ):
            continue

        try:
            resolved = path.resolve()
            stat = resolved.stat()
            modified = float(
                stat.st_mtime
            )
        except Exception:
            continue

        match = dict(
            entry
        )

        match[
            "path"
        ] = str(
            resolved
        )
        match[
            "score"
        ] = score
        match[
            "modified"
        ] = modified

        matches.append(
            match
        )

    matches.sort(
        key=lambda item: (
            -int(
                item[
                    "score"
                ]
            ),
            int(
                item.get(
                    "root_priority",
                    999,
                )
            ),
            int(
                item.get(
                    "depth",
                    999,
                )
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


def search_local_files(
    query: str,
    roots: Optional[List[Path]] = None,
    max_results: int = MAX_RESULTS,
) -> List[dict]:
    """
    Search approved roots using a lightweight session-local filename index.

    Matched files are revalidated against approved roots at query time.
    A cached miss triggers one immediate index refresh before "not found".
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

    had_current_cache = _file_index_cache_is_current(
        roots
    )

    entries = _get_file_index(
        roots
    )

    matches = _search_index_entries(
        query_value=query_value,
        roots=roots,
        entries=entries,
        max_results=max_results,
    )

    if matches:
        return matches

    # Only refresh on a miss when we actually searched an older cached index.
    # A first-ever miss has just built a fresh index, so scanning twice would
    # waste time without improving accuracy.
    if not had_current_cache:
        return []

    refreshed_entries = _get_file_index(
        roots,
        force_refresh=True,
    )

    return _search_index_entries(
        query_value=query_value,
        roots=roots,
        entries=refreshed_entries,
        max_results=max_results,
    )

def _strip_possessive_file_prefix(
    value: str,
) -> str:
    text = str(
        value
        or ""
    ).strip()

    # Remove conversational wrappers while preserving the actual filename
    # description.
    patterns = [
        r"^(?:my|the)\s+file\s+(?:named|called)\s+",
        r"^(?:my|the)\s+(?:document|doc)\s+(?:named|called)\s+",
        r"^(?:a|the)\s+file\s+(?:named|called)\s+",
        r"^(?:a|the)\s+(?:document|doc)\s+(?:named|called)\s+",
        r"^file\s+(?:named|called)\s+",
        r"^(?:document|doc)\s+(?:named|called)\s+",
        r"^(?:my|the)\s+",
    ]

    for pattern in patterns:
        updated = re.sub(
            pattern,
            "",
            text,
            count=1,
            flags=re.IGNORECASE,
        )

        if updated != text:
            text = updated
            break

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



def _ordinal_index(
    value: str,
) -> Optional[int]:
    text = _normalise_text(
        value
    )

    # Explicit ordinals take precedence over generic number words.
    ordinal_mapping = {
        "first": 0,
        "1st": 0,
        "second": 1,
        "2nd": 1,
        "third": 2,
        "3rd": 2,
        "fourth": 3,
        "4th": 3,
        "fifth": 4,
        "5th": 4,
    }

    for token, index in ordinal_mapping.items():
        if re.search(
            rf"\b{re.escape(token)}\b",
            text,
        ):
            return index

    numeric = re.search(
        r"\b(?:number\s*)?([1-9]|1[0-2])\b",
        text,
    )

    if numeric:
        return int(
            numeric.group(
                1
            )
        ) - 1

    # Cardinal words are accepted only when they are the actual selector,
    # not merely the noun in phrases such as "the second one".
    cardinal_mapping = {
        "one": 0,
        "two": 1,
        "three": 2,
        "four": 3,
        "five": 4,
    }

    selector_match = re.search(
        r"\b(?:number\s+|option\s+)?"
        r"(one|two|three|four|five)\b",
        text,
    )

    if selector_match:
        return cardinal_mapping.get(
            selector_match.group(
                1
            )
        )

    return None

def _candidate_extension(
    candidate: dict,
) -> str:
    extension = str(
        candidate.get(
            "extension",
            "",
        )
        or ""
    ).lower()

    if extension:
        return extension

    return Path(
        str(
            candidate.get(
                "path",
                "",
            )
            or ""
        )
    ).suffix.lower()


def _candidate_filter_by_extension(
    candidates: List[dict],
    text: str,
) -> List[dict]:
    value = _normalise_text(
        text
    )

    extension_terms = {
        ".pdf": (
            "pdf",
        ),
        ".docx": (
            "docx",
            "word",
            "word document",
        ),
        ".doc": (
            "doc",
            "word",
            "word document",
        ),
        ".xlsx": (
            "xlsx",
            "excel",
            "spreadsheet",
        ),
        ".xls": (
            "xls",
            "excel",
            "spreadsheet",
        ),
        ".pptx": (
            "pptx",
            "powerpoint",
            "slides",
            "presentation",
        ),
        ".ppt": (
            "ppt",
            "powerpoint",
            "slides",
            "presentation",
        ),
    }

    requested = set()

    for extension, terms in extension_terms.items():
        for term in terms:
            if re.search(
                rf"\b{re.escape(term)}\b",
                value,
            ):
                requested.add(
                    extension
                )

    if not requested:
        return list(
            candidates
        )

    return [
        candidate
        for candidate in candidates
        if _candidate_extension(
            candidate
        )
        in requested
    ]


def _candidate_name_score(
    text: str,
    candidate: dict,
) -> float:
    query = _normalise_filename_for_match(
        text
    )

    name = _normalise_filename_for_match(
        str(
            candidate.get(
                "name",
                "",
            )
            or ""
        )
    )

    stem = _normalise_filename_for_match(
        Path(
            str(
                candidate.get(
                    "name",
                    "",
                )
                or ""
            )
        ).stem
    )

    if not query:
        return 0.0

    if query == name:
        return 1.0

    if query == stem:
        return 0.99

    if query in name:
        return 0.95

    query_tokens = {
        token
        for token in query.split()
        if token
        not in {
            "my",
            "the",
            "file",
            "document",
            "open",
            "show",
            "view",
        }
    }

    target_tokens = set(
        name.split()
    )

    if (
        query_tokens
        and query_tokens.issubset(
            target_tokens
        )
    ):
        return 0.93

    return SequenceMatcher(
        None,
        query,
        name,
    ).ratio()


def resolve_active_file_candidate_request(
    text: str,
    conversation_state=None,
) -> Optional[dict]:
    if conversation_state is None:
        return None

    candidates = list(
        getattr(
            conversation_state,
            "active_local_file_candidates",
            [],
        )
        or []
    )

    if not candidates:
        return None

    raw = str(
        text
        or ""
    ).strip()

    value = _normalise_text(
        raw
    )

    if not value:
        return None

    if re.match(
        r"^\s*(?:open|show|view)\s+"
        r"(?:it|that|this|the\s+file)\s*[.!?]*$",
        raw,
        flags=re.IGNORECASE,
    ):
        return {
            "action": "candidate_choice_required",
            "inherited": True,
        }

    pending_action = str(
        getattr(
            conversation_state,
            "active_local_file_pending_action",
            "",
        )
        or ""
    ).strip().lower()

    explicit_open = bool(
        re.match(
            r"^\s*(?:open|show|view)\b",
            raw,
            flags=re.IGNORECASE,
        )
    )

    wants_both = bool(
        re.search(
            r"\b(?:both|all)\b",
            value,
        )
    )

    if (
        wants_both
        and (
            explicit_open
            or re.search(
                r"\bfiles?\b",
                value,
            )
        )
    ):
        return {
            "action": "open_files",
            "paths": [
                str(
                    candidate.get(
                        "path",
                        "",
                    )
                    or ""
                )
                for candidate in candidates
                if candidate.get(
                    "path"
                )
            ],
            "display_names": [
                str(
                    candidate.get(
                        "name",
                        "",
                    )
                    or ""
                )
                for candidate in candidates
            ],
            "inherited": True,
        }

    ordinal = _ordinal_index(
        value
    )

    filtered = _candidate_filter_by_extension(
        candidates,
        value,
    )

    if ordinal is not None:
        source = (
            filtered
            if filtered
            else candidates
        )

        if 0 <= ordinal < len(
            source
        ):
            selected = source[
                ordinal
            ]

            should_open = (
                explicit_open
                or pending_action == "open"
            )

            return {
                "action": (
                    "open_file"
                    if should_open
                    else "select_file"
                ),
                "path": selected[
                    "path"
                ],
                "display_name": selected.get(
                    "name"
                ),
                "query": "",
                "inherited": True,
            }

    if len(
        filtered
    ) == 1:
        selected = filtered[
            0
        ]

        should_open = (
            explicit_open
            or pending_action == "open"
        )

        return {
            "action": (
                "open_file"
                if should_open
                else "select_file"
            ),
            "path": selected[
                "path"
            ],
            "display_name": selected.get(
                "name"
            ),
            "query": "",
            "inherited": True,
        }

    scored = sorted(
        [
            (
                _candidate_name_score(
                    raw,
                    candidate,
                ),
                candidate,
            )
            for candidate in candidates
        ],
        key=lambda item: -item[
            0
        ],
    )

    if scored:
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
            best_score >= 0.93
            and (
                best_score
                - second_score
            ) >= 0.03
        ):
            should_open = (
                explicit_open
                or pending_action == "open"
            )

            return {
                "action": (
                    "open_file"
                    if should_open
                    else "select_file"
                ),
                "path": best[
                    "path"
                ],
                "display_name": best.get(
                    "name"
                ),
                "query": "",
                "inherited": True,
            }

    return None


FIND_AND_OPEN_LOCAL_FILE_PATTERN = re.compile(
    r"^\s*(?:find|locate|look\s+for)\s+"
    r"(?P<query>.+?)\s+"
    r"(?:and|then)\s+"
    r"(?:open|show|view)\s+"
    r"(?:it|that|the\s+file)\s*[.!?]*$",
    flags=re.IGNORECASE,
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

    compound_match = (
        FIND_AND_OPEN_LOCAL_FILE_PATTERN.match(
            raw
        )
    )

    if compound_match:
        query = _strip_possessive_file_prefix(
            compound_match.group(
                "query"
            )
        )

        if query:
            return {
                "action": "open_file",
                "query": query,
                "path": None,
                "inherited": False,
            }

    candidate_request = (
        resolve_active_file_candidate_request(
            raw,
            conversation_state=(
                conversation_state
            ),
        )
    )

    if candidate_request is not None:
        return candidate_request

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
                "folder_id": folder[
                    "folder_id"
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
                "select_local_file",
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
