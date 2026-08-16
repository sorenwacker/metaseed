"""Abstract storage port for spec-builder drafts.

A draft is an identified, versioned spec-in-progress -- a serialized
``SpecBuilderState`` (stored as ``spec_data``). This port lets the spec builder
run against any backend: metaseed's default in-memory/file store for single-user
use, or a database adapter a consumer injects (e.g. metaseed-hub's per-tenant
SQLAlchemy store).

Like ``AsyncDatasetRepository``, a store instance is **scoped to its caller by
construction** -- a consumer builds one per authenticated user/tenant, so every
method only ever sees drafts that caller may access. This is the storage half of
the toolbox/ports design (metaseed#168); the MCP ``spec_*`` tools and the hub UI
both drive the spec builder through it.
"""

from __future__ import annotations

import copy
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SpecDraftInfo:
    """Summary of a draft, for listing without loading the full spec."""

    id: str
    name: str
    version: str
    modified: str = ""


@dataclass
class SpecDraftData:
    """Full draft contents: the serialized ``SpecBuilderState``."""

    id: str
    name: str
    version: str
    spec_data: dict[str, Any] = field(default_factory=dict)
    modified: str = ""


class AsyncSpecDraftStore(ABC):
    """Abstract async storage for spec-builder drafts, scoped to the caller.

    Implementations back this with a database, filesystem, etc. Not-found is a
    ``KeyError``; a store that also enforces access raises ``KeyError`` for a
    draft the caller may not see (so absence and denial are indistinguishable).
    """

    @abstractmethod
    async def list(self) -> list[SpecDraftInfo]:
        """List the caller's drafts, most-recently-modified first."""

    @abstractmethod
    async def create(
        self, name: str, version: str, spec_data: dict[str, Any]
    ) -> SpecDraftData:
        """Create a new draft and return it with its assigned id."""

    @abstractmethod
    async def load(self, draft_id: str) -> SpecDraftData:
        """Load a draft by id. Raises ``KeyError`` if it does not exist."""

    @abstractmethod
    async def save(
        self, draft_id: str, name: str, version: str, spec_data: dict[str, Any]
    ) -> SpecDraftData:
        """Persist a draft's state. Raises ``KeyError`` if it does not exist."""

    @abstractmethod
    async def delete(self, draft_id: str) -> bool:
        """Delete a draft. Returns True if deleted, False if not found."""

    @abstractmethod
    async def exists(self, draft_id: str) -> bool:
        """Return whether a draft exists."""


class MemorySpecDraftStore(AsyncSpecDraftStore):
    """In-memory default adapter -- the toolbox's zero-config store.

    Suitable for single-user use and tests. ``now`` is injectable so callers
    (and tests) control the ``modified`` timestamp.
    """

    def __init__(self, now: Callable[[], str] | None = None) -> None:
        self._drafts: dict[str, SpecDraftData] = {}
        self._now = now or _utc_now

    async def list(self) -> list[SpecDraftInfo]:
        drafts = sorted(self._drafts.values(), key=lambda d: d.modified, reverse=True)
        return [SpecDraftInfo(d.id, d.name, d.version, d.modified) for d in drafts]

    async def create(
        self, name: str, version: str, spec_data: dict[str, Any]
    ) -> SpecDraftData:
        draft = SpecDraftData(
            id=str(uuid.uuid4()),
            name=name,
            version=version,
            spec_data=spec_data,
            modified=self._now(),
        )
        self._drafts[draft.id] = draft
        # A copy, like every other repository here returns: handing out the
        # stored object let a caller mutate the store without saving, so an
        # abandoned edit persisted and a save became a no-op.
        return copy.deepcopy(draft)

    async def load(self, draft_id: str) -> SpecDraftData:
        if draft_id not in self._drafts:
            raise KeyError(draft_id)
        return copy.deepcopy(self._drafts[draft_id])

    async def save(
        self, draft_id: str, name: str, version: str, spec_data: dict[str, Any]
    ) -> SpecDraftData:
        if draft_id not in self._drafts:
            raise KeyError(draft_id)
        draft = SpecDraftData(
            id=draft_id,
            name=name,
            version=version,
            spec_data=spec_data,
            modified=self._now(),
        )
        self._drafts[draft_id] = draft
        return draft

    async def delete(self, draft_id: str) -> bool:
        return self._drafts.pop(draft_id, None) is not None

    async def exists(self, draft_id: str) -> bool:
        return draft_id in self._drafts


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
