"""Push and pull between a metaseed instance and a metaseed-hub.

The hub is a fake here: a dict of datasets and specs behind the same methods
``HubClient`` offers. The rules under test are the ones the guide states —
identical content is not sent, differing content is shown and replaced only
when chosen, a pulled dataset never overwrites a differing local one, and a
profile lands at its own name and version.
"""

from __future__ import annotations

from typing import Any

import pytest

from metaseed.hub.sync import (
    HubRecord,
    dataset_pull_target,
    plan_dataset_push,
    provenance,
    push_dataset,
)
from metaseed.repositories.dataset_repository import DatasetData

ENTITIES = [
    {"_type": "Investigation", "identifier": "I1", "title": "inv"},
    {"_type": "Study", "identifier": "S1", "title": "study", "_parent_unique_id": "I1"},
]


class _FakeHub:
    """The subset of HubClient the sync uses, over in-memory records."""

    def __init__(self, datasets: list[dict[str, Any]] | None = None) -> None:
        self.url = "https://hub.test"
        self.datasets = datasets or []
        self.created: list[dict[str, Any]] = []
        self.updated: list[tuple[str, dict[str, Any]]] = []

    def me(self) -> dict[str, str]:
        return {
            "email": "me@example.org",
            "name": "Me",
            "tenant_id": "t1",
            "tenant_name": "T",
        }

    def list_datasets(self, tenant_id: str) -> list[dict[str, Any]]:
        return [d for d in self.datasets if d["tenant_id"] == tenant_id]

    def get_dataset(self, dataset_id: str) -> dict[str, Any]:
        return next(d for d in self.datasets if d["id"] == dataset_id)

    def create_dataset(
        self,
        *,
        tenant_id: str,
        name: str,
        profile: str,
        version: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        row = {
            "id": f"d{len(self.datasets) + 1}",
            "tenant_id": tenant_id,
            "name": name,
            "profile": profile,
            "version": version,
            "data": data,
        }
        self.datasets.append(row)
        self.created.append(row)
        return row

    def update_dataset(
        self, dataset_id: str, *, data: dict[str, Any]
    ) -> dict[str, Any]:
        row = self.get_dataset(dataset_id)
        row["data"] = data
        self.updated.append((dataset_id, data))
        return row


def _local(
    entities: list[dict[str, Any]] = ENTITIES, name: str = "test-drought"
) -> DatasetData:
    return DatasetData(name=name, profile="isa", version="1.0", entities=list(entities))


def _remote(
    entities: list[dict[str, Any]], name: str = "test-drought"
) -> dict[str, Any]:
    return {
        "id": "d1",
        "tenant_id": "t1",
        "name": name,
        "profile": "isa",
        "version": "1.0",
        "data": {"entities": list(entities)},
    }


class TestPlanningAPush:
    def test_a_dataset_the_hub_lacks_is_created(self) -> None:
        plan = plan_dataset_push(_local(), remote=None)
        assert plan.kind == "create"
        assert plan.added == ["Investigation I1", "Study S1"]

    def test_identical_content_sends_nothing(self) -> None:
        plan = plan_dataset_push(_local(), remote=_remote(ENTITIES))
        assert plan.kind == "identical"
        assert not plan.added and not plan.changed and not plan.removed

    def test_differing_content_is_described_before_anything_is_sent(self) -> None:
        remote = _remote(
            [
                ENTITIES[0],
                {**ENTITIES[1], "title": "old"},
                {"_type": "Study", "identifier": "S2"},
            ]
        )
        plan = plan_dataset_push(_local(), remote=remote)
        assert plan.kind == "differs"
        assert plan.changed == ["Study S1"]
        assert plan.removed == ["Study S2"]
        assert plan.added == []
        assert plan.counts == {"Investigation": (1, 1), "Study": (1, 2)}

    def test_a_field_order_difference_is_not_a_difference(self) -> None:
        reordered = [dict(reversed(list(e.items()))) for e in ENTITIES]
        assert (
            plan_dataset_push(_local(), remote=_remote(reordered)).kind == "identical"
        )


class TestPushing:
    def test_a_new_dataset_lands_in_the_callers_tenant(self) -> None:
        hub = _FakeHub()
        outcome = push_dataset(hub, _local())
        assert outcome.kind == "create"
        (row,) = hub.created
        assert (row["tenant_id"], row["name"], row["profile"], row["version"]) == (
            "t1",
            "test-drought",
            "isa",
            "1.0",
        )
        assert row["data"] == {"entities": ENTITIES}
        assert outcome.provenance == provenance(hub, direction="push")

    def test_identical_content_is_not_sent(self) -> None:
        hub = _FakeHub([_remote(ENTITIES)])
        outcome = push_dataset(hub, _local())
        assert outcome.kind == "identical"
        assert not hub.updated and not hub.created

    def test_differing_content_is_replaced_only_when_chosen(self) -> None:
        hub = _FakeHub([_remote([ENTITIES[0]])])
        refused = push_dataset(hub, _local())
        assert refused.kind == "differs"
        assert not hub.updated
        replaced = push_dataset(hub, _local(), replace=True)
        assert replaced.kind == "replaced"
        assert hub.updated == [("d1", {"entities": ENTITIES})]


class TestPulling:
    def test_a_name_the_instance_lacks_is_saved_under_it(self) -> None:
        target = dataset_pull_target(HubRecord.from_row(_remote(ENTITIES)), local=None)
        assert target.name == "test-drought"
        assert target.kind == "new"

    def test_an_identical_local_dataset_is_left_alone(self) -> None:
        target = dataset_pull_target(
            HubRecord.from_row(_remote(ENTITIES)), local=_local()
        )
        assert target.kind == "identical"

    def test_a_differing_local_dataset_is_never_overwritten(self) -> None:
        target = dataset_pull_target(
            HubRecord.from_row(_remote([ENTITIES[0]])), local=_local()
        )
        assert target.kind == "beside"
        assert target.name == "test-drought-hub"

    def test_the_pulled_record_keeps_profile_and_version(self) -> None:
        record = HubRecord.from_row(_remote(ENTITIES))
        assert (record.profile, record.version, record.entity_count) == (
            "isa",
            "1.0",
            2,
        )


def test_provenance_names_the_hub_the_account_the_direction_and_the_time() -> None:
    stamp = provenance(_FakeHub(), direction="pull")
    assert stamp["hub"] == "https://hub.test"
    assert stamp["account"] == "me@example.org"
    assert stamp["direction"] == "pull"
    assert stamp["at"][:2] == "20"


@pytest.mark.parametrize("direction", ["up", ""])
def test_a_direction_that_is_not_push_or_pull_is_refused(direction: str) -> None:
    with pytest.raises(ValueError):
        provenance(_FakeHub(), direction=direction)
