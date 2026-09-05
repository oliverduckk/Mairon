import argparse
import json
import sys
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
from pathlib import Path
from typing import Any, Callable, Dict, Optional


SRC_DIR = Path(
    __file__
).resolve().parent

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
    DEFAULT_AGENT_HOST,
    DEFAULT_AGENT_PORT,
    MAX_REQUEST_BYTES,
    TOKEN_HEADER,
    decode_json,
    encode_json,
    error_response,
    load_or_create_agent_secret,
    secrets_match,
    success_response,
    validate_request,
)


ActionExecutor = Callable[
    [
        str,
        Dict[str, Any],
    ],
    Dict[str, Any],
]


def execute_approved_agent_action(
    action: str,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Production Desktop Agent dispatcher.

    Every callable action is explicitly listed here. The request can never
    provide a Python function name, executable path, shell command, or module.
    """

    if action == "ping":
        return {
            "success": True,
            "status": "pong",
            "agent": "windows_desktop",
        }

    if action == "launch_application":
        from tools.desktop_tools import (
            launch_application,
        )

        return launch_application(
            app_name=args[
                "app_name"
            ],
        )

    return {
        "success": False,
        "status": "unsupported_action",
        "message": (
            "That action is not implemented by the Windows Desktop Agent."
        ),
    }


class DesktopAgentRequestHandler(
    BaseHTTPRequestHandler
):
    server_version = "MaironDesktopAgent/0.1"
    protocol_version = "HTTP/1.1"

    def log_message(
        self,
        format_string,
        *args,
    ):
        # Keep the terminal useful rather than printing default HTTP access
        # logs for every local action. Explicit action logs are emitted below.
        return

    def _send_json(
        self,
        status_code: int,
        payload: Dict[str, Any],
    ) -> None:
        raw = encode_json(
            payload
        )

        self.send_response(
            status_code
        )

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )

        self.send_header(
            "Content-Length",
            str(
                len(
                    raw
                )
            ),
        )

        self.send_header(
            "Connection",
            "close",
        )

        self.end_headers()

        self.wfile.write(
            raw
        )

    def _request_id_from_untrusted_body(
        self,
        payload: Any,
    ) -> str:
        if not isinstance(
            payload,
            dict,
        ):
            return ""

        return str(
            payload.get(
                "request_id",
                "",
            )
            or ""
        )[
            :128
        ]

    def do_GET(
        self,
    ):
        self._send_json(
            404,
            error_response(
                request_id="",
                code="not_found",
                message=(
                    "Desktop Agent accepts authenticated POST requests only."
                ),
            ),
        )

    def do_POST(
        self,
    ):
        if self.path != "/v1/action":
            self._send_json(
                404,
                error_response(
                    request_id="",
                    code="not_found",
                    message=(
                        "Unknown Desktop Agent endpoint."
                    ),
                ),
            )
            return

        expected_secret = str(
            getattr(
                self.server,
                "agent_secret",
                "",
            )
            or ""
        )

        supplied_secret = str(
            self.headers.get(
                TOKEN_HEADER,
                "",
            )
            or ""
        )

        if not secrets_match(
            supplied_secret,
            expected_secret,
        ):
            self._send_json(
                401,
                error_response(
                    request_id="",
                    code="unauthorized",
                    message=(
                        "Desktop Agent authentication failed."
                    ),
                ),
            )
            return

        content_length_raw = str(
            self.headers.get(
                "Content-Length",
                "",
            )
            or ""
        ).strip()

        try:
            content_length = int(
                content_length_raw
            )
        except Exception:
            content_length = -1

        if (
            content_length < 0
            or content_length > MAX_REQUEST_BYTES
        ):
            self._send_json(
                413,
                error_response(
                    request_id="",
                    code="invalid_size",
                    message=(
                        "Desktop Agent request size is invalid."
                    ),
                ),
            )
            return

        raw = self.rfile.read(
            content_length
        )

        untrusted_payload = None

        try:
            untrusted_payload = decode_json(
                raw
            )

            request = validate_request(
                untrusted_payload
            )

        except ValueError as exc:
            self._send_json(
                400,
                error_response(
                    request_id=(
                        self._request_id_from_untrusted_body(
                            untrusted_payload
                        )
                    ),
                    code="invalid_request",
                    message=str(
                        exc
                    ),
                ),
            )
            return

        action = request[
            "action"
        ]

        args = request[
            "args"
        ]

        request_id = request[
            "request_id"
        ]

        executor = getattr(
            self.server,
            "action_executor",
            None,
        )

        if executor is None:
            self._send_json(
                500,
                error_response(
                    request_id=request_id,
                    code="agent_misconfigured",
                    message=(
                        "Desktop Agent has no action executor."
                    ),
                ),
            )
            return

        try:
            result = executor(
                action,
                args,
            )

        except Exception as exc:
            self._send_json(
                500,
                error_response(
                    request_id=request_id,
                    code="action_exception",
                    message=str(
                        exc
                    ),
                ),
            )
            return

        if not isinstance(
            result,
            dict,
        ):
            self._send_json(
                500,
                error_response(
                    request_id=request_id,
                    code="invalid_action_result",
                    message=(
                        "Desktop Agent action returned an invalid result."
                    ),
                ),
            )
            return

        print(
            "[Desktop Agent] "
            f"{action} -> "
            f"{result.get('status') or ('ok' if result.get('success') else 'failed')}"
        )

        self._send_json(
            200,
            success_response(
                request_id=request_id,
                result=result,
            ),
        )


class DesktopAgentServer(
    ThreadingHTTPServer
):
    allow_reuse_address = True
    daemon_threads = True


def create_desktop_agent_server(
    host: str = DEFAULT_AGENT_HOST,
    port: int = DEFAULT_AGENT_PORT,
    secret: Optional[str] = None,
    action_executor: Optional[
        ActionExecutor
    ] = None,
) -> DesktopAgentServer:
    """
    Create a localhost-only Desktop Agent server.

    Phase 9.1 intentionally refuses LAN binding. Remote/Pi transport comes
    later with a stronger device-identity layer.
    """

    host_value = str(
        host
        or ""
    ).strip().lower()

    if host_value not in {
        "127.0.0.1",
        "localhost",
    }:
        raise ValueError(
            "Phase 9.1 Desktop Agent may bind to localhost only."
        )

    port_value = int(
        port
    )

    if not (
        0 <= port_value <= 65535
    ):
        raise ValueError(
            "Desktop Agent port must be between 0 and 65535."
        )

    server = DesktopAgentServer(
        (
            "127.0.0.1",
            port_value,
        ),
        DesktopAgentRequestHandler,
    )

    server.agent_secret = (
        str(
            secret
            or ""
        ).strip()
        or load_or_create_agent_secret()
    )

    server.action_executor = (
        action_executor
        or execute_approved_agent_action
    )

    return server


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Mairon Windows Desktop Agent v0.1"
        )
    )

    parser.add_argument(
        "--host",
        default=DEFAULT_AGENT_HOST,
    )

    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_AGENT_PORT,
    )

    args = parser.parse_args()

    server = create_desktop_agent_server(
        host=args.host,
        port=args.port,
    )

    bound_host, bound_port = (
        server.server_address
    )

    print(
        "Mairon Windows Desktop Agent v0.1 starting..."
    )

    print(
        f"Listening: http://{bound_host}:{bound_port}"
    )

    print(
        "Security: localhost-only + shared local secret"
    )

    print(
        "Approved actions: ping, launch_application"
    )

    try:
        server.serve_forever(
            poll_interval=0.25
        )

    except KeyboardInterrupt:
        print(
            "\nDesktop Agent stopping..."
        )

    finally:
        server.server_close()


if __name__ == "__main__":
    main()
