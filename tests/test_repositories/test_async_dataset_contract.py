"""The async dataset contract is public API -- metaseed-hub implements it.

This exists because the class was once removed as "0 impls, 0 callers": the
only implementation lives in a *different repository*, so a grep of this repo
alone will always conclude it is unused. These tests are the standing evidence
that it is not.
"""

from __future__ import annotations

import inspect

from metaseed.repositories import AsyncDatasetRepository, DatasetData, DatasetInfo


def test_async_dataset_repository_is_exported() -> None:
    """Downstream imports `from metaseed.repositories import AsyncDatasetRepository`."""
    from metaseed import repositories

    assert "AsyncDatasetRepository" in repositories.__all__


def test_contract_methods_are_async_and_complete() -> None:
    """The five storage operations a database-backed host must implement."""
    assert AsyncDatasetRepository.__abstractmethods__ == frozenset(
        {"list", "save", "load", "delete", "exists"}
    )
    for name in AsyncDatasetRepository.__abstractmethods__:
        assert inspect.iscoroutinefunction(getattr(AsyncDatasetRepository, name)), (
            f"{name} must be async: the interface exists for async backends"
        )


def test_validate_name_is_inherited_behaviour_not_just_an_interface() -> None:
    """Implementations rely on this being provided, not re-implemented."""
    assert AsyncDatasetRepository.validate_name("good-name") is None
    assert AsyncDatasetRepository.validate_name("../escape") is not None


def test_a_conforming_implementation_satisfies_the_contract() -> None:
    """A minimal subclass instantiates -- the shape downstream depends on."""

    class _Impl(AsyncDatasetRepository):
        async def list(self) -> list[DatasetInfo]:
            return []

        async def save(self, name: str, data: DatasetData) -> DatasetInfo:
            return DatasetInfo(
                name=name, profile="miappe", version="1.2", entity_count=0, modified=""
            )

        async def load(self, name: str) -> DatasetData:
            raise FileNotFoundError(name)

        async def delete(self, name: str) -> bool:
            return False

        async def exists(self, name: str) -> bool:
            return False

    assert isinstance(_Impl(), AsyncDatasetRepository)
