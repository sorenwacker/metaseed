"""An exported workbook carries the standard's vocabulary, not just its columns.

The approach is RightField's (Wolstencroft et al., 2011): a column the
specification controls becomes a dropdown, the terms and their identifiers
travel in a hidden sheet, and the scientist filling the sheet in never sees an
ontology. Without this a spreadsheet is free text, and a value that does not
meet the standard is only discovered on import — after two hundred rows.
"""

from __future__ import annotations

from metaseed.specs.schema import Constraints, FieldSpec, FieldType
from metaseed.ui.services.controlled_terms import (
    MAX_EMBEDDED_TERMS,
    TERMS_SHEET,
    allowed_values,
)
from metaseed.ui.services.export import build_workbook
from metaseed.ui.state import AppState


def _validations(ws) -> list:
    return list(ws.data_validations.dataValidation)


class TestWhichFieldsGetADropdown:
    def test_a_declared_value_list_is_embedded(self) -> None:
        field = FieldSpec(
            name="tissue",
            type=FieldType.STRING,
            constraints=Constraints(enum=["leaf", "root", "seed"]),
        )
        terms = allowed_values(field)

        assert terms is not None
        assert terms.embedded
        assert terms.values == ["leaf", "root", "seed"]

    def test_an_ontology_is_documented_not_embedded(self) -> None:
        """NCBI Taxonomy has millions of names. A spreadsheet cannot hold them,
        and a dropdown of thousands is worse than typing."""
        field = FieldSpec(
            name="organism",
            type=FieldType.ONTOLOGY_TERM,
            ontologies=["ncbitaxon"],
        )
        terms = allowed_values(field)

        assert terms is not None
        assert not terms.embedded
        assert "ncbitaxon" in terms.source
        # What the note may not do is promise a check that does not exist: no
        # validator compares a value against an ontology yet (issue #215).
        assert "nothing" in terms.note and "#215" in terms.note

    def test_a_list_past_the_cap_stays_free_text(self) -> None:
        field = FieldSpec(
            name="code",
            type=FieldType.STRING,
            constraints=Constraints(
                enum=[f"T{i}" for i in range(MAX_EMBEDDED_TERMS + 1)]
            ),
        )
        terms = allowed_values(field)

        assert terms is not None
        assert not terms.embedded

    def test_a_plain_field_has_no_terms(self) -> None:
        assert allowed_values(FieldSpec(name="title", type=FieldType.STRING)) is None


class TestTheExportedWorkbook:
    def _workbook(self):
        state = AppState(profile="miappe", version="1.2")
        facade = state.get_or_create_facade()
        investigation = facade.Investigation.create(
            unique_id="INV1",
            title="An investigation",
            description="a valid long description " * 3,
            skip_validation=True,
        )
        state.add_node("Investigation", investigation)
        return build_workbook(state)

    def test_the_terms_sheet_exists_and_is_hidden(self) -> None:
        """Hidden because the person filling in the sheet has no use for it;
        present because the identifiers are what make the values resolvable."""
        wb = self._workbook()

        assert TERMS_SHEET in wb.sheetnames
        assert wb[TERMS_SHEET].sheet_state == "hidden"

    def test_the_terms_sheet_records_where_values_came_from(self) -> None:
        wb = self._workbook()
        header = [cell.value for cell in wb[TERMS_SHEET][1]]

        assert header == ["entity", "field", "value", "identifier", "source", "note"]

    def test_a_reference_column_points_at_the_sheet_it_names(self) -> None:
        """MIAPPE's Study names its Investigation. Typed by hand, a transposed
        character silently orphans the row."""
        wb = self._workbook()
        formulas = [v.formula1 for v in _validations(wb["Study"])]

        assert any("Investigation" in formula for formula in formulas), (
            f"no validation on Study points at Investigation: {formulas}"
        )

    def test_the_parent_column_points_at_the_parent_sheet(self) -> None:
        wb = self._workbook()
        formulas = [v.formula1 for v in _validations(wb["Person"])]

        assert formulas, "the Person sheet has no validations at all"

    def test_data_cells_are_still_text(self) -> None:
        """The dropdowns must not undo what the text format protects: gene names
        becoming dates, identifiers losing leading zeros."""
        wb = self._workbook()
        ws = wb["Investigation"]

        assert ws.cell(row=2, column=1).number_format == "@"


class TestTheSheetIsReadable:
    """A sheet somebody has to fill in by hand: headings that stay on screen,
    say what they mean, and are wide enough to read."""

    def _sheet(self, entity: str = "Study"):
        state = AppState(profile="miappe", version="1.2")
        facade = state.get_or_create_facade()
        study = facade.Study.create(
            unique_id="STU1",
            title="Site A 2026",
            description="Rain-fed plots across two irrigation regimes. " * 3,
            skip_validation=True,
        )
        state.add_node("Study", study)
        return build_workbook(state)[entity]

    def test_the_heading_row_and_first_column_stay_on_screen(self) -> None:
        assert self._sheet().freeze_panes == "B2"

    def test_headings_carry_their_description_from_the_specification(self) -> None:
        """The person filling the sheet has not read the standard."""
        ws = self._sheet()
        headings = {cell.value: cell for cell in ws[1]}
        described = [
            name for name, cell in headings.items() if cell.comment is not None
        ]

        assert described, "no heading explains itself"
        title = headings.get("title")
        assert title is not None and title.comment is not None
        assert "Required" in title.comment.text or "Optional" in title.comment.text

    def test_the_parent_column_explains_what_it_is_for(self) -> None:
        ws = self._sheet()
        parent = next(cell for cell in ws[1] if cell.value == "_parent")

        assert parent.comment is not None
        assert "parent sheet" in parent.comment.text

    def test_columns_are_wide_enough_to_read_the_heading(self) -> None:
        ws = self._sheet()
        for index, cell in enumerate(ws[1], start=1):
            letter = ws.cell(row=1, column=index).column_letter
            width = ws.column_dimensions[letter].width
            assert width >= min(len(str(cell.value)), 12), (
                f"{cell.value} is narrower than its own heading"
            )

    def test_values_wrap_instead_of_running_under_the_next_cell(self) -> None:
        ws = self._sheet()
        assert ws.cell(row=2, column=1).alignment.wrap_text is True

    def test_the_banding_comes_from_the_table_not_painted_cells(self) -> None:
        """Painted banding stops where the data stops; a table keeps banding
        rows as they are added."""
        ws = self._sheet()
        table = next(iter(ws.tables.values()))

        assert table.tableStyleInfo.showRowStripes is True
        assert ws.cell(row=2, column=2).fill.patternType is None


class TestTheStructuralColumn:
    """_parent is not metadata: nobody observed or measured it, and inventing a
    value for it breaks the tree. It stays visible only because a row added in
    Excel has no other way to say where it belongs."""

    def _study_sheet(self):
        state = AppState(profile="miappe", version="1.2")
        facade = state.get_or_create_facade()
        state.add_node(
            "Study",
            facade.Study.create(
                unique_id="STU1", title="A study", skip_validation=True
            ),
        )
        return build_workbook(state)["Study"]

    def test_it_is_set_apart_from_the_metadata_columns(self) -> None:
        ws = self._study_sheet()
        columns = [cell.value for cell in ws[1]]
        parent_index = columns.index("_parent") + 1

        parent_cell = ws.cell(row=2, column=parent_index)
        assert parent_cell.font.italic is True
        assert parent_cell.fill.fgColor.rgb.endswith("ECEFE9")

    def test_it_says_what_to_do_when_adding_a_row(self) -> None:
        ws = self._study_sheet()
        parent = next(cell for cell in ws[1] if cell.value == "_parent")

        assert "Structure, not metadata" in parent.comment.text
        assert "add a row" in parent.comment.text


class TestEachSheetIsATable:
    """A row typed under a table is absorbed into it, inheriting the banding and
    the column's data validation. Painted banding stopped where the data did,
    and a dropdown for an added row had to be guessed at in advance."""

    def _sheet(self, entity: str = "Study"):
        state = AppState(profile="miappe", version="1.2")
        facade = state.get_or_create_facade()
        state.add_node(
            "Study",
            facade.Study.create(unique_id="STU1", title="One", skip_validation=True),
        )
        return build_workbook(state)[entity]

    def test_the_sheet_carries_a_table(self) -> None:
        ws = self._sheet()
        assert ws.tables, "the Study sheet is a plain range, not a table"

    def test_the_table_covers_the_header_and_the_data(self) -> None:
        ws = self._sheet()
        table = next(iter(ws.tables.values()))
        assert table.ref.startswith("A1:")

    def test_the_rows_are_banded_by_the_table(self) -> None:
        ws = self._sheet()
        table = next(iter(ws.tables.values()))
        assert table.tableStyleInfo.showRowStripes is True

    def test_an_entity_with_no_rows_still_has_a_table_to_type_into(self) -> None:
        """A table cannot be a header alone, and an empty sheet is exactly where
        somebody is about to start typing."""
        ws = self._sheet("Person")
        assert ws.tables
        assert ws.max_row >= 2

    def test_table_names_do_not_collide(self) -> None:
        state = AppState(profile="miappe", version="1.2")
        state.get_or_create_facade()
        wb = build_workbook(state)
        names = [name for sheet in wb.worksheets for name in sheet.tables]
        assert len(names) == len(set(names)), f"duplicate table names: {names}"


class TestIdentifiersMustBeUnique:
    """Two rows claiming the same identifier is not a typo the import can
    resolve: every reference to it becomes ambiguous and the second row
    silently replaces the first."""

    def _sheet(self):
        state = AppState(profile="miappe", version="1.2")
        facade = state.get_or_create_facade()
        state.add_node(
            "Investigation",
            facade.Investigation.create(
                unique_id="INV1", title="One", skip_validation=True
            ),
        )
        return build_workbook(state)["Investigation"]

    def test_the_identifier_column_refuses_a_repeat(self) -> None:
        ws = self._sheet()
        customs = [v for v in ws.data_validations.dataValidation if v.type == "custom"]

        assert customs, "nothing stops a duplicate identifier being typed"
        assert any("COUNTIF" in (v.formula1 or "") for v in customs)

    def test_it_says_why_rather_than_just_refusing(self) -> None:
        ws = self._sheet()
        custom = next(
            v for v in ws.data_validations.dataValidation if v.type == "custom"
        )

        assert "already used" in (custom.error or "")

    def test_a_blank_is_still_allowed(self) -> None:
        """Refusing blanks would stop someone filling a sheet top to bottom."""
        ws = self._sheet()
        custom = next(
            v for v in ws.data_validations.dataValidation if v.type == "custom"
        )

        assert custom.allow_blank is True


class TestPastedValuesAreStillCaught:
    """Data validation only fires while somebody types. Paste a column from
    another workbook — how bulk metadata actually arrives — and Excel accepts
    every value. Conditional formatting keeps looking."""

    def _sheet(self, entity: str = "Investigation"):
        state = AppState(profile="miappe", version="1.2")
        facade = state.get_or_create_facade()
        state.add_node(
            "Investigation",
            facade.Investigation.create(
                unique_id="INV1", title="One", skip_validation=True
            ),
        )
        state.add_node(
            "Study",
            facade.Study.create(
                unique_id="STU1",
                title="A",
                growth_facility_type="field",
                skip_validation=True,
            ),
        )
        return build_workbook(state)[entity]

    def _formulas(self, ws) -> list[str]:
        out: list[str] = []
        for rules in ws.conditional_formatting:
            for rule in rules.rules:
                out.extend(rule.formula or [])
        return out

    def test_a_repeated_identifier_is_coloured(self) -> None:
        formulas = self._formulas(self._sheet())
        assert any("COUNTIF" in f and ">1" in f for f in formulas), formulas

    def test_a_term_outside_the_vocabulary_is_coloured(self) -> None:
        formulas = self._formulas(self._sheet("Study"))
        assert any("=0" in f and "metaseed terms" in f for f in formulas), formulas

    def test_a_required_value_left_empty_is_marked(self) -> None:
        formulas = self._formulas(self._sheet())
        assert any('=""' in f for f in formulas), formulas


class TestExcelActuallyEnforcesTheRules:
    """openpyxl writes showErrorMessage="0" unless told otherwise, and Excel
    then treats every rule as advice it never gives: the dropdown appears, the
    refusal never does. The rules were all present and all inert."""

    def _validations(self):
        state = AppState(profile="miappe", version="1.2")
        facade = state.get_or_create_facade()
        state.add_node(
            "Study",
            facade.Study.create(
                unique_id="STU1",
                title="A",
                growth_facility_type="field",
                skip_validation=True,
            ),
        )
        wb = build_workbook(state)
        return [
            v for sheet in wb.worksheets for v in sheet.data_validations.dataValidation
        ]

    def test_every_rule_actually_speaks_up(self) -> None:
        validations = self._validations()

        assert validations, "no validations at all"
        inert = [v for v in validations if not v.showErrorMessage]
        assert not inert, (
            f"{len(inert)} validations would be ignored by Excel: "
            f"{[v.errorTitle for v in inert]}"
        )

    def test_the_rules_warn_rather_than_block(self) -> None:
        """A vocabulary is rarely complete, and someone who knows their value is
        right should not be locked out of their own spreadsheet."""
        blocking = [v for v in self._validations() if v.errorStyle != "warning"]

        assert not blocking, (
            f"{len(blocking)} rules would refuse outright: "
            f"{[v.errorTitle for v in blocking]}"
        )


class TestAnEntityAppearsOnce:
    """A child can be present twice: as a stored node, and as the dict still
    embedded in its parent's data. Exporting both put every child in the sheet
    twice — the copy carrying no parent, since only a node knows what it hangs
    from — which showed up as a column of duplicate identifiers and a row that
    belonged to nothing."""

    def _collected(self):
        from metaseed import MetaseedClient
        from metaseed.ui.services.export import collect_rows_by_type

        client = MetaseedClient("ena", "1.0")
        study = client.create_entity(
            "Study",
            {
                "alias": "STUDY1",
                "title": "T",
                "study_type": "Other",
                "samples": [{"alias": "SAMP1", "title": "S"}],
            },
            skip_validation=True,
        )
        client.create_entity(
            "Sample",
            {"alias": "SAMP1", "title": "S"},
            parent_id=study.id,
            skip_validation=True,
        )
        return collect_rows_by_type(client.facade)

    def test_the_embedded_copy_is_not_a_second_row(self) -> None:
        samples = self._collected()["Sample"]
        assert [s["alias"] for s in samples] == ["SAMP1"]

    def test_the_row_that_survives_is_the_one_that_knows_its_parent(self) -> None:
        samples = self._collected()["Sample"]
        assert samples[0].get("_parent") == "STUDY1"


class TestOnlyRealKeysMustBeUnique:
    """The facade's identifier_field falls back to an entity's first field when
    the profile declares nothing. Treating that as a key flagged every row of
    ENA's File.filename and of attribute-style tag columns, which repeat by
    design."""

    def _keys(self, entity: str) -> set[str]:
        from metaseed.facade import ProfileFacade
        from metaseed.specs.loader import SpecLoader
        from metaseed.ui.services.controlled_terms import key_columns

        facade = ProfileFacade("ena", "1.0")
        spec = SpecLoader().load_profile("1.0", "ena")
        fields = {f.name: f for f in spec.entities[entity].fields}
        return key_columns(facade, entity, fields)

    def test_a_column_other_rows_point_at_is_a_key(self) -> None:
        assert "alias" in self._keys("Study")

    def test_a_first_field_nobody_references_is_not(self) -> None:
        assert self._keys("File") == set(), (
            "File.filename is the first field, not a key: files repeat names"
        )


class TestBothUniquenessMechanismsAgree:
    """The typing-time warning and the conditional formatting use ONE key rule.

    key_columns deliberately excludes the bare identifier_field fallback
    (File.filename flagged on every legitimately repeated row) and adds
    referenced target fields. apply_uniqueness_validations still used the
    fallback and skipped referenced targets, so typing a repeated filename
    raised the duplicate dialog the formatting correctly did not.
    """

    def test_the_validation_columns_are_the_key_columns(self):
        import inspect

        from metaseed.ui.services import controlled_terms

        source = inspect.getsource(controlled_terms.apply_uniqueness_validations)
        assert "key_columns(" in source, (
            "apply_uniqueness_validations must derive its columns from "
            "key_columns, the single statement of what is a key"
        )
        assert "identifier_field" not in source
