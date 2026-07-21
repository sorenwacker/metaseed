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

import pytest

pytestmark = pytest.mark.network


def _seek_client():
    url = os.environ.get("SEEK_URL")
    auth = os.environ.get("SEEK_AUTH")
    if not url or not auth or ":" not in auth:
        pytest.skip("set SEEK_URL and SEEK_AUTH=login:password to run the live test")
    from metaseed.seek import SeekClient

    login, password = auth.split(":", 1)
    return SeekClient(url, auth=(login, password))


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


def test_provision_then_sync_round_trips():
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
    assert not result.errors, result.errors
    assert result.investigations  # an Investigation was created

    # The Investigation reads back with our title.
    inv_id = next(iter(result.investigations.values()))
    inv = seek.get(f"/investigations/{inv_id}")
    assert inv["data"]["attributes"]["title"] == "metaseed live-test"
