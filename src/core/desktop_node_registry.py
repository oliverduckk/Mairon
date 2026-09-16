import ipaddress
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


NODE_REGISTRY_SCHEMA_VERSION = "1"
DEFAULT_DESKTOP_NODE_ID = "windows_desktop"
DEFAULT_WAKE_PORT = 9

_MAC_HEX_PATTERN = re.compile(
    r"^[0-9a-fA-F]{12}$"
)


@dataclass(
    frozen=True
)
class WakeTarget:
    """
    Private Core-owned Wake-on-LAN target.

    This object is intentionally not part of the public node descriptor or
    developer diagnostics surface.
    """

    node_id: str
    mac_address: str
    broadcast_address: str
    port: int

    def to_private_dict(
        self,
    ) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "mac_address": self.mac_address,
            "broadcast_address": self.broadcast_address,
            "port": self.port,
        }


def get_desktop_node_registry_path() -> Path:
    explicit = str(
        os.environ.get(
            "MAIRON_DESKTOP_NODE_REGISTRY_PATH",
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
        / "desktop_nodes.json"
    )


def normalise_mac_address(
    value: str,
) -> str:
    raw = str(
        value
        or ""
    ).strip()

    compact = re.sub(
        r"[^0-9a-fA-F]",
        "",
        raw,
    )

    if not _MAC_HEX_PATTERN.fullmatch(
        compact
    ):
        raise ValueError(
            "Wake-on-LAN MAC address must contain exactly 12 hexadecimal digits."
        )

    compact = compact.upper()

    return ":".join(
        compact[index:index + 2]
        for index in range(
            0,
            12,
            2,
        )
    )


def normalise_broadcast_address(
    value: str,
) -> str:
    raw = str(
        value
        or ""
    ).strip()

    try:
        address = ipaddress.ip_address(
            raw
        )

    except ValueError as exc:
        raise ValueError(
            "Wake-on-LAN broadcast address must be a valid IPv4 address."
        ) from exc

    if address.version != 4:
        raise ValueError(
            "Wake-on-LAN currently supports IPv4 broadcast targets only."
        )

    return str(
        address
    )


def _normalise_port(
    value: Any,
) -> int:
    try:
        port = int(
            value
        )

    except Exception as exc:
        raise ValueError(
            "Wake-on-LAN port must be an integer."
        ) from exc

    if not (
        1 <= port <= 65535
    ):
        raise ValueError(
            "Wake-on-LAN port must be between 1 and 65535."
        )

    return port


def _read_registry(
    path: Optional[
        Path
    ] = None,
) -> Optional[Dict[str, Any]]:
    registry_path = (
        Path(
            path
        )
        if path is not None
        else get_desktop_node_registry_path()
    )

    if not registry_path.is_file():
        return None

    try:
        payload = json.loads(
            registry_path.read_text(
                encoding="utf-8",
            )
        )

    except Exception as exc:
        raise ValueError(
            "Desktop node registry is not valid JSON."
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "Desktop node registry must be a JSON object."
        )

    version = str(
        payload.get(
            "schema_version",
            "",
        )
        or ""
    ).strip()

    if version != NODE_REGISTRY_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported desktop node registry schema version."
        )

    nodes = payload.get(
        "nodes"
    )

    if not isinstance(
        nodes,
        dict,
    ):
        raise ValueError(
            "Desktop node registry must contain a nodes object."
        )

    return payload


def load_wake_target(
    node_id: str = DEFAULT_DESKTOP_NODE_ID,
    *,
    path: Optional[
        Path
    ] = None,
) -> Optional[WakeTarget]:
    """
    Load one explicitly configured and enabled WOL target.

    Missing registry, missing node, or disabled wake configuration means
    "wake authority does not exist" rather than an error.
    """

    payload = _read_registry(
        path
    )

    if payload is None:
        return None

    resolved_node_id = str(
        node_id
        or ""
    ).strip().lower()

    if not resolved_node_id:
        raise ValueError(
            "Desktop node_id is required."
        )

    node = (
        payload.get(
            "nodes"
        )
        or {}
    ).get(
        resolved_node_id
    )

    if node is None:
        return None

    if not isinstance(
        node,
        dict,
    ):
        raise ValueError(
            "Desktop node registry entry must be an object."
        )

    node_type = str(
        node.get(
            "node_type",
            "desktop",
        )
        or ""
    ).strip().lower()

    platform = str(
        node.get(
            "platform",
            "windows",
        )
        or ""
    ).strip().lower()

    if node_type != "desktop":
        raise ValueError(
            "Wake target must refer to a desktop node."
        )

    if platform != "windows":
        raise ValueError(
            "Wake target must refer to a Windows node."
        )

    wake = node.get(
        "wake"
    )

    if wake is None:
        return None

    if not isinstance(
        wake,
        dict,
    ):
        raise ValueError(
            "Desktop node wake configuration must be an object."
        )

    enabled = wake.get(
        "enabled",
        False,
    )

    if enabled is not True:
        return None

    mac_address = normalise_mac_address(
        wake.get(
            "mac_address",
            "",
        )
    )

    broadcast_address = (
        normalise_broadcast_address(
            wake.get(
                "broadcast_address",
                "255.255.255.255",
            )
        )
    )

    port = _normalise_port(
        wake.get(
            "port",
            DEFAULT_WAKE_PORT,
        )
    )

    return WakeTarget(
        node_id=resolved_node_id,
        mac_address=mac_address,
        broadcast_address=broadcast_address,
        port=port,
    )


def desktop_wake_is_configured(
    node_id: str = DEFAULT_DESKTOP_NODE_ID,
    *,
    path: Optional[
        Path
    ] = None,
) -> bool:
    try:
        return load_wake_target(
            node_id,
            path=path,
        ) is not None

    except ValueError:
        # Invalid private configuration must fail closed.
        return False
