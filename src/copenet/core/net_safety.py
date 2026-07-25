"""Outbound-fetch safety primitives shared by the Barricade and the web ingestion service.

Resolves a hostname to its actual IP addresses and classifies them, so a
private/loopback/link-local/metadata target is caught even when it's reached
through a domain name (DNS rebinding) rather than a literal IP in the URL —
checking the URL text alone misses that case entirely.
"""

from __future__ import annotations

import ipaddress
import socket

_HOSTNAME_LITERALS_UNSAFE = {"localhost", "metadata", "metadata.google.internal"}


def is_private_ip(value: str) -> bool:
    """True when `value` is a private/loopback/link-local/reserved/multicast IP literal."""
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast


def hostname_resolves_unsafe(hostname: str | None) -> tuple[bool, str]:
    """Resolve `hostname` and report whether ANY resolved address is unsafe to fetch.

    Returns (unsafe, reason). A hostname that fails to resolve is treated as unsafe
    (fail closed) — there is no legitimate destination to distinguish it from an
    attacker-controlled one. This is what actually stops DNS rebinding: a domain name
    that currently resolves to 169.254.169.254 is caught here even though the URL
    itself never mentions a literal IP.
    """
    host = (hostname or "").strip().strip("[]").lower()
    if not host:
        return True, "empty hostname"
    if host in _HOSTNAME_LITERALS_UNSAFE:
        return True, f"'{host}' is a well-known internal/metadata alias"
    if is_private_ip(host):
        return True, f"'{host}' is a private/loopback/reserved IP literal"

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        return True, f"could not resolve '{host}': {exc}"

    for info in infos:
        sockaddr = info[4]
        addr = sockaddr[0] if sockaddr else ""
        if addr and is_private_ip(addr):
            return True, f"'{host}' resolves to private/loopback/reserved address {addr}"
    return False, ""
