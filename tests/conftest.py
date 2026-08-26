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
def _models_are_not_shared_between_tests():
    """Each test generates its own models rather than inheriting them.

    Models are cached globally by ``profile:version:name`` so validation can
    resolve a nested entity at deserialization time. Two tests that build the
    same profile name from different specs therefore hand each other the wrong
    model, and the second one sees "Extra inputs are not permitted" for a
    field its own spec defines. Clearing the registry between tests keeps that
    a property of one test rather than of the order they ran in.
    """
    from metaseed.models.factory import get_global_context

    context = get_global_context()
    context._models.clear()
    yield
    context._models.clear()


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
def _test_datasets_are_named_for_what_they_are(monkeypatch):
    """A dataset a test creates is named ``test-<what it is>``.

    Datasets tests made used to be called ``inv1``, ``doe``, ``i``, ``s1`` --
    indistinguishable from a person's work when they showed up in a datasets
    directory (which, before the isolation fixture above, was the user's).
    The gate is on the write itself, so any path -- the UI route, the MCP
    tool, the repository -- is covered; a name the application chooses for
    a loaded example (``<profile>-<version>-example``) is exempt.
    """
    from metaseed.repositories.filesystem_dataset import FilesystemDatasetRepository
    from metaseed.ui.dataset_manager import DatasetManager

    original_save = FilesystemDatasetRepository.save
    original_auto_save = DatasetManager.auto_save
    autosaving = {"depth": 0}

    def named_save(self, name, data):
        # The application names an auto-saved dataset after its root entity
        # and a loaded example after its profile; those are its choices, not
        # the test's, and are not gated.
        # A name the repository rejects anyway is its error to raise.
        if (
            autosaving["depth"] == 0
            and self.validate_name(name) is None
            and not name.startswith("test-")
            and not name.endswith("-example")
        ):
            raise AssertionError(
                f"a test created a dataset named {name!r}; name it "
                "'test-<what it is>' so it cannot be mistaken for a person's work"
            )
        return original_save(self, name, data)

    def counted_auto_save(self):
        autosaving["depth"] += 1
        try:
            return original_auto_save(self)
        finally:
            autosaving["depth"] -= 1

    monkeypatch.setattr(FilesystemDatasetRepository, "save", named_save)
    monkeypatch.setattr(DatasetManager, "auto_save", counted_auto_save)


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
