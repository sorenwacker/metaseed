"""A dataset must survive Excel export and import unchanged.

The export is only "an option to be exported" if what comes back is the same
dataset: same entities, same tree, same values -- including the ones Excel
loves to mangle (gene names, leading zeros) and the scalar lists the export
joins into one cell.
"""

from __future__ import annotations

from metaseed import MetaseedClient
from metaseed.ui.datasets import import_payload
from metaseed.ui.services.export import export_to_bytes
from metaseed.ui.services.import_excel import workbook_to_payload
from metaseed.ui.state import AppState


def _exported_state() -> bytes:
    state = AppState(profile="miappe", version="1.1")
    facade = state.get_or_create_facade()
    inv = facade.Investigation.create(
        unique_id="0001", title="SEPT1 trial", skip_validation=True
    )
    inv_node = state.add_node("Investigation", inv)
    study = facade.Study.create(
        unique_id="st-01",
        title="field study",
        investigation_id="0001",
        observation_unit_level_hierarchy=["block", "plot"],
        skip_validation=True,
    )
    state.add_node("Study", study, parent_id=inv_node.id)
    return export_to_bytes(state).getvalue()


def _reimport(raw: bytes) -> list[dict]:
    fresh = AppState(profile="miappe", version="1.1")
    payload = workbook_to_payload(
        raw, profile="miappe", version="1.1", facade=fresh.get_or_create_facade()
    )
    info = import_payload(fresh, payload)
    assert info["entity_count"] == 2, info
    client = MetaseedClient.from_facade(fresh.get_or_create_facade())
    return client.serialize()["entities"]


def test_the_tree_and_the_fragile_values_survive() -> None:
    entities = _reimport(_exported_state())
    by_type = {e["_type"]: e for e in entities}
    assert set(by_type) == {"Investigation", "Study"}
    # The values Excel mangles when cells are not text.
    assert by_type["Investigation"]["unique_id"] == "0001"
    assert by_type["Investigation"]["title"] == "SEPT1 trial"
    # The tree, carried by the _parent column.
    assert by_type["Study"]["_parent_unique_id"] == "0001"


def test_a_scalar_list_splits_back_into_a_list() -> None:
    entities = _reimport(_exported_state())
    study = next(e for e in entities if e["_type"] == "Study")
    assert study["observation_unit_level_hierarchy"] == ["block", "plot"]


def test_a_workbook_from_another_profile_is_refused() -> None:
    import pytest

    raw = _exported_state()
    other = AppState(profile="darwin-core", version="1.0")
    with pytest.raises(ValueError, match="different profile"):
        workbook_to_payload(
            raw,
            profile="darwin-core",
            version="1.0",
            facade=other.get_or_create_facade(),
        )
