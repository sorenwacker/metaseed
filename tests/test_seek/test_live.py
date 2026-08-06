"""Live round-trip test against a running FAIRDOM-SEEK instance.

Marked ``network`` and skipped by the default test run. Point it at a running
SEEK (e.g. the local docker instance) with, for HTTP Basic auth::

    SEEK_URL=http://localhost:3001 SEEK_AUTH=admin:seek-admin-2026 \
        uv run pytest tests/test_seek/test_live.py -m network

It provisions the model (Controlled Vocabularies + Sample Types) from the ISA
profile, pushes a small dataset, and reads a resource back to confirm the round
trip. Requires SEEK's samples + ISA features enabled and at least one project.
"""

from __future__ import annotations

import os
import warnings

import pytest

pytestmark = pytest.mark.network


def _seek_client():
    url = os.environ.get("SEEK_URL")
    auth = os.environ.get("SEEK_AUTH")
    token = os.environ.get("SEEK_API_KEY")
    if not url or not (token or (auth and ":" in auth)):
        pytest.skip(
            "set SEEK_URL and either SEEK_API_KEY or SEEK_AUTH=login:password "
            "to run the live tests"
        )
    from metaseed.seek import SeekClient

    if token:
        return SeekClient(url, token=token)
    login, password = auth.split(":", 1)
    return SeekClient(url, auth=(login, password))


# Children before parents: SEEK rejects deleting a Study that still has Assays.
_DELETE_ORDER = ("samples", "data_files", "assays", "studies", "investigations")


class _CreatedInSeek:
    """The resources one test wrote, so teardown can remove exactly those."""

    def __init__(self) -> None:
        self._client = None
        self._ids: dict[str, list[str]] = {kind: [] for kind in _DELETE_ORDER}

    def track(self, client, result) -> None:
        """Register a :class:`SyncResult` for removal after the test."""
        self._client = client
        for kind in _DELETE_ORDER:
            self._ids[kind].extend(getattr(result, kind, {}).values())

    def remove_all(self) -> list[str]:
        if self._client is None:
            return []
        failures = []
        for kind in _DELETE_ORDER:
            for resource_id in self._ids[kind]:
                try:
                    self._client.delete(f"/{kind}/{resource_id}")
                except Exception as exc:
                    failures.append(f"{kind}/{resource_id}: {exc}")
        return failures


@pytest.fixture
def created_in_seek():
    """Delete whatever the test pushed, so runs do not accumulate in the instance.

    These tests create a fresh Investigation every run against a real SEEK. Left
    behind they pile up, and because several carry the same title they become hard
    to tell apart from records a person made -- so a later tidy-up risks deleting
    the wrong thing. Removing them here keeps that from ever arising.

    Teardown warns rather than fails: a resource that could not be deleted is
    worth knowing about, but must not turn a passing test red or mask a real one.
    """
    record = _CreatedInSeek()
    yield record
    failures = record.remove_all()
    if failures:
        warnings.warn(
            "left behind in SEEK (delete by hand): " + "; ".join(failures),
            stacklevel=1,
        )


def _dataset():
    from metaseed import MetaseedClient

    client = MetaseedClient("isa", "1.0")
    inv = client.create_entity(
        "Investigation",
        {"identifier": "INV-live", "title": "metaseed live-test"},
        skip_validation=True,
    )
    study = client.create_entity(
        "Study",
        {"identifier": "STU-live", "title": "live study"},
        parent_id=inv.id,
        skip_validation=True,
    )
    client.create_entity(
        "Sample", {"name": "live-sample"}, parent_id=study.id, skip_validation=True
    )
    return client


def test_provision_then_sync_round_trips(created_in_seek):
    from metaseed.seek import (
        build_provisioning_plan,
        execute_provisioning_plan,
        sync_dataset_to_seek,
    )
    from metaseed.specs.loader import SpecLoader

    seek = _seek_client()
    project_id = seek.default_project_id()
    ms_client = _dataset()

    # Phase 1 — provision the model from the profile.
    profile = SpecLoader().load_profile(ms_client.version, ms_client.profile)
    plan = build_provisioning_plan(profile)
    provisioned = execute_provisioning_plan(seek, plan, project_id=project_id)
    assert provisioned.sample_type_ids  # at least one Sample Type exists

    # Phase 2 — push the dataset.
    result = sync_dataset_to_seek(
        seek,
        ms_client,
        project_id=project_id,
        sample_type_ids=provisioned.sample_type_ids,
    )
    created_in_seek.track(seek, result)
    assert not result.errors, result.errors
    assert result.investigations  # an Investigation was created

    # The Investigation reads back with our title.
    inv_id = next(iter(result.investigations.values()))
    inv = seek.get(f"/investigations/{inv_id}")
    assert inv["data"]["attributes"]["title"] == "metaseed live-test"


def _dataset_with_sample_under_assay():
    """The same ISA shape, but the Sample hangs off the Assay as SEEK models it."""
    from metaseed import MetaseedClient

    client = MetaseedClient("isa", "1.0")
    inv = client.create_entity(
        "Investigation",
        {"identifier": "INV-live-assay", "title": "metaseed live-test"},
        skip_validation=True,
    )
    study = client.create_entity(
        "Study",
        {"identifier": "STU-live-assay", "title": "live study"},
        parent_id=inv.id,
        skip_validation=True,
    )
    assay = client.create_entity(
        "Assay",
        {"identifier": "ASY-live", "title": "live assay"},
        parent_id=study.id,
        skip_validation=True,
    )
    # The isa profile's Sample carries a required ``study_id`` field, which
    # provisioning turns into a required SEEK sample attribute. Nesting the
    # Sample under the Assay leaves it unset, so supply it explicitly.
    client.create_entity(
        "Sample",
        {"name": "live-sample", "study_id": "STU-live-assay"},
        parent_id=assay.id,
        skip_validation=True,
    )
    return client


def _provision_and_sync(seek, ms_client, created_in_seek):
    from metaseed.seek import (
        build_provisioning_plan,
        execute_provisioning_plan,
        sync_dataset_to_seek,
    )
    from metaseed.specs.loader import SpecLoader

    project_id = seek.default_project_id()
    profile = SpecLoader().load_profile(ms_client.version, ms_client.profile)
    plan = build_provisioning_plan(profile)
    provisioned = execute_provisioning_plan(seek, plan, project_id=project_id)
    result = sync_dataset_to_seek(
        seek,
        ms_client,
        project_id=project_id,
        sample_type_ids=provisioned.sample_type_ids,
    )
    created_in_seek.track(seek, result)
    assert not result.errors, result.errors
    return result


def _isa_links(seek, sample_id):
    rels = seek.get(f"/samples/{sample_id}")["data"].get("relationships") or {}
    return {
        name
        for name in ("assays", "studies", "investigations")
        if (rels.get(name) or {}).get("data")
    }


def test_a_sample_under_an_assay_is_linked_into_the_isa_tree(created_in_seek):
    """A Sample with an Assay ancestor must come back attached to it.

    SEEK hangs Samples off Assays and derives their Study and Investigation from
    that link. A sync that creates the Sample without it leaves a record reachable
    only by listing the project's samples, which a re-import cannot find.
    """
    seek = _seek_client()
    result = _provision_and_sync(
        seek, _dataset_with_sample_under_assay(), created_in_seek
    )
    assert result.samples, "the dataset has a Sample; the sync reported none created"
    assert not result.unlinked, (
        "the Sample sits under an Assay, so it should have been linked: "
        f"{result.unlinked}"
    )

    for node_id, sample_id in result.samples.items():
        links = _isa_links(seek, sample_id)
        assert "assays" in links, (
            f"{node_id} -> SEEK sample {sample_id} was created without an Assay "
            f"link (has: {sorted(links)})"
        )


def test_a_sample_with_no_assay_ancestor_is_reported_not_silently_orphaned(
    created_in_seek,
):
    """When a Sample cannot be linked, the result must say so.

    SEEK accepts only an ``assays`` association on a Sample -- it ignores
    ``studies`` -- so a Sample nested directly under a Study cannot be placed in
    the ISA tree at all. That is a limitation to report, not to hide: the record
    exists in SEEK but nothing walking down from the Investigation reaches it, and
    a re-import drops it. The failure this guards against is a ``SyncResult`` that
    counts such a Sample as created and says nothing else.
    """
    seek = _seek_client()
    result = _provision_and_sync(seek, _dataset(), created_in_seek)
    assert result.samples, "the dataset has a Sample; the sync reported none created"

    unreachable = [
        node_id
        for node_id, sample_id in result.samples.items()
        if not _isa_links(seek, sample_id)
    ]
    reported = {node_id for node_id, _ in result.unlinked}
    assert set(unreachable) <= reported, (
        "these Samples were created in SEEK with no ISA link and were not reported "
        f"in SyncResult.unlinked: {sorted(set(unreachable) - reported)}"
    )
