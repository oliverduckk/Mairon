"""S1–S4 acceptance: classify external, public HTTP(S) URLs without fetching.

Used at both public web-read execution admission and cloud result egress.
This is a conservative lexical boundary, not a DNS/rebinding, redirect or
remote-provider network guarantee.  No DNS lookup or side effect occurs here.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit

_NONPUBLIC_SUFFIXES = (
    "localhost", "local", "localdomain", "lan", "internal", "intranet",
    "corp", "private", "home", "home.arpa", "test", "invalid", "onion",
    "nip.io", "sslip.io", "xip.io", "lvh.me", "localtest.me", "localhost.direct",
)
_SECRET_QUERY_KEY = re.compile(r"(?:token|access_token|refresh_token|api[_-]?key|key|password|secret|authorization|auth|credential|signature|sig|session(?:_?id)?|jwt|code|client_secret)\Z", re.I)
_DOMAIN_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z", re.I)
_NUMERIC_LABEL = re.compile(r"(?:[0-9]+|0x[0-9a-f]+)\Z", re.I)
_SERVICE_ACCESS_KEY = re.compile(r"(?:x[-_]amz[-_].*|x[-_]goog[-_].*|awsaccesskeyid|googleaccessid|key[-_]pair[-_]id|policy)\Z", re.I)
_AZURE_ACCESS_KEYS = frozenset({"sv", "se", "sp", "sr", "st", "si", "ss", "srt",
    "skoid", "sktid", "skt", "ske", "sks", "skv", "saoid", "suoid", "scid", "sdd", "ses"})
_PATH_ACCESS = re.compile(
    r"(?:^|[/;?&#])(?:token|access[_-]?token|refresh[_-]?token|api[_-]?key|"
    r"password|secret|authorization|auth|credential|signature|sig|session(?:_?id)?|"
    r"jwt|client_secret|x[-_]amz[-_][a-z_-]+|x[-_]goog[-_][a-z_-]+)"
    r"(?:[/=:]|$)", re.I)


def _decoded_url_component(value):
    # Decode a bounded number of nested encodings for screening, never fetch.
    for _ in range(5):
        decoded = unquote(value, errors="strict")
        if decoded == value:
            return value
        value = decoded
    return None


def _access_bearing(parts):
    keys = set()
    for component in (parts.query, parts.path, parts.fragment):
        decoded = _decoded_url_component(component)
        if decoded is None or any(ord(c) < 32 or ord(c) == 127 for c in decoded):
            return True
        if _PATH_ACCESS.search(decoded):
            return True
        # Semicolon parameters and nested percent-encoded names must receive
        # the same decision as ordinary query names before any query stripping.
        pairs = parse_qsl(decoded.replace(";", "&"), keep_blank_values=True, max_num_fields=100)
        for key, _ in pairs:
            key = key.strip().lower()
            keys.add(key)
            if _SECRET_QUERY_KEY.fullmatch(key) or _SERVICE_ACCESS_KEY.fullmatch(key):
                return True
    return len(keys & _AZURE_ACCESS_KEYS) >= 2


def public_http_url(value: object, *, strip_query: bool = False) -> str | None:
    """Return a checked public URL, or None. Strip query/fragment for egress.

    Public domain resolution cannot be proven without a trusted resolver and
    redirect enforcement at the actual network executor. Known non-public
    address forms are rejected before any tool adapter is invoked.
    """
    if not isinstance(value, str) or not value or len(value) > 1800:
        return None
    if (any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
            or "\\" in value or re.search(r"%(?![0-9a-fA-F]{2})", value)):
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port  # Force validation of malformed/out-of-range ports.
        if (parts.scheme not in {"http", "https"} or not parts.netloc or not host
                or parts.username is not None or parts.password is not None
                or parts.netloc.endswith(":")):
            return None
        # A signed/credential-bearing URL is not public evidence. A normal
        # search query or section anchor may be projected without its query.
        if _access_bearing(parts):
            return None
        host = host.lower()
        if not host or host.endswith(".") or "%" in host or "\\" in host:
            return None
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            # Numeric dotted names can be interpreted as legacy IPv4 forms by
            # some resolvers even though ipaddress rejects them.
            if all(_NUMERIC_LABEL.fullmatch(label) for label in host.split(".")):
                return None
            ascii_host = host.encode("idna").decode("ascii")
            labels = ascii_host.split(".")
            if (len(labels) < 2 or len(ascii_host) > 253
                    or not all(_DOMAIN_LABEL.fullmatch(label) for label in labels)
                    or all(_NUMERIC_LABEL.fullmatch(label) for label in labels)):
                return None
            if any(ascii_host == suffix or ascii_host.endswith("." + suffix)
                   for suffix in _NONPUBLIC_SUFFIXES):
                return None
            host = ascii_host
        else:
            if (not address.is_global or address.is_multicast or address.is_reserved
                    or getattr(address, "ipv4_mapped", None) is not None):
                return None
            host = str(address)
            if address.version == 6:
                host = "[" + host + "]"
        if port is not None and port <= 0:
            return None
        netloc = host + ((":" + str(port)) if port is not None else "")
        if strip_query:
            return urlunsplit((parts.scheme, netloc, parts.path, "", ""))
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except (ValueError, UnicodeError):
        return None
