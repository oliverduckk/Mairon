import re
from typing import Dict, Optional


DESKTOP_TARGETS: Dict[str, dict] = {
    "calculator": {
        "display_name": "Calculator",
        "aliases": ("calculator", "calc"),
        "kind": "application",
        "process_names": ("calculatorapp.exe", "calculator.exe"),
        "supports_close": True,
        "supports_focus": True,
        "close_behavior": "graceful_window",
    },
    "notepad": {
        "display_name": "Notepad",
        "aliases": ("notepad",),
        "kind": "application",
        "process_names": ("notepad.exe",),
        "supports_close": True,
        "supports_focus": True,
        "close_behavior": "graceful_window",
    },
    "chrome": {
        "display_name": "Chrome",
        "aliases": ("google chrome", "chrome"),
        "kind": "application",
        "process_names": ("chrome.exe",),
        "supports_close": True,
        "supports_focus": True,
        "close_behavior": "graceful_window",
    },
    "spotify": {
        "display_name": "Spotify",
        "aliases": ("spotify",),
        "kind": "application",
        "process_names": ("spotify.exe",),
        "supports_close": True,
        "supports_focus": True,
        "close_behavior": "graceful_window",
    },
    "discord": {
        "display_name": "Discord",
        "aliases": ("discord",),
        "kind": "application",
        "process_names": ("discord.exe",),
        "supports_close": True,
        "supports_focus": True,
        "close_behavior": "quit_process",
    },
    "lunar_client": {
        "display_name": "Lunar Client",
        "aliases": (
            "lunar client",
            "lunar launcher",
            "lunar",
        ),
        "kind": "application",
        "process_names": (
            "Lunar Client.exe",
        ),
        "supports_close": True,
        "supports_focus": True,
        "close_behavior": "quit_process",
    },
    "steam": {
        "display_name": "Steam",
        "aliases": ("steam",),
        "kind": "application",
        "process_names": ("steam.exe",),
        "supports_close": True,
        "supports_focus": True,
        "close_behavior": "graceful_window",
    },
    "vscode": {
        "display_name": "VS Code",
        "aliases": ("visual studio code", "vs code", "vscode"),
        "kind": "application",
        "process_names": ("code.exe",),
        "supports_close": True,
        "supports_focus": True,
        "close_behavior": "graceful_window",
    },
    "downloads": {
        "display_name": "Downloads",
        "aliases": (
            "downloads folder",
            "download folder",
            "my downloads",
            "downloads",
        ),
        "kind": "folder",
        "process_names": (),
        "supports_close": False,
        "supports_focus": False,
        "close_behavior": "unsupported",
    },
    "mairon_project": {
        "display_name": "Mairon project",
        "aliases": (
            "my mairon project",
            "the mairon project",
            "mairon project",
            "mairon in vs code",
        ),
        "kind": "project",
        "process_names": ("code.exe",),
        "supports_close": True,
        "supports_focus": True,
        "close_behavior": "graceful_window",
    },
}


OPEN_PATTERN = re.compile(
    r"\b(?:open|launch|start|run)(?:\s+up)?\b",
    flags=re.IGNORECASE,
)

CLOSE_PATTERN = re.compile(
    r"\b(?:close|quit|exit)\b",
    flags=re.IGNORECASE,
)

FOCUS_PATTERN = re.compile(
    r"(?:"
    r"\bfocus\b|"
    r"\bswitch\s+to\b|"
    r"\bbring\b.{0,80}\b(?:to\s+the\s+front|forward)\b"
    r")",
    flags=re.IGNORECASE,
)

DEICTIC_TARGET_PATTERN = re.compile(
    r"\b(?:it|that|this|the\s+app|the\s+window)\b",
    flags=re.IGNORECASE,
)

UNSUPPORTED_OPEN_COMPOUND_PATTERN = re.compile(
    r"\band\s+(?:search|look|find|go|navigate|type|play|queue|send|write)\b",
    flags=re.IGNORECASE,
)


def get_desktop_target(
    target_id: str,
) -> Optional[dict]:
    target_id = str(
        target_id
        or ""
    ).strip().lower()

    value = DESKTOP_TARGETS.get(
        target_id
    )

    if value is None:
        return None

    result = dict(
        value
    )

    result["target_id"] = target_id
    return result


def desktop_display_name(
    target_id: str,
) -> str:
    target = get_desktop_target(
        target_id
    )

    if target is None:
        return str(
            target_id
            or "that target"
        ).strip()

    return str(
        target.get(
            "display_name"
        )
        or target_id
    )


def _normalise(
    text: str,
) -> str:
    value = str(
        text
        or ""
    ).lower()

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def find_named_desktop_target(
    text: str,
) -> Optional[str]:
    value = _normalise(
        text
    )

    candidates = []

    for target_id, metadata in DESKTOP_TARGETS.items():
        for alias in metadata.get(
            "aliases",
            (),
        ):
            alias_value = _normalise(
                alias
            )

            candidates.append(
                (
                    len(alias_value),
                    alias_value,
                    target_id,
                )
            )

    for _, alias, target_id in sorted(
        candidates,
        reverse=True,
    ):
        if re.search(
            r"(?<![a-z0-9])"
            + re.escape(alias)
            + r"(?![a-z0-9])",
            value,
            flags=re.IGNORECASE,
        ):
            return target_id

    return None


def _active_desktop_target(
    conversation_state,
) -> Optional[str]:
    if conversation_state is None:
        return None

    value = str(
        getattr(
            conversation_state,
            "active_desktop_target",
            "",
        )
        or ""
    ).strip().lower()

    if value not in DESKTOP_TARGETS:
        return None

    return value


def extract_desktop_action_request(
    text: str,
    conversation_state=None,
) -> Optional[dict]:
    """
    Resolve one bounded Core-owned desktop action.

    Only allowlisted target IDs and open/close/focus are returned. User text
    never becomes executable text, a shell command, or an arbitrary path.
    """

    value = _normalise(
        text
    )

    if not value:
        return None

    action = None

    if FOCUS_PATTERN.search(value):
        action = "focus"
    elif CLOSE_PATTERN.search(value):
        action = "close"
    elif OPEN_PATTERN.search(value):
        action = "open"

    if action is None:
        return None

    # Never silently execute only half of a compound action.
    if (
        action == "open"
        and UNSUPPORTED_OPEN_COMPOUND_PATTERN.search(value)
    ):
        return None

    target_id = find_named_desktop_target(
        value
    )

    inherited = False

    if (
        target_id is None
        and DEICTIC_TARGET_PATTERN.search(value)
    ):
        target_id = _active_desktop_target(
            conversation_state
        )
        inherited = bool(
            target_id
        )

    if target_id is None:
        return None

    target = get_desktop_target(
        target_id
    )

    if target is None:
        return None

    if (
        action == "close"
        and not target.get("supports_close", False)
    ):
        return None

    if (
        action == "focus"
        and not target.get("supports_focus", False)
    ):
        return None

    return {
        "action": action,
        "target_id": target_id,
        "display_name": target["display_name"],
        "inherited": inherited,
    }
