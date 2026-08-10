"""Tests for the Excel export service, incl. formula-injection neutralization.

A collaborator-supplied field value like ``=HYPERLINK("http://evil","x")`` would,
without escaping, round-trip into a live Excel formula on export. The export now
prefixes formula-triggering string cells with a single quote.
"""

from __future__ import annotations

import pytest

from metaseed.ui.services.export import _escape_formula, build_workbook
from metaseed.ui.state import AppState


class TestEscapeFormula:
    @pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
    def test_formula_triggers_are_quoted(self, prefix):
        assert _escape_formula(f"{prefix}cmd") == f"'{prefix}cmd"

    def test_benign_string_unchanged(self):
        assert _escape_formula("Hello world") == "Hello world"
        assert _escape_formula("PXD000001") == "PXD000001"

    def test_non_strings_unchanged(self):
        for value in (123, 1.5, True, None):
            assert _escape_formula(value) is value


class TestBuildWorkbookInjection:
    def _cell_matching(self, ws, needle: str):
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and needle in cell.value:
                    return cell
        return None

    def test_formula_value_is_neutralized_not_emitted_as_formula(self):
        payload = '=HYPERLINK("http://evil","x")'
        state = AppState(profile="miappe", version="1.2")
        facade = state.get_or_create_facade()
        inv = facade.Investigation.create(
            unique_id="INV1",
            title=payload,
            description="a valid long description " * 3,
            skip_validation=True,
        )
        state.add_node("Investigation", inv)

        wb = build_workbook(state)
        cell = self._cell_matching(wb["Investigation"], "HYPERLINK")
        assert cell is not None, "the payload cell was not found in the export"
        # Neutralized to literal text, and NOT stored as a formula.
        assert cell.value == "'" + payload
        assert cell.data_type == "s"
        assert cell.data_type != "f"

    def test_benign_value_unchanged_in_export(self):
        state = AppState(profile="miappe", version="1.2")
        facade = state.get_or_create_facade()
        inv = facade.Investigation.create(
            unique_id="INV2",
            title="Drought tolerance study",
            description="a valid long description " * 3,
            skip_validation=True,
        )
        state.add_node("Investigation", inv)

        wb = build_workbook(state)
        cell = self._cell_matching(wb["Investigation"], "Drought")
        assert cell is not None
        assert cell.value == "Drought tolerance study"  # untouched


class TestEveryCellIsText:
    """Excel reinterprets what it recognises: gene names become dates,
    identifiers lose leading zeros, "1e3" becomes a thousand. A metadata value
    must survive the round trip byte for byte, so every data cell is text."""

    def test_data_cells_carry_the_text_number_format(self):
        state = AppState(profile="miappe", version="1.2")
        facade = state.get_or_create_facade()
        inv = facade.Investigation.create(
            unique_id="0001",  # the classic leading-zero casualty
            title="SEPT1",  # the classic gene-name-becomes-a-date casualty
            description="a valid long description " * 3,
            skip_validation=True,
        )
        state.add_node("Investigation", inv)

        wb = build_workbook(state)
        ws = wb["Investigation"]
        data_cells = [c for row in ws.iter_rows(min_row=2) for c in row]
        assert data_cells, "no data rows were written"
        assert all(c.number_format == "@" for c in data_cells)

    def test_values_are_written_as_strings_not_numbers(self):
        state = AppState(profile="miappe", version="1.2")
        facade = state.get_or_create_facade()
        inv = facade.Investigation.create(
            unique_id="0042",
            title="numbers survive",
            description="a valid long description " * 3,
            skip_validation=True,
        )
        state.add_node("Investigation", inv)

        wb = build_workbook(state)
        ws = wb["Investigation"]
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                if cell.value not in (None, ""):
                    assert isinstance(cell.value, str), (cell.coordinate, cell.value)
