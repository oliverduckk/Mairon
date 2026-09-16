import hmac
import json
import os
import re
import secrets
from pathlib import Path
from typing import Any, Dict, Optional


PROTOCOL_VERSION = "1"
DEFAULT_AGENT_HOST = "127.0.0.1"
DEFAULT_AGENT_PORT = 8765
MAX_REQUEST_BYTES = 64 * 1024

TOKEN_HEADER = "X-Mairon-Agent-Token"

NODE_DESCRIPTOR_VERSION = "1"
DEFAULT_DESKTOP_NODE_ID = "windows_desktop"
DESKTOP_NODE_TYPE = "desktop"
DESKTOP_NODE_PLATFORM = "windows"
DESKTOP_NODE_TRANSPORT_SCOPE = "localhost_only"

DESKTOP_CAPABILITY_ACTIONS = {
    "application_control": {
        "launch_application",
        "close_application",
        "focus_application",
    },
    "trusted_browser": {
        "open_trusted_browser_site",
    },
    "approved_local_files": {
        "search_approved_local_files",
        "open_approved_local_path",
        "open_trusted_folder",
    },
    "steam_library": {
        "list_installed_steam_games",
        "launch_steam_game_appid",
    },
}

KNOWN_DESKTOP_CAPABILITIES = frozenset(
    DESKTOP_CAPABILITY_ACTIONS.keys()
)

_NODE_ID_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9_.-]{0,63}$"
)

ALLOWED_ACTIONS = {
    "ping",
    "describe_node",
    "launch_application",
    "close_application",
    "focus_application",
    "open_trusted_browser_site",
    "search_approved_local_files",
    "open_approved_local_path",
    "list_installed_steam_games",
    "launch_steam_game_appid",
    "open_trusted_folder",
}


def get_desktop_node_id() -> str:
    """
    Resolve the stable logical identity of this Windows capability node.

    Phase 10.10.1 still uses localhost-only transport, but Core no longer
    needs to equate "the desktop" with one hard-coded socket endpoint.
    """

    value = str(
        os.environ.get(
            "MAIRON_DESKTOP_NODE_ID",
            DEFAULT_DESKTOP_NODE_ID,
        )
        or ""
    ).strip().lower()

    if not value:
        value = DEFAULT_DESKTOP_NODE_ID

    if not _NODE_ID_PATTERN.fullmatch(
        value
    ):
        raise ValueError(
            "MAIRON_DESKTOP_NODE_ID must use 1-64 lowercase letters, "
            "numbers, dots, underscores, or hyphens."
        )

    return value


def build_desktop_node_descriptor(
    node_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build the safe authenticated capability descriptor returned to Core.

    The descriptor intentionally contains no secrets, filesystem paths,
    executable paths, shell authority, private user data, or model state.
    """

    resolved_node_id = (
        str(
            node_id
            or ""
        ).strip().lower()
        or get_desktop_node_id()
    )

    if not _NODE_ID_PATTERN.fullmatch(
        resolved_node_id
    ):
        raise ValueError(
            "Desktop node_id is invalid."
        )

    return {
        "schema_version": NODE_DESCRIPTOR_VERSION,
        "node_id": resolved_node_id,
        "node_type": DESKTOP_NODE_TYPE,
        "platform": DESKTOP_NODE_PLATFORM,
        "protocol_version": PROTOCOL_VERSION,
        "transport_scope": DESKTOP_NODE_TRANSPORT_SCOPE,
        "available": True,
        "status": "online",
        "capabilities": list(
            DESKTOP_CAPABILITY_ACTIONS.keys()
        ),
        "power": {
            # Wake-on-LAN is intentionally NOT enabled merely because the
            # future architecture may use it. Capability must be truthful.
            "wake_supported": False,
        },
    }


def normalise_node_descriptor(
    payload: Any,
) -> Dict[str, Any]:
    """
    Validate an Agent-supplied node descriptor before Core trusts it.

    Phase 10.10.1 accepts only the current localhost Windows node contract.
    Future remote/Pi transport can version this boundary rather than silently
    broadening today's trust assumptions.
    """

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "Desktop node descriptor must be a JSON object."
        )

    schema_version = str(
        payload.get(
            "schema_version",
            "",
        )
        or ""
    ).strip()

    if schema_version != NODE_DESCRIPTOR_VERSION:
        raise ValueError(
            "Unsupported desktop node descriptor version."
        )

    node_id = str(
        payload.get(
            "node_id",
            "",
        )
        or ""
    ).strip().lower()

    if not _NODE_ID_PATTERN.fullmatch(
        node_id
    ):
        raise ValueError(
            "Desktop node descriptor has an invalid node_id."
        )

    node_type = str(
        payload.get(
            "node_type",
            "",
        )
        or ""
    ).strip().lower()

    if node_type != DESKTOP_NODE_TYPE:
        raise ValueError(
            "Desktop node descriptor has an unsupported node_type."
        )

    platform = str(
        payload.get(
            "platform",
            "",
        )
        or ""
    ).strip().lower()

    if platform != DESKTOP_NODE_PLATFORM:
        raise ValueError(
            "Desktop node descriptor has an unsupported platform."
        )

    protocol_version = str(
        payload.get(
            "protocol_version",
            "",
        )
        or ""
    ).strip()

    if protocol_version != PROTOCOL_VERSION:
        raise ValueError(
            "Desktop node descriptor protocol version does not match Core."
        )

    transport_scope = str(
        payload.get(
            "transport_scope",
            "",
        )
        or ""
    ).strip().lower()

    if transport_scope != DESKTOP_NODE_TRANSPORT_SCOPE:
        raise ValueError(
            "Desktop node descriptor attempted an unsupported transport scope."
        )

    if payload.get(
        "available"
    ) is not True:
        raise ValueError(
            "Desktop node descriptor did not report the node online."
        )

    status = str(
        payload.get(
            "status",
            "",
        )
        or ""
    ).strip().lower()

    if status != "online":
        raise ValueError(
            "Desktop node descriptor has an invalid availability status."
        )

    capabilities_raw = payload.get(
        "capabilities"
    )

    if not isinstance(
        capabilities_raw,
        list,
    ):
        raise ValueError(
            "Desktop node capabilities must be a list."
        )

    capabilities = []

    for item in capabilities_raw:
        capability = str(
            item
            or ""
        ).strip().lower()

        if (
            not capability
            or capability not in KNOWN_DESKTOP_CAPABILITIES
        ):
            raise ValueError(
                "Desktop node advertised an unknown capability."
            )

        if capability not in capabilities:
            capabilities.append(
                capability
            )

    power = payload.get(
        "power"
    )

    if not isinstance(
        power,
        dict,
    ):
        raise ValueError(
            "Desktop node power metadata must be an object."
        )

    wake_supported = power.get(
        "wake_supported"
    )

    if not isinstance(
        wake_supported,
        bool,
    ):
        raise ValueError(
            "Desktop node wake_supported must be boolean."
        )

    return {
        "schema_version": NODE_DESCRIPTOR_VERSION,
        "node_id": node_id,
        "node_type": DESKTOP_NODE_TYPE,
        "platform": DESKTOP_NODE_PLATFORM,
        "protocol_version": PROTOCOL_VERSION,
        "transport_scope": DESKTOP_NODE_TRANSPORT_SCOPE,
        "available": True,
        "status": "online",
        "capabilities": capabilities,
        "power": {
            "wake_supported": wake_supported,
        },
    }


def required_capability_for_action(
    action: str,
) -> Optional[str]:
    """
    Return the capability Core must see before dispatching one action.

    Control-plane actions are authenticated but do not require a workload
    capability.
    """

    action_value = str(
        action
        or ""
    ).strip().lower()

    if action_value in {
        "ping",
        "describe_node",
    }:
        return None

    for (
        capability,
        actions,
    ) in DESKTOP_CAPABILITY_ACTIONS.items():
        if action_value in actions:
            return capability

    return None


def node_supports_action(
    node_descriptor: Any,
    action: str,
) -> bool:
    """
    Fail-closed capability check for Core-side dispatch decisions.
    """

    action_value = str(
        action
        or ""
    ).strip().lower()

    if action_value not in ALLOWED_ACTIONS:
        return False

    try:
        node = normalise_node_descriptor(
            node_descriptor
        )

    except ValueError:
        return False

    if action_value in {
        "ping",
        "describe_node",
    }:
        return True

    capability = required_capability_for_action(
        action_value
    )

    if not capability:
        return False

    return capability in set(
        node.get(
            "capabilities",
            [],
        )
    )


def get_agent_secret_path() -> Path:
    explicit = str(
        os.environ.get(
            "MAIRON_DESKTOP_AGENT_SECRET_PATH",
            "",
        )
        or ""
    ).strip()

    if explicit:
        return Path(
            explicit
        ).expanduser()

    project_root = str(
        os.environ.get(
            "MAIRON_PROJECT_ROOT",
            r"C:\Projects\Mairon",
        )
        or ""
    ).strip()

    return (
        Path(
            project_root
        )
        / "data"
        / "private"
        / "desktop_agent_secret.txt"
    )


def load_or_create_agent_secret() -> str:
    """
    Load the local desktop-agent pairing secret, creating it on first use.

    The secret lives under data/private by default and therefore stays outside
    source control. It is never accepted from model-generated text.
    """

    path = get_agent_secret_path()

    if path.is_file():
        value = path.read_text(
            encoding="utf-8",
        ).strip()

        if len(
            value
        ) >= 32:
            return value

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    value = secrets.token_urlsafe(
        48
    )

    path.write_text(
        value + "\n",
        encoding="utf-8",
    )

    try:
        os.chmod(
            path,
            0o600,
        )
    except Exception:
        # Windows ACLs are not controlled by chmod in the same way as POSIX.
        # The important boundary remains the private data directory + token.
        pass

    return value


def secrets_match(
    supplied: str,
    expected: str,
) -> bool:
    supplied_value = str(
        supplied
        or ""
    )

    expected_value = str(
        expected
        or ""
    )

    if (
        not supplied_value
        or not expected_value
    ):
        return False

    return hmac.compare_digest(
        supplied_value,
        expected_value,
    )


def build_request(
    request_id: str,
    action: str,
    args: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "version": PROTOCOL_VERSION,
        "request_id": str(
            request_id
            or ""
        ).strip(),
        "action": str(
            action
            or ""
        ).strip(),
        "args": dict(
            args
            or {}
        ),
    }


def validate_request(
    payload: Any,
) -> Dict[str, Any]:
    """
    Validate one Core -> Desktop Agent request.

    Validation is deliberately structural and allowlist-based. There is no
    arbitrary command, executable path, shell string, or function-name field.
    """

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "Request body must be a JSON object."
        )

    version = str(
        payload.get(
            "version",
            "",
        )
        or ""
    ).strip()

    if version != PROTOCOL_VERSION:
        raise ValueError(
            "Unsupported desktop-agent protocol version."
        )

    request_id = str(
        payload.get(
            "request_id",
            "",
        )
        or ""
    ).strip()

    if (
        not request_id
        or len(
            request_id
        ) > 128
    ):
        raise ValueError(
            "request_id is required and must be at most 128 characters."
        )

    action = str(
        payload.get(
            "action",
            "",
        )
        or ""
    ).strip().lower()

    if action not in ALLOWED_ACTIONS:
        raise ValueError(
            "That desktop-agent action is not approved."
        )

    args = payload.get(
        "args",
        {},
    )

    if not isinstance(
        args,
        dict,
    ):
        raise ValueError(
            "args must be a JSON object."
        )

    if action in {
        "ping",
        "describe_node",
    }:
        if args:
            raise ValueError(
                f"{action} does not accept arguments."
            )

    elif action == "open_trusted_folder":
        allowed_keys = {
            "folder_id",
        }

        unknown = set(
            args.keys()
        ) - allowed_keys

        if unknown:
            raise ValueError(
                "open_trusted_folder received unsupported arguments."
            )

        folder_id = str(
            args.get(
                "folder_id",
                "",
            )
            or ""
        ).strip().lower()

        if folder_id not in {
            "desktop",
            "documents",
            "pictures",
            "screenshots",
        }:
            raise ValueError(
                "open_trusted_folder requires an approved folder_id."
            )

        args = {
            "folder_id": folder_id,
        }

    elif action == "list_installed_steam_games":
        if args:
            raise ValueError(
                "list_installed_steam_games does not accept arguments."
            )

    elif action == "launch_steam_game_appid":
        allowed_keys = {
            "appid",
        }

        unknown = set(
            args.keys()
        ) - allowed_keys

        if unknown:
            raise ValueError(
                "launch_steam_game_appid received unsupported arguments."
            )

        appid = str(
            args.get(
                "appid",
                "",
            )
            or ""
        ).strip()

        if (
            not appid
            or not appid.isdigit()
            or len(
                appid
            ) > 20
        ):
            raise ValueError(
                "launch_steam_game_appid requires a numeric AppID."
            )

        args = {
            "appid": appid,
        }

    elif action == "search_approved_local_files":
        allowed_keys = {
            "query",
        }

        unknown = set(
            args.keys()
        ) - allowed_keys

        if unknown:
            raise ValueError(
                "search_approved_local_files received unsupported arguments."
            )

        query = str(
            args.get(
                "query",
                "",
            )
            or ""
        ).strip()

        if (
            not query
            or len(
                query
            ) > 240
        ):
            raise ValueError(
                "search_approved_local_files requires a valid query."
            )

        args = {
            "query": query,
        }

    elif action == "open_approved_local_path":
        allowed_keys = {
            "path",
        }

        unknown = set(
            args.keys()
        ) - allowed_keys

        if unknown:
            raise ValueError(
                "open_approved_local_path received unsupported arguments."
            )

        path = str(
            args.get(
                "path",
                "",
            )
            or ""
        ).strip()

        if (
            not path
            or len(
                path
            ) > 4096
        ):
            raise ValueError(
                "open_approved_local_path requires a valid path."
            )

        args = {
            "path": path,
        }

    elif action == "open_trusted_browser_site":
        allowed_keys = {
            "site_id",
            "query",
        }

        unknown = set(
            args.keys()
        ) - allowed_keys

        if unknown:
            raise ValueError(
                "open_trusted_browser_site received unsupported arguments."
            )

        site_id = str(
            args.get(
                "site_id",
                "",
            )
            or ""
        ).strip().lower()

        if (
            not site_id
            or len(
                site_id
            ) > 64
        ):
            raise ValueError(
                "open_trusted_browser_site requires a valid site_id."
            )

        query = args.get(
            "query"
        )

        if query is not None:
            query = str(
                query
                or ""
            ).strip()

            if (
                not query
                or len(
                    query
                ) > 500
            ):
                raise ValueError(
                    "open_trusted_browser_site query is empty or too long."
                )

        args = {
            "site_id": site_id,
            "query": query,
        }

    elif action in {
        "launch_application",
        "close_application",
        "focus_application",
    }:
        allowed_keys = {
            "app_name",
        }

        unknown = set(
            args.keys()
        ) - allowed_keys

        if unknown:
            raise ValueError(
                f"{action} received unsupported arguments."
            )

        app_name = str(
            args.get(
                "app_name",
                "",
            )
            or ""
        ).strip().lower()

        if (
            not app_name
            or len(
                app_name
            ) > 80
        ):
            raise ValueError(
                f"{action} requires a valid app_name."
            )

        args = {
            "app_name": app_name,
        }

    return {
        "version": PROTOCOL_VERSION,
        "request_id": request_id,
        "action": action,
        "args": args,
    }


def success_response(
    request_id: str,
    result: Any,
) -> Dict[str, Any]:
    return {
        "version": PROTOCOL_VERSION,
        "request_id": str(
            request_id
            or ""
        ),
        "success": True,
        "result": result,
        "error": None,
    }


def error_response(
    request_id: str,
    code: str,
    message: str,
) -> Dict[str, Any]:
    return {
        "version": PROTOCOL_VERSION,
        "request_id": str(
            request_id
            or ""
        ),
        "success": False,
        "result": None,
        "error": {
            "code": str(
                code
                or "desktop_agent_error"
            ),
            "message": str(
                message
                or "Desktop agent request failed."
            ),
        },
    }


def encode_json(
    payload: Dict[str, Any],
) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )


def decode_json(
    raw: bytes,
) -> Dict[str, Any]:
    if len(
        raw
    ) > MAX_REQUEST_BYTES:
        raise ValueError(
            "Desktop-agent request exceeds the maximum size."
        )

    try:
        payload = json.loads(
            raw.decode(
                "utf-8"
            )
        )
    except Exception as exc:
        raise ValueError(
            "Request body is not valid UTF-8 JSON."
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "Request body must be a JSON object."
        )

    return payload
