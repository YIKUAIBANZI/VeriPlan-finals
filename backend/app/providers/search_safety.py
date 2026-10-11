"""Pure URL and domain policy helpers for external search evidence."""

import ipaddress
import re
import unicodedata
from urllib.parse import unquote_plus, urlsplit, urlunsplit


_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_IP_LIKE_LABEL = re.compile(r"^(?:0x[0-9a-f]+|0[0-7]*|[0-9]+)$", re.IGNORECASE)
_LOCAL_SUFFIXES = ("localhost", "local", "internal", "home", "lan")
_TRACKING_KEYS = {"gclid", "fbclid", "mc_cid", "mc_eid"}


def _contains_control_characters(value: str) -> bool:
    return any(unicodedata.category(character).startswith("C") for character in value)


def _looks_like_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        labels = host.split(".")
        return bool(labels) and all(_IP_LIKE_LABEL.fullmatch(label) for label in labels)
    return True


def _normalize_public_host(value: str) -> str:
    if not value or _contains_control_characters(value):
        raise ValueError("host is missing or contains control characters")
    try:
        host = value.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise ValueError("host is not valid IDNA") from error
    labels = host.split(".")
    if len(labels) < 2 or len(host) > 253:
        raise ValueError("host must be a public multi-label domain")
    if any(not _HOST_LABEL.fullmatch(label) for label in labels):
        raise ValueError("host contains an invalid DNS label")
    if _looks_like_ip_address(host):
        raise ValueError("IP addresses are not allowed")
    if any(host == suffix or host.endswith(f".{suffix}") for suffix in _LOCAL_SUFFIXES):
        raise ValueError("local host names are not allowed")
    return host


def normalize_domains(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw_value in values:
        value = raw_value.strip()
        if not value:
            continue
        if any(character in value for character in "/:@*?#[\\]"):
            raise ValueError("domain configuration must contain host names only")
        host = _normalize_public_host(value)
        if host not in normalized:
            normalized.append(host)
    return tuple(normalized)


def host_matches_domain(host: str, domain: str) -> bool:
    host = host.lower().rstrip(".")
    domain = domain.lower().rstrip(".")
    return host == domain or host.endswith(f".{domain}")


def canonicalize_public_https_url(
    value: str,
    *,
    blocked_domains: tuple[str, ...] = (),
) -> str:
    if not isinstance(value, str) or _contains_control_characters(value):
        raise ValueError("URL contains control characters")
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as error:
        raise ValueError("URL is malformed") from error
    if parsed.scheme.lower() != "https":
        raise ValueError("URL must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL userinfo is not allowed")
    try:
        host = _normalize_public_host(parsed.hostname or "")
    except ValueError as error:
        raise ValueError("URL host is not public") from error
    if any(host_matches_domain(host, domain) for domain in normalize_domains(blocked_domains)):
        raise ValueError("URL host is blocked")

    netloc = host if port in {None, 443} else f"{host}:{port}"
    kept_query_parts: list[str] = []
    for part in parsed.query.split("&"):
        if not part:
            continue
        key = unquote_plus(part.partition("=")[0]).lower()
        if key.startswith("utm_") or key in _TRACKING_KEYS:
            continue
        kept_query_parts.append(part)
    return urlunsplit(
        (
            "https",
            netloc,
            parsed.path,
            "&".join(kept_query_parts),
            "",
        )
    )
