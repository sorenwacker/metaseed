"""A table under Related Entities shows the stored child records, not an old copy.

A Study carried an embedded copy of its sources next to the stored Source
records. The table read the copy, so a renamed Source kept its old name there,
and a value converted in the record (3702 -> NCBITaxon:3702) showed unconverted.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from metaseed import MetaseedClient
from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


def _dataset_with_a_stale_copy(tmp_path) -> None:
    c = MetaseedClient("isa", "1.0")
    inv = c.create_entity(
        "Investigation", {"identifier": "I-1", "title": "Inv"}, skip_validation=True
    )
    study = c.create_entity(
        "Study",
        {"identifier": "S-1", "investigation_id": "I-1", "title": "Study"},
        parent_id=inv.id,
        skip_validation=True,
    )
    c.create_entity(
        "Source",
        {"study_id": "S-1", "name": "renamed source"},
        parent_id=study.id,
        skip_validation=True,
    )
    payload = json.loads(json.dumps(c.serialize()))
    stored_study = next(e for e in payload["entities"] if e["_type"] == "Study")
    stored_study["sources"] = [{"study_id": "S-1", "name": "old name"}]
    payload["name"] = "test-stale-copy"
    (tmp_path / "test-stale-copy.json").write_text(json.dumps(payload))


def test_the_sources_table_shows_the_stored_source(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("METASEED_DATASETS_DIR", str(tmp_path))
    _dataset_with_a_stale_copy(tmp_path)
    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)
    client.get("/dataset/test-stale-copy/edit")
    study = next(n for n in state.nodes_by_id.values() if n.entity_type == "Study")

    page = client.get(f"/form/Study/{study.id}").text
    table = page[page.index('id="inline-table-body-sources"') :]
    table = table[: table.index("</tbody>")]

    assert "renamed source" in table
    assert "old name" not in table
    assert 'data-testid="inline-open-sources-0"' in table
