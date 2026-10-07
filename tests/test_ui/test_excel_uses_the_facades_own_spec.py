"""The workbook is built from the specification the facade holds.

The export and the import each looked the specification up by name in a fresh
``SpecLoader``. A facade built from a supplied specification has no profile
file to find, so the lookup failed: the export fell back to a bare grid with no
heading notes and no dropdowns, and the import raised. Every specification the
hub stores is of that kind. See docs/architecture/excel-round-trip.md.
"""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from metaseed.facade import ProfileFacade
from metaseed.specs.loader import SpecLoader
from metaseed.ui.services.export import build_workbook_from_facade
from metaseed.ui.services.import_excel import workbook_to_payload

UI_SOURCES = Path(__file__).parents[2] / "src" / "metaseed" / "ui"

#: A by-name lookup of a facade's specification with no ``profile_spec`` before it.
BY_NAME_ONLY = re.compile(r"(?<!or )SpecLoader\(\)\.load_profile\(")


def _facade_over_an_unlisted_spec() -> ProfileFacade:
    """MIAPPE 1.1 under a name no installed profile has."""
    listed = SpecLoader().load_profile("1.1", "miappe")
    return ProfileFacade(
        "unlisted", spec=listed.model_copy(update={"name": "unlisted"})
    )


def _notes(workbook: object) -> int:
    return sum(
        1
        for sheet in workbook.worksheets  # type: ignore[attr-defined]
        for cell in sheet[1]
        if cell.comment
    )


def test_an_in_memory_spec_gets_the_notes_a_listed_one_gets() -> None:
    listed = build_workbook_from_facade(ProfileFacade("miappe", "1.1"))
    unlisted = build_workbook_from_facade(_facade_over_an_unlisted_spec())

    assert _notes(unlisted) == _notes(listed)


def test_an_in_memory_spec_gets_its_dropdowns() -> None:
    listed = build_workbook_from_facade(ProfileFacade("miappe", "1.1"))
    unlisted = build_workbook_from_facade(_facade_over_an_unlisted_spec())

    def dropdowns(workbook: object) -> int:
        return sum(
            len(sheet.data_validations.dataValidation)
            for sheet in workbook.worksheets  # type: ignore[attr-defined]
        )

    assert dropdowns(unlisted) == dropdowns(listed)


def test_a_workbook_of_an_in_memory_spec_imports() -> None:
    facade = _facade_over_an_unlisted_spec()
    workbook = build_workbook_from_facade(facade)
    sheet = workbook["Investigation"]
    headings = [cell.value for cell in sheet[1]]
    sheet.cell(row=2, column=headings.index("unique_id") + 1, value="INV-1")
    sheet.cell(row=2, column=headings.index("title") + 1, value="A trial")
    raw = BytesIO()
    workbook.save(raw)

    payload = workbook_to_payload(
        raw.getvalue(), profile=facade.profile, version=facade.version, facade=facade
    )

    assert [entity["unique_id"] for entity in payload["entities"]] == ["INV-1"]


def test_no_ui_module_looks_a_spec_up_by_name_alone() -> None:
    offenders = [
        f"{path.relative_to(UI_SOURCES)}:{number}"
        for path in sorted(UI_SOURCES.rglob("*.py"))
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if BY_NAME_ONLY.search(line)
    ]

    assert offenders == []
