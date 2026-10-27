"""An Excel import reads each typed field back as the type its spec declares.

The export writes every cell as text. Kept as text on the way back, an integer
field holds a string, which the dataset stores without complaint. A value that
does not convert keeps the text the person wrote, so nothing is discarded.
"""

from __future__ import annotations

import datetime as dt
from io import BytesIO

from openpyxl import Workbook

from metaseed.ui.services.import_excel import workbook_to_payload
from metaseed.ui.state import AppState


def _workbook(sheets: dict[str, list[list[str]]]) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        for row in rows:
            sheet.append(row)
    out = BytesIO()
    workbook.save(out)
    return out.getvalue()


def _rows(raw: bytes) -> dict[str, dict]:
    facade = AppState(profile="ena", version="1.0").get_or_create_facade()
    payload = workbook_to_payload(raw, profile="ena", version="1.0", facade=facade)
    return {e["_type"]: e for e in payload["entities"]}


def test_typed_cells_come_back_as_their_declared_types() -> None:
    rows = _rows(
        _workbook(
            {
                "Sample": [
                    ["alias", "taxon_id", "lat_lon_latitude", "environmental_sample"],
                    ["test-sample", "4577", "52.5", "true"],
                ],
                "Run": [["alias", "run_date"], ["test-run", "2024-05-01"]],
            }
        )
    )
    sample = rows["Sample"]
    assert sample["taxon_id"] == 4577
    assert sample["lat_lon_latitude"] == 52.5
    assert sample["environmental_sample"] is True
    assert rows["Run"]["run_date"] == dt.date(2024, 5, 1)


def test_a_value_that_does_not_convert_keeps_its_text() -> None:
    rows = _rows(_workbook({"Sample": [["alias", "taxon_id"], ["test-sample", "n/a"]]}))
    assert rows["Sample"]["taxon_id"] == "n/a"
