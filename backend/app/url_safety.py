"""URL safety helpers — SSRF protections for outbound fetches."""

from __future__ import annotations

import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse


_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
        return True
    for net in _BLOCKED_NETWORKS:
        if ip in net:
            return True
    # Cloud metadata commonly used
    if str(ip) in ("169.254.169.254", "metadata.google.internal"):
        return True
    return False


def is_public_http_url(url: str) -> bool:
    """True if URL is http(s) with a hostname that does not resolve to private IPs."""
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    if host.lower() in ("localhost", "metadata.google.internal"):
        return False
    try:
        # Resolve all addresses; reject if any are blocked (DNS rebinding basic check)
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    if not infos:
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if _is_blocked_ip(ip):
            return False
    return True


def assert_safe_fetch_url(url: str) -> Optional[str]:
    """Return None if safe, else an error message."""
    if not (url or "").strip().startswith(("http://", "https://")):
        return "URL must be http(s)"
    if not is_public_http_url(url):
        return "URL host is not allowed (private/metadata/localhost blocked)"
    return None
