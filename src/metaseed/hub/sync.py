"""Push and pull rules between this instance and a metaseed-hub.

Everything here is decided on data and reported before anything is sent:
what a push would create, replace or leave alone; where a pull lands. The
hub is reached only through the small :class:`HubApi` protocol, so the rules
are testable without a network and the UI shows exactly what these say.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from metaseed.repositories.dataset_repository import DatasetData

# Suffix a pulled dataset gets when a differing local one holds its name.
PULLED_BESIDE_SUFFIX = "-hub"

DIRECTIONS = ("push", "pull")


class HubApi(Protocol):
    """What the sync needs from a hub client."""

    url: str

    def me(self) -> dict[str, str]: ...

    def list_datasets(self, tenant_id: str) -> list[dict[str, Any]]: ...

    def get_dataset(self, dataset_id: str) -> dict[str, Any]: ...

    def create_dataset(
        self,
        *,
        tenant_id: str,
        name: str,
        profile: str,
        version: str,
        data: dict[str, Any],
    ) -> dict[str, Any]: ...

    def update_dataset(
        self, dataset_id: str, *, data: dict[str, Any]
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class HubRecord:
    """A hub dataset as the pull list shows it."""

    id: str
    name: str
    profile: str
    version: str
    entities: list[dict[str, Any]]

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> HubRecord:
        """Build from one ``/api/datasets`` row."""
        return cls(
            id=row["id"],
            name=row["name"],
            profile=row["profile"],
            version=row["version"],
            entities=list((row.get("data") or {}).get("entities") or []),
        )

    @property
    def entity_count(self) -> int:
        return len(self.entities)

    def as_dataset(self, name: str) -> DatasetData:
        """The record as a local dataset under ``name``."""
        return DatasetData(
            name=name,
            profile=self.profile,
            version=self.version,
            entities=list(self.entities),
        )


def _key(entity: dict[str, Any]) -> str:
    """How an entity is named in a push report: its type and identifier."""
    ident = next(
        (
            str(entity[k])
            for k in ("identifier", "id", "name", "title")
            if k in entity and entity[k] not in (None, "")
        ),
        "",
    )
    return f"{entity.get('_type', '?')} {ident}".strip()


def _canonical(entity: dict[str, Any]) -> str:
    return json.dumps(entity, sort_keys=True, default=str)


@dataclass
class PushPlan:
    """What a push would do, before it does it."""

    kind: str
    """``create`` (the hub lacks the name), ``identical`` or ``differs``."""
    remote_id: str | None = None
    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    counts: dict[str, tuple[int, int]] = field(default_factory=dict)
    """Entity type -> (local count, hub count)."""


def plan_dataset_push(local: DatasetData, remote: dict[str, Any] | None) -> PushPlan:
    """Compare the local dataset with the hub's row of the same name.

    Args:
        local: The dataset as saved here.
        remote: The hub's row (``/api/datasets`` shape), or None when the hub
            has no dataset of that name.
    """
    if remote is None:
        return PushPlan(kind="create", added=[_key(e) for e in local.entities])
    theirs = HubRecord.from_row(remote).entities
    mine_by = {_key(e): _canonical(e) for e in local.entities}
    theirs_by = {_key(e): _canonical(e) for e in theirs}
    added = [k for k in mine_by if k not in theirs_by]
    removed = [k for k in theirs_by if k not in mine_by]
    changed = [k for k in mine_by if k in theirs_by and mine_by[k] != theirs_by[k]]
    counts: dict[str, tuple[int, int]] = {}
    for t in sorted({e.get("_type", "?") for e in [*local.entities, *theirs]}):
        counts[t] = (
            sum(1 for e in local.entities if e.get("_type") == t),
            sum(1 for e in theirs if e.get("_type") == t),
        )
    kind = "identical" if not (added or removed or changed) else "differs"
    return PushPlan(
        kind=kind,
        remote_id=remote["id"],
        added=added,
        changed=changed,
        removed=removed,
        counts=counts,
    )


def provenance(hub: HubApi, *, direction: str) -> dict[str, str]:
    """Where a dataset came from or went: the hub, the account, when.

    Raises:
        ValueError: If ``direction`` is not ``push`` or ``pull``.
    """
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}, not {direction!r}")
    me = hub.me()
    return {
        "hub": hub.url,
        "account": me.get("email", ""),
        "direction": direction,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


@dataclass
class PushOutcome:
    """What a push did."""

    kind: str
    """``create``, ``replaced``, ``identical``, or ``differs`` (not sent)."""
    plan: PushPlan
    remote_id: str | None = None
    provenance: dict[str, str] | None = None


def find_remote_by_name(hub: HubApi, name: str) -> dict[str, Any] | None:
    """The hub's dataset of this name in the caller's tenant, if any."""
    tenant_id = hub.me()["tenant_id"]
    for row in hub.list_datasets(tenant_id):
        if row["name"] == name:
            return hub.get_dataset(row["id"])
    return None


def push_dataset(
    hub: HubApi, local: DatasetData, *, replace: bool = False
) -> PushOutcome:
    """Push ``local`` to the hub.

    A name the hub lacks is created; identical content is not sent; differing
    content is sent only with ``replace``.

    Args:
        hub: The hub client.
        local: The dataset as saved here.
        replace: Replace a differing hub dataset of the same name.
    """
    remote = find_remote_by_name(hub, local.name)
    plan = plan_dataset_push(local, remote)
    data = {"entities": list(local.entities)}
    if plan.kind == "create":
        row = hub.create_dataset(
            tenant_id=hub.me()["tenant_id"],
            name=local.name,
            profile=local.profile,
            version=local.version,
            data=data,
        )
        return PushOutcome("create", plan, row["id"], provenance(hub, direction="push"))
    if plan.kind == "identical" or not replace:
        return PushOutcome(plan.kind, plan, plan.remote_id)
    assert plan.remote_id is not None
    hub.update_dataset(plan.remote_id, data=data)
    return PushOutcome(
        "replaced", plan, plan.remote_id, provenance(hub, direction="push")
    )


@dataclass(frozen=True)
class PullTarget:
    """Where a pulled dataset lands."""

    kind: str
    """``new`` (no local dataset of that name), ``identical`` (nothing to
    write), or ``beside`` (saved under the ``-hub`` name)."""
    name: str


def dataset_pull_target(record: HubRecord, local: DatasetData | None) -> PullTarget:
    """Decide where ``record`` is saved, given the local dataset of its name."""
    if local is None:
        return PullTarget("new", record.name)
    mine = sorted(_canonical(e) for e in local.entities)
    theirs = sorted(_canonical(e) for e in record.entities)
    if mine == theirs and (local.profile, local.version) == (
        record.profile,
        record.version,
    ):
        return PullTarget("identical", record.name)
    return PullTarget("beside", f"{record.name}{PULLED_BESIDE_SUFFIX}")


def local_counterpart(store: Any, name: str) -> DatasetData | None:
    """The local dataset a hub record would meet, if there can be one.

    A hub name need not be a name this store can hold -- it may carry a space
    or a separator -- and asking the store about one of those raises rather
    than answering (deliberately: that check is what stops a crafted name
    escaping the datasets directory). A listing compares many names, so it
    asks here: an impossible name simply has no local counterpart.

    Args:
        store: The dataset repository.
        name: The hub record's name.

    Returns:
        The stored dataset of that name, or None when there is none -- or when
        the name is not one this store could ever hold.
    """
    if store.validate_name(name):
        return None
    loaded: DatasetData | None = store.load(name) if store.exists(name) else None
    return loaded


def list_hub_datasets(hub: HubApi) -> list[HubRecord]:
    """The caller's hub datasets, for the pull list."""
    tenant_id = hub.me()["tenant_id"]
    return [HubRecord.from_row(row) for row in hub.list_datasets(tenant_id)]
