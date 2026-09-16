from pathlib import Path
from typing import Any, Callable, Dict, Optional


from core.desktop_agent_client import (
    probe_desktop_node,
)
from core.desktop_node_policy import (
    DesktopNodeDecision,
    WAKE_POLICY_ALWAYS_ASK,
    decide_desktop_node_use,
)
from core.desktop_node_registry import (
    DEFAULT_DESKTOP_NODE_ID,
    desktop_wake_is_configured,
)


ProbeFunction = Callable[
    [],
    Dict[str, Any],
]


def inspect_desktop_node(
    *,
    node_id: str = DEFAULT_DESKTOP_NODE_ID,
    registry_path: Optional[
        Path
    ] = None,
    probe_function: Optional[
        Callable[..., Dict[str, Any]]
    ] = None,
) -> Dict[str, Any]:
    """
    Combine authenticated Desktop Agent reachability with Core-owned wake
    configuration.

    Private WOL target details are deliberately not returned.
    """

    probe = (
        probe_function
        or probe_desktop_node
    )

    try:
        probe_result = probe()

    except Exception as exc:
        probe_result = {
            "success": False,
            "status": "agent_probe_failed",
            "message": str(
                exc
            ),
            "available": False,
            "node": None,
        }

    if not isinstance(
        probe_result,
        dict,
    ):
        probe_result = {
            "success": False,
            "status": "invalid_agent_probe",
            "message": (
                "Desktop Agent probe returned an invalid result."
            ),
            "available": False,
            "node": None,
        }

    wake_configured = (
        desktop_wake_is_configured(
            node_id,
            path=registry_path,
        )
    )

    online = (
        probe_result.get(
            "success"
        ) is True
        and probe_result.get(
            "available"
        ) is True
        and isinstance(
            probe_result.get(
                "node"
            ),
            dict,
        )
    )

    node = (
        probe_result.get(
            "node"
        )
        if online
        else None
    )

    resolved_node_id = node_id

    if isinstance(
        node,
        dict,
    ):
        discovered_id = str(
            node.get(
                "node_id",
                "",
            )
            or ""
        ).strip().lower()

        if discovered_id:
            resolved_node_id = discovered_id

    return {
        "node_id": resolved_node_id,
        "available": online,
        "status": (
            "online"
            if online
            else "offline"
        ),
        "node": node,
        "probe_status": str(
            probe_result.get(
                "status",
                "",
            )
            or ""
        ),
        "wake_supported": wake_configured,
        "wake_configured": wake_configured,
    }


def decide_desktop_use_from_runtime(
    *,
    desktop_required: bool,
    explicit_wake_requested: bool = False,
    alternative_available: bool = False,
    required_capability: Optional[str] = None,
    wake_policy: str = WAKE_POLICY_ALWAYS_ASK,
    node_id: str = DEFAULT_DESKTOP_NODE_ID,
    registry_path: Optional[
        Path
    ] = None,
    probe_function: Optional[
        Callable[..., Dict[str, Any]]
    ] = None,
) -> DesktopNodeDecision:
    """
    Produce the Phase 10.10.2 policy result from real runtime presence/config.
    """

    presence = inspect_desktop_node(
        node_id=node_id,
        registry_path=registry_path,
        probe_function=probe_function,
    )

    return decide_desktop_node_use(
        presence.get(
            "node"
        ),
        desktop_required=desktop_required,
        explicit_wake_requested=explicit_wake_requested,
        alternative_available=alternative_available,
        required_capability=required_capability,
        wake_supported=bool(
            presence.get(
                "wake_supported"
            )
        ),
        wake_policy=wake_policy,
    )
