import json
import os
import uuid
from typing import Any, Dict, Optional
from urllib.error import (
    HTTPError,
    URLError,
)
from urllib.request import (
    Request,
    urlopen,
)


from core.desktop_agent_protocol import (
    DEFAULT_AGENT_HOST,
    DEFAULT_AGENT_PORT,
    MAX_REQUEST_BYTES,
    TOKEN_HEADER,
    build_request,
    decode_json,
    encode_json,
    load_or_create_agent_secret,
)


DEFAULT_TIMEOUT_SECONDS = 4.0


def get_desktop_agent_url() -> str:
    explicit = str(
        os.environ.get(
            "MAIRON_DESKTOP_AGENT_URL",
            "",
        )
        or ""
    ).strip()

    if explicit:
        return explicit.rstrip(
            "/"
        )

    return (
        f"http://{DEFAULT_AGENT_HOST}:"
        f"{DEFAULT_AGENT_PORT}"
    )


def call_desktop_agent(
    action: str,
    args: Optional[
        Dict[str, Any]
    ] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    base_url: Optional[str] = None,
    secret: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send one authenticated structured request to the local Desktop Agent.
    """

    request_id = str(
        uuid.uuid4()
    )

    payload = build_request(
        request_id=request_id,
        action=action,
        args=args,
    )

    raw = encode_json(
        payload
    )

    if len(
        raw
    ) > MAX_REQUEST_BYTES:
        return {
            "success": False,
            "status": "request_too_large",
            "message": (
                "Desktop Agent request exceeds the maximum size."
            ),
        }

    token = (
        str(
            secret
            or ""
        ).strip()
        or load_or_create_agent_secret()
    )

    url = (
        str(
            base_url
            or get_desktop_agent_url()
        ).rstrip(
            "/"
        )
        + "/v1/action"
    )

    request = Request(
        url=url,
        data=raw,
        method="POST",
        headers={
            "Content-Type": "application/json",
            TOKEN_HEADER: token,
            "Content-Length": str(
                len(
                    raw
                )
            ),
        },
    )

    try:
        with urlopen(
            request,
            timeout=float(
                timeout
            ),
        ) as response:
            response_raw = response.read(
                MAX_REQUEST_BYTES
            )

    except HTTPError as exc:
        try:
            response_raw = exc.read(
                MAX_REQUEST_BYTES
            )

            payload = decode_json(
                response_raw
            )

            error = payload.get(
                "error"
            ) or {}

            return {
                "success": False,
                "status": str(
                    error.get(
                        "code",
                        "http_error",
                    )
                    or "http_error"
                ),
                "message": str(
                    error.get(
                        "message",
                        str(
                            exc
                        ),
                    )
                    or str(
                        exc
                    )
                ),
            }

        except Exception:
            return {
                "success": False,
                "status": "http_error",
                "message": str(
                    exc
                ),
            }

    except URLError as exc:
        return {
            "success": False,
            "status": "agent_unavailable",
            "message": (
                "Mairon Desktop Agent is not reachable."
            ),
            "detail": str(
                exc
            ),
        }

    except Exception as exc:
        return {
            "success": False,
            "status": "agent_request_failed",
            "message": str(
                exc
            ),
        }

    try:
        response_payload = decode_json(
            response_raw
        )

    except ValueError as exc:
        return {
            "success": False,
            "status": "invalid_agent_response",
            "message": str(
                exc
            ),
        }

    if (
        str(
            response_payload.get(
                "request_id",
                "",
            )
            or ""
        )
        != request_id
    ):
        return {
            "success": False,
            "status": "request_id_mismatch",
            "message": (
                "Desktop Agent response did not match the request."
            ),
        }

    if response_payload.get(
        "success"
    ) is not True:
        error = response_payload.get(
            "error"
        ) or {}

        return {
            "success": False,
            "status": str(
                error.get(
                    "code",
                    "agent_error",
                )
                or "agent_error"
            ),
            "message": str(
                error.get(
                    "message",
                    "Desktop Agent request failed.",
                )
                or "Desktop Agent request failed."
            ),
        }

    result = response_payload.get(
        "result"
    )

    if not isinstance(
        result,
        dict,
    ):
        return {
            "success": False,
            "status": "invalid_action_result",
            "message": (
                "Desktop Agent returned an invalid action result."
            ),
        }

    return result


def ping_desktop_agent(
    **kwargs,
) -> Dict[str, Any]:
    return call_desktop_agent(
        action="ping",
        args={},
        **kwargs,
    )


def launch_application_via_agent(
    app_name: str,
    **kwargs,
) -> Dict[str, Any]:
    return call_desktop_agent(
        action="launch_application",
        args={
            "app_name": str(
                app_name
                or ""
            ).strip().lower(),
        },
        **kwargs,
    )
