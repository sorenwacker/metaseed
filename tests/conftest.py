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
def _private_datasets_dir(tmp_path_factory: pytest.TempPathFactory, monkeypatch):
    """Every test saves and deletes datasets in a directory of its own.

    The dataset repository honours ``METASEED_DATASETS_DIR``; without it, tests
    that save, list or delete datasets through the app operated on the user's
    real ``~/.local/share/metaseed/datasets`` -- test datasets appeared in the
    running UI, and one run's cleanup deleted the user's own saved datasets.
    Selenium tests start the server as a subprocess, which inherits this
    environment, so they are covered too.
    """
    monkeypatch.setenv(
        "METASEED_DATASETS_DIR", str(tmp_path_factory.mktemp("datasets"))
    )
    # The dataset factory is a session-wide binding whose repository resolves
    # the directory when it is created; a binding left by an earlier test
    # would keep pointing at that test's directory.
    from metaseed.ui.datasets import set_factory

    set_factory(None)
    yield
    set_factory(None)


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
