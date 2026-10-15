"""A batch element that is not an object is reported in its own row.

`batch_create` and `bulk_update_entities` read each element with `.get`, outside
the per-item error handling. A string or number in the array raised there, the
whole call returned one generic error, and the items before it stayed changed
without the auto-save running or their results being reported.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from metaseed.agent.mcp.server import create_server, set_mcp_state
from metaseed.ui.state import AppState


def _tools():
    set_mcp_state(AppState(profile="miappe"))
    return create_server()._tool_manager._tools


def test_batch_create_reports_a_non_object_element_and_keeps_the_rest() -> None:
    tools = _tools()
    with patch("metaseed.ui.datasets.auto_save") as save:
        result = json.loads(
            tools["batch_create"].fn(
                entities=json.dumps(
                    [
                        {
                            "entity_type": "Investigation",
                            "data": {"unique_id": "inv-1", "title": "First"},
                        },
                        "not an object",
                    ]
                )
            )
        )
    assert "error" not in result
    rows = result["results"]
    assert rows[0]["status"] == "created"
    assert rows[1] == {"index": 1, "status": "error", "message": rows[1]["message"]}
    assert "object" in rows[1]["message"]
    save.assert_called()


def test_bulk_update_reports_a_non_object_element_and_keeps_the_rest() -> None:
    tools = _tools()
    with patch("metaseed.ui.datasets.auto_save") as save:
        created = json.loads(
            tools["create_entity"].fn(
                entity_type="Investigation",
                data='{"unique_id": "inv-1", "title": "First"}',
            )
        )
        result = json.loads(
            tools["bulk_update_entities"].fn(
                updates=json.dumps(
                    [{"id": created["id"], "data": {"title": "Changed"}}, 7]
                )
            )
        )
    assert "error" not in result
    rows = result["results"]
    assert rows[0]["status"] == "updated"
    assert rows[1]["status"] == "error"
    assert "object" in rows[1]["message"]
    save.assert_called()
