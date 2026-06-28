"""Shared pytest fixtures.

Blocks real outbound network during the test suite so it stays fast and
deterministic. A test that genuinely needs the network (e.g. a live EBI OLS
lookup) must be marked ``@pytest.mark.network``; the pre-push hook excludes
those (``-m "not network"``), and they are allowed through the guard.

Without this, tests that hit the ontology service on a cache miss made real
HTTP calls with a 30s timeout each, hanging the suite when connectivity is poor.
"""

from __future__ import annotations

import socket

import pytest

_real_connect = socket.socket.connect
_LOOPBACK = {"127.0.0.1", "::1", "localhost", ""}


@pytest.fixture(autouse=True)
def _block_external_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail fast on real outbound connections unless the test is marked network.

    Loopback connections are allowed (in-process servers); the FastAPI
    ``TestClient`` uses an in-memory ASGI transport and is unaffected.
    """
    if request.node.get_closest_marker("network"):
        return

    def guarded_connect(self: socket.socket, address: object) -> object:
        host = address[0] if isinstance(address, tuple) else address
        if host not in _LOOPBACK:
            raise RuntimeError(
                f"Blocked a real network connection to {host!r} during a test. "
                "Mock the call, or mark the test with @pytest.mark.network."
            )
        return _real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
