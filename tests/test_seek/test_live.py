"""Live round-trip test against a running FAIRDOM-SEEK instance.

Marked ``network`` and skipped by the default test run. Point it at a running
SEEK (e.g. the local docker instance) with, for HTTP Basic auth::

    SEEK_URL=http://localhost:3001 SEEK_AUTH=admin:seek-admin-2026 \
        uv run pytest tests/test_seek/test_live.py -m network

It creates a minimal experiment and reads each resource back to confirm the
hierarchy and relationships survived the round trip.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.network


def _client():
    url = os.environ.get("SEEK_URL")
    auth = os.environ.get("SEEK_AUTH")
    if not url or not auth or ":" not in auth:
        pytest.skip("set SEEK_URL and SEEK_AUTH=login:password to run the live test")
    from metaseed.seek import SeekClient

    login, password = auth.split(":", 1)
    return SeekClient(url, auth=(login, password))


def test_push_minimal_experiment_round_trips():
    from metaseed.seek import push_minimal_experiment

    client = _client()
    ids = push_minimal_experiment(client, title_prefix="metaseed live-test")

    # Each resource is readable and linked to its parent.
    study = client.get(f"/studies/{ids.study}")
    assert (
        study["data"]["relationships"]["investigation"]["data"]["id"]
        == ids.investigation
    )

    assay = client.get(f"/assays/{ids.assay}")
    assert assay["data"]["relationships"]["study"]["data"]["id"] == ids.study

    sample = client.get(f"/samples/{ids.sample}")
    assert (
        sample["data"]["relationships"]["sample_type"]["data"]["id"]
        == ids.sample_type
    )
    # SEEK is asymmetric: values are POSTed under attributes.data but read back
    # under attributes.attribute_map.
    assert sample["data"]["attributes"]["attribute_map"]["name"].startswith(
        "metaseed live-test"
    )
