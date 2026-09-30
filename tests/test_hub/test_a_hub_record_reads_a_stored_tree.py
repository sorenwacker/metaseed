"""A hub dataset stored as a tree is read with its entities.

The hub stores every dataset saved in its web interface as a tree; the hub
client read only the flat ``entities`` form. ``metaseed hub list`` reported 0
entities for a dataset holding 16,812 nodes, and a pull brought it down empty.
"""

from __future__ import annotations

from metaseed import MetaseedClient
from metaseed.hub.sync import HubRecord

TREE_ROW = {
    "id": "d1",
    "name": "stored-as-a-tree",
    "profile": "miappe",
    "version": "1.2",
    "data": {
        "profile": "miappe",
        "version": "1.2",
        "tree": [
            {
                "id": "n-inv",
                "entity_type": "Investigation",
                "label": "INV-1",
                "data": {"unique_id": "INV-1", "title": "T"},
                "children": [
                    {
                        "id": "n-stu",
                        "entity_type": "Study",
                        "label": "STU-1",
                        "parent_field": "studies",
                        "data": {
                            "unique_id": "STU-1",
                            "investigation_id": "INV-1",
                            "title": "S",
                        },
                        "children": [],
                    }
                ],
            }
        ],
    },
}


def test_a_tree_row_counts_every_node() -> None:
    assert HubRecord.from_row(TREE_ROW).entity_count == 2


def test_a_tree_row_flattens_into_loadable_entities() -> None:
    record = HubRecord.from_row(TREE_ROW)

    client = MetaseedClient("miappe", "1.2")
    client.load({"entities": record.entities}, on_skip=lambda skip: None)
    roots = client._facade.get_roots()

    assert [r.entity_type for r in roots] == ["Investigation"]
    assert [(c.entity_type, c.parent_field) for c in roots[0].children] == [
        ("Study", "studies")
    ]


def test_a_flat_row_still_reads_as_before() -> None:
    row = {
        **TREE_ROW,
        "data": {"entities": [{"_type": "Investigation", "unique_id": "INV-1"}]},
    }
    assert HubRecord.from_row(row).entities == [
        {"_type": "Investigation", "unique_id": "INV-1"}
    ]
