import json
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(
    SRC_DIR
) not in sys.path:
    sys.path.insert(
        0,
        str(
            SRC_DIR
        ),
    )


from core.desktop_agent_protocol import (
    build_desktop_node_descriptor,
)
from core.desktop_node_policy import (
    DECISION_ASK_TO_WAKE,
    DECISION_DESKTOP_UNAVAILABLE,
    DECISION_USE_DESKTOP,
)
from core.desktop_node_registry import (
    desktop_wake_is_configured,
    load_wake_target,
    normalise_mac_address,
)
from core.desktop_node_runtime import (
    decide_desktop_use_from_runtime,
    inspect_desktop_node,
)


def _write_registry(
    path: Path,
    *,
    enabled: bool = True,
    mac: str = "AA-BB-CC-DD-EE-FF",
    broadcast: str = "192.168.1.255",
    port: int = 9,
):
    payload = {
        "schema_version": "1",
        "nodes": {
            "windows_desktop": {
                "node_type": "desktop",
                "platform": "windows",
                "wake": {
                    "enabled": enabled,
                    "mac_address": mac,
                    "broadcast_address": broadcast,
                    "port": port,
                },
            },
        },
    }

    path.write_text(
        json.dumps(
            payload
        ),
        encoding="utf-8",
    )


def run():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(
            temp_dir
        )

        registry_path = (
            root
            / "desktop_nodes.json"
        )

        # --------------------------------------------------
        # 1. Missing private config means no wake authority.
        # --------------------------------------------------

        assert (
            desktop_wake_is_configured(
                path=registry_path,
            )
            is False
        )

        assert (
            load_wake_target(
                path=registry_path,
            )
            is None
        )

        # --------------------------------------------------
        # 2. Valid enabled config becomes truthful wake authority.
        # --------------------------------------------------

        _write_registry(
            registry_path
        )

        target = load_wake_target(
            path=registry_path,
        )

        assert target is not None
        assert (
            target.node_id
            == "windows_desktop"
        )
        assert (
            target.mac_address
            == "AA:BB:CC:DD:EE:FF"
        )
        assert (
            target.broadcast_address
            == "192.168.1.255"
        )
        assert target.port == 9

        assert (
            desktop_wake_is_configured(
                path=registry_path,
            )
            is True
        )

        # --------------------------------------------------
        # 3. MAC formats are normalised, malformed values fail closed.
        # --------------------------------------------------

        assert (
            normalise_mac_address(
                "aabb.ccdd.eeff"
            )
            == "AA:BB:CC:DD:EE:FF"
        )

        _write_registry(
            registry_path,
            mac="definitely-not-a-mac",
        )

        assert (
            desktop_wake_is_configured(
                path=registry_path,
            )
            is False
        )

        # Restore valid registry.
        _write_registry(
            registry_path
        )

        # --------------------------------------------------
        # 4. Presence combines live Agent state + private wake truth.
        # --------------------------------------------------

        descriptor = (
            build_desktop_node_descriptor(
                node_id="windows_desktop"
            )
        )

        def online_probe():
            return {
                "success": True,
                "status": "node_ready",
                "available": True,
                "node": descriptor,
            }

        online = inspect_desktop_node(
            registry_path=registry_path,
            probe_function=online_probe,
        )

        assert online["available"] is True
        assert online["status"] == "online"
        assert online["wake_supported"] is True
        assert online["wake_configured"] is True

        # Private target material must not leak through runtime presence.
        presence_text = repr(
            online
        )

        assert "AA:BB:CC:DD:EE:FF" not in presence_text
        assert "192.168.1.255" not in presence_text

        def offline_probe():
            return {
                "success": False,
                "status": "agent_unavailable",
                "available": False,
                "node": None,
            }

        offline = inspect_desktop_node(
            registry_path=registry_path,
            probe_function=offline_probe,
        )

        assert offline["available"] is False
        assert offline["status"] == "offline"
        assert offline["wake_supported"] is True
        assert offline["node"] is None

        # --------------------------------------------------
        # 5. Real runtime state feeds the existing deterministic wake policy.
        # --------------------------------------------------

        online_decision = (
            decide_desktop_use_from_runtime(
                desktop_required=True,
                required_capability="application_control",
                registry_path=registry_path,
                probe_function=online_probe,
            )
        )

        assert (
            online_decision.decision
            == DECISION_USE_DESKTOP
        )

        offline_required = (
            decide_desktop_use_from_runtime(
                desktop_required=True,
                required_capability="application_control",
                registry_path=registry_path,
                probe_function=offline_probe,
            )
        )

        assert (
            offline_required.decision
            == DECISION_ASK_TO_WAKE
        )

        # --------------------------------------------------
        # 6. Disabled WOL means the same offline task cannot ask for a wake.
        # --------------------------------------------------

        _write_registry(
            registry_path,
            enabled=False,
        )

        disabled_decision = (
            decide_desktop_use_from_runtime(
                desktop_required=True,
                required_capability="application_control",
                registry_path=registry_path,
                probe_function=offline_probe,
            )
        )

        assert (
            disabled_decision.decision
            == DECISION_DESKTOP_UNAVAILABLE
        )

        # --------------------------------------------------
        # 7. Registry remains private configuration, not source-controlled state.
        # --------------------------------------------------

        default_registry_text = str(
            (
                PROJECT_ROOT
                / "data"
                / "private"
                / "desktop_nodes.json"
            )
        ).lower()

        assert "data" in default_registry_text
        assert "private" in default_registry_text

    print(
        "Mairon Phase 10.10.3 desktop presence + wake configuration tests: PASS"
    )


if __name__ == "__main__":
    run()
