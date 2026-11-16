"""SEC-02 local-only service endpoint admission; no DNS or network operation.

Remote deployment requires a separately governed export capability. A local
endpoint is not permission to follow a redirect or use an environment proxy.
"""
import ipaddress
from urllib.parse import urlsplit, urlunsplit


def local_http_endpoint(value: object) -> str | None:
    """Return a canonical numeric-loopback HTTP(S) base URL, or None.

    Exact localhost is pinned to IPv4 loopback before any client construction.
    Other names, legacy numeric aliases and IPv6 zones/mappings are unsupported.
    """
    if (not isinstance(value, str) or not value or len(value) > 512
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
            or any(c in value for c in ("\\", "%"))):
        return None
    try:
        parts = urlsplit(value)
        host, port = parts.hostname, parts.port
        if (parts.scheme not in {"http", "https"} or not parts.netloc or not host
                or parts.username is not None or parts.password is not None
                or parts.path not in {"", "/"} or parts.query or parts.fragment
                or "?" in value or "#" in value or parts.netloc.endswith(":")):
            return None
        if port is not None and not 1 <= port <= 65535:
            return None
        if host == "localhost":
            host = "127.0.0.1"
        address = ipaddress.ip_address(host)
        if (not address.is_loopback or getattr(address, "ipv4_mapped", None) is not None
                or (address.version == 4 and host != str(address))):
            return None
        canonical = str(address)
        netloc = f"[{canonical}]" if address.version == 6 else canonical
        if port is not None:
            netloc += ":" + str(port)
        return urlunsplit((parts.scheme, netloc, "", "", ""))
    except (ValueError, UnicodeError):
        return None
