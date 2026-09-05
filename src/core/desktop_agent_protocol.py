import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any, Dict, Optional


PROTOCOL_VERSION = "1"
DEFAULT_AGENT_HOST = "127.0.0.1"
DEFAULT_AGENT_PORT = 8765
MAX_REQUEST_BYTES = 64 * 1024

TOKEN_HEADER = "X-Mairon-Agent-Token"

ALLOWED_ACTIONS = {
    "ping",
    "launch_application",
}


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

    if action == "ping":
        if args:
            raise ValueError(
                "ping does not accept arguments."
            )

    elif action == "launch_application":
        allowed_keys = {
            "app_name",
        }

        unknown = set(
            args.keys()
        ) - allowed_keys

        if unknown:
            raise ValueError(
                "launch_application received unsupported arguments."
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
                "launch_application requires a valid app_name."
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
