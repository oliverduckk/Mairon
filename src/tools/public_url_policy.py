"""S1–S4 acceptance: classify external, public HTTP(S) URLs without fetching.

Used at both public web-read execution admission and cloud result egress.
This is a conservative lexical boundary, not a DNS/rebinding, redirect or
remote-provider network guarantee.  No DNS lookup or side effect occurs here.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qsl, urlsplit, urlunsplit

_NONPUBLIC_SUFFIXES = (
    "localhost", "local", "localdomain", "lan", "internal", "intranet",
    "corp", "private", "home", "home.arpa", "test", "invalid", "onion",
    "nip.io", "sslip.io", "xip.io", "lvh.me", "localtest.me", "localhost.direct",
)
_SECRET_QUERY_KEY = re.compile(r"(?:token|access_token|refresh_token|api[_-]?key|key|password|secret|authorization|auth|credential|signature|sig|session(?:_?id)?|jwt|code|client_secret)\Z", re.I)
_DOMAIN_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z", re.I)


def public_http_url(value: object, *, strip_query: bool = False) -> str | None:
    """Return a checked public URL, or None. Strip query/fragment for egress.

    Public domain resolution cannot be proven without a trusted resolver and
    redirect enforcement at the actual network executor. Known non-public
    address forms are rejected before any tool adapter is invoked.
    """
    if not isinstance(value, str) or not value or len(value) > 1800:
        return None
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port  # Force validation of malformed/out-of-range ports.
        if (parts.scheme not in {"http", "https"} or not parts.netloc or not host
                or parts.username is not None or parts.password is not None):
            return None
        # A signed/credential-bearing URL is not public evidence. A normal
        # search query or section anchor may be projected without its query.
        if any(_SECRET_QUERY_KEY.fullmatch(key) for key, _ in parse_qsl(
            parts.query, keep_blank_values=True, max_num_fields=100,
        )):
            return None
        host = host.rstrip(".").lower()
        if not host or "%" in host or "\\" in host:
            return None
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            # Numeric dotted names can be interpreted as legacy IPv4 forms by
            # some resolvers even though ipaddress rejects them.
            if re.fullmatch(r"[0-9.]+", host):
                return None
            ascii_host = host.encode("idna").decode("ascii")
            labels = ascii_host.split(".")
            if (len(labels) < 2 or len(ascii_host) > 253
                    or not all(_DOMAIN_LABEL.fullmatch(label) for label in labels)):
                return None
            if any(ascii_host == suffix or ascii_host.endswith("." + suffix)
                   for suffix in _NONPUBLIC_SUFFIXES):
                return None
        else:
            if not address.is_global:
                return None
        if port is not None and port <= 0:
            return None
        if strip_query:
            return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        return value
    except (ValueError, UnicodeError):
        return None
