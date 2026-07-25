"""Refusing the default gateway token when bound beyond loopback.

Confirmed audit finding (2026-07-24, A-001): COPNET_TOKEN defaults to the
well-known literal "dev-token", so binding beyond 127.0.0.1 (e.g.
COPNET_HOST=tailscale) with no operator-set token would let anyone who can
reach the port authenticate as a full-access operator. See docs/audit/.
"""

from __future__ import annotations

from copenet.host.main import _default_token_beyond_loopback_refusal


def test_loopback_bind_is_always_allowed_even_without_a_token() -> None:
    assert (
        _default_token_beyond_loopback_refusal(host="127.0.0.1", port=17123, token="", host_env=None)
        is None
    )


def test_non_loopback_bind_with_no_token_is_refused() -> None:
    refusal = _default_token_beyond_loopback_refusal(
        host="100.64.0.1", port=17123, token="", host_env="tailscale"
    )
    assert refusal is not None
    assert "COPNET_TOKEN" in refusal
    assert "tailscale" in refusal  # tells the operator how to restart


def test_non_loopback_bind_with_an_operator_token_is_allowed() -> None:
    assert (
        _default_token_beyond_loopback_refusal(
            host="100.64.0.1", port=17123, token="a-real-secret-token", host_env="tailscale"
        )
        is None
    )
