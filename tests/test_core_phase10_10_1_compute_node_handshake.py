import sys
import threading
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
    ALLOWED_ACTIONS,
    DESKTOP_CAPABILITY_ACTIONS,
    PROTOCOL_VERSION,
    build_desktop_node_descriptor,
    build_request,
    node_supports_action,
    normalise_node_descriptor,
    validate_request,
)

import core.desktop_agent_client as client_module

from desktop_agent import (
    create_desktop_agent_server,
    execute_approved_agent_action,
)


def run():
    # --------------------------------------------------
    # 1. Capability discovery is an explicit, approved control-plane action.
    # --------------------------------------------------

    assert "describe_node" in ALLOWED_ACTIONS

    request = validate_request(
        build_request(
            request_id="node-discovery-test",
            action="describe_node",
            args={},
        )
    )

    assert request["action"] == "describe_node"
    assert request["args"] == {}

    try:
        validate_request(
            build_request(
                request_id="bad-node-discovery-test",
                action="describe_node",
                args={
                    "path": r"C:\secret",
                },
            )
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "describe_node must not accept arbitrary arguments"
        )

    # --------------------------------------------------
    # 2. Descriptor contains only bounded operational metadata.
    # --------------------------------------------------

    descriptor = build_desktop_node_descriptor(
        node_id="test_windows_node"
    )

    assert descriptor["node_id"] == "test_windows_node"
    assert descriptor["node_type"] == "desktop"
    assert descriptor["platform"] == "windows"
    assert descriptor["protocol_version"] == PROTOCOL_VERSION
    assert descriptor["transport_scope"] == "localhost_only"
    assert descriptor["available"] is True
    assert descriptor["status"] == "online"
    assert descriptor["power"]["wake_supported"] is False

    expected_capabilities = set(
        DESKTOP_CAPABILITY_ACTIONS.keys()
    )

    assert set(
        descriptor["capabilities"]
    ) == expected_capabilities

    forbidden_serialised_terms = (
        "secret",
        "token",
        "password",
        "shell",
        "command_line",
        "executable_path",
        "filesystem_root",
    )

    descriptor_text = repr(
        descriptor
    ).lower()

    for term in forbidden_serialised_terms:
        assert term not in descriptor_text

    # --------------------------------------------------
    # 3. Core validates node metadata before trusting capabilities.
    # --------------------------------------------------

    normalised = normalise_node_descriptor(
        descriptor
    )

    assert normalised == descriptor

    poisoned = dict(
        descriptor
    )

    poisoned[
        "capabilities"
    ] = list(
        descriptor["capabilities"]
    ) + [
        "arbitrary_shell",
    ]

    try:
        normalise_node_descriptor(
            poisoned
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Unknown advertised capabilities must fail closed"
        )

    remote_scope = dict(
        descriptor
    )

    remote_scope[
        "transport_scope"
    ] = "lan"

    try:
        normalise_node_descriptor(
            remote_scope
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Phase 10.10.1 must not silently widen localhost trust to LAN"
        )

    # --------------------------------------------------
    # 4. Capability support is deterministic and action-specific.
    # --------------------------------------------------

    assert node_supports_action(
        descriptor,
        "launch_application",
    ) is True

    assert node_supports_action(
        descriptor,
        "search_approved_local_files",
    ) is True

    assert node_supports_action(
        descriptor,
        "launch_steam_game_appid",
    ) is True

    assert node_supports_action(
        descriptor,
        "definitely_not_an_action",
    ) is False

    reduced = dict(
        descriptor
    )

    reduced[
        "capabilities"
    ] = [
        "trusted_browser",
    ]

    assert node_supports_action(
        reduced,
        "open_trusted_browser_site",
    ) is True

    assert node_supports_action(
        reduced,
        "launch_application",
    ) is False

    # --------------------------------------------------
    # 5. Production dispatcher returns the safe descriptor.
    # --------------------------------------------------

    direct = execute_approved_agent_action(
        "describe_node",
        {},
    )

    assert direct["success"] is True
    assert direct["status"] == "node_ready"

    direct_node = normalise_node_descriptor(
        direct["node"]
    )

    assert direct_node[
        "node_type"
    ] == "desktop"

    # Existing ping contract stays backwards compatible.
    ping = execute_approved_agent_action(
        "ping",
        {},
    )

    assert ping == {
        "success": True,
        "status": "pong",
        "agent": "windows_desktop",
    }

    # --------------------------------------------------
    # 6. Real authenticated client/server handshake.
    # --------------------------------------------------

    secret = "phase10-10-test-secret-" + ("x" * 32)

    server = create_desktop_agent_server(
        host="127.0.0.1",
        port=0,
        secret=secret,
    )

    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={
            "poll_interval": 0.05,
        },
        daemon=True,
    )

    thread.start()

    try:
        host, port = server.server_address

        base_url = (
            f"http://{host}:{port}"
        )

        discovered = (
            client_module
            .describe_desktop_node(
                base_url=base_url,
                secret=secret,
            )
        )

        assert discovered[
            "success"
        ] is True

        assert discovered[
            "status"
        ] == "node_ready"

        assert discovered[
            "node"
        ][
            "transport_scope"
        ] == "localhost_only"

        assert (
            client_module
            .desktop_node_supports_action(
                discovered,
                "launch_application",
            )
            is True
        )

        unauthorized = (
            client_module
            .describe_desktop_node(
                base_url=base_url,
                secret="wrong-secret-" + ("y" * 32),
            )
        )

        assert unauthorized[
            "success"
        ] is False

        assert unauthorized[
            "status"
        ] == "unauthorized"

    finally:
        server.shutdown()
        server.server_close()

        thread.join(
            timeout=2.0
        )

    # --------------------------------------------------
    # 7. Client rejects malformed descriptors even after a successful call.
    # --------------------------------------------------

    original_call = (
        client_module
        .call_desktop_agent
    )

    try:
        def fake_call(
            *args,
            **kwargs,
        ):
            return {
                "success": True,
                "status": "node_ready",
                "node": {
                    **descriptor,
                    "platform": "mystery_os",
                },
            }

        client_module.call_desktop_agent = (
            fake_call
        )

        invalid = (
            client_module
            .describe_desktop_node()
        )

        assert invalid[
            "success"
        ] is False

        assert invalid[
            "status"
        ] == "invalid_node_descriptor"

    finally:
        client_module.call_desktop_agent = (
            original_call
        )

    print(
        "Mairon Phase 10.10.1 compute-node capability handshake tests: PASS"
    )


if __name__ == "__main__":
    run()
