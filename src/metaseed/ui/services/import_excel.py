"""Excel import: the reverse of the Excel export.

Reads a workbook shaped the way :mod:`metaseed.ui.services.export` writes one —
one sheet per entity type, a header row of field names, every cell text — back
into the dataset payload :func:`metaseed.ui.datasets.import_payload` loads, so
Excel and JSON imports share one loading path.

The tree comes from the **Belongs to** column the export writes, ``Type:
identifier`` (:mod:`metaseed.ui.services.belongs_to`): no profile declares
``parent_ref`` fields, so without that column the linkage would not survive the
round trip. Workbooks exported before 0.67.0 carry ``_parent``, the identifier
alone, which is still read.

Nested list fields (a parent's embedded children) are skipped on import: the
children arrive as rows on their own sheet, and the export flattens the list to
a count that means nothing on the way back.

A workbook written for someone to fill in carries ``<unique_id>``-style prompts
where the values belong. Those are skipped too: storing the prompt would leave a
Study titled ``<title>``, which is worse than one with no title because nothing
downstream can tell it is missing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import TYPE_CHECKING, Any

from openpyxl import load_workbook

from metaseed.specs.loader import SpecLoader
from metaseed.specs.schema import FieldType
from metaseed.ui.services.belongs_to import BELONGS_TO, LEGACY_PARENT, parse
from metaseed.ui.services.export import FORMULA_TRIGGERS

if TYPE_CHECKING:
    from metaseed.facade import ProfileFacade


def _is_placeholder(value: str) -> bool:
    """Whether a cell holds a template's prompt rather than a value.

    The brackets have to wrap the whole cell and nothing else inside may be
    bracketed, so ``<title>`` is a prompt while markup like ``<em>x</em>`` and
    prose like ``a < b`` remain data.

    Args:
        value: The cell's text.

    Returns:
        True if the cell is a prompt and should not be stored.
    """
    text = value.strip()
    return (
        len(text) > 2
        and text.startswith("<")
        and text.endswith(">")
        and "<" not in text[1:-1]
        and ">" not in text[1:-1]
    )


def _unescape_formula(value: str) -> str:
    """Reverse the export's formula neutralisation.

    The export prefixes formula-triggering cells with a quote so Excel shows
    them as text; importing must give back the original value or a round trip
    changes the data.
    """
    if (
        value.startswith("'")
        and len(value) > 1
        and value[1:].startswith(FORMULA_TRIGGERS)
    ):
        return value[1:]
    return value


@dataclass
class _Reading:
    """The rows read so far, and what is wrong with them.

    Every row naming its parent is checked once all sheets are read, so a
    parent may stand on a later sheet than its child.
    """

    facade: Any
    entities: list[dict[str, Any]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    #: (entity type, identifier) of every row read.
    identifiers: set[tuple[str, str]] = field(default_factory=set)
    #: (sheet, row number, cell text, parent type, parent identifier).
    placed: list[tuple[str, int, str, str, str]] = field(default_factory=list)

    def read_sheet(self, entity_type: str, sheet: Any, fields: dict[str, Any]) -> None:
        """Read every row of one entity type's sheet."""
        nested = {n for n, f in fields.items() if f.is_nested()}
        scalar_lists = {
            n for n, f in fields.items() if f.type == FieldType.LIST and n not in nested
        }
        rows = sheet.iter_rows(values_only=True)
        header = next(rows, None)
        if not header:
            return
        columns = [str(c) if c is not None else "" for c in header]
        identifier_field = getattr(
            getattr(self.facade, entity_type, None), "identifier_field", None
        )
        for row_number, row in enumerate(rows, start=2):
            data: dict[str, Any] = {"_type": entity_type}
            for column, cell in zip(columns, row, strict=False):
                if cell is None or cell == "" or not column:
                    continue
                value = _unescape_formula(str(cell))
                if _is_placeholder(value):
                    # An unedited template row leaves `data` at just its
                    # `_type`, which the row-level check below drops.
                    continue
                if column == BELONGS_TO:
                    self._place(data, entity_type, row_number, value)
                elif column == LEGACY_PARENT:
                    data["_parent_unique_id"] = value
                elif column in scalar_lists:
                    data[column] = [v.strip() for v in value.split(",") if v.strip()]
                elif column not in nested:
                    data[column] = value
            if len(data) > 1:  # a row of empties is not an entity
                self.entities.append(data)
                if identifier_field and data.get(identifier_field):
                    self.identifiers.add((entity_type, str(data[identifier_field])))

    def _place(
        self, data: dict[str, Any], entity_type: str, row_number: int, value: str
    ) -> None:
        """Read a **Belongs to** cell into the row's parent reference."""
        try:
            placement = parse(self.facade, entity_type, value)
        except ValueError as exc:
            self.problems.append(f"{entity_type} row {row_number}: {exc}")
            return
        data["_parent_unique_id"] = placement.identifier
        data["_parent_field"] = placement.field
        self.placed.append(
            (
                entity_type,
                row_number,
                value,
                placement.entity_type,
                placement.identifier,
            )
        )

    def entities_or_refusal(self) -> list[dict[str, Any]]:
        """The rows read, or a ``ValueError`` naming every row that cannot be placed.

        Whole or not at all: a partly placed import has to be repaired by
        comparing the dataset with the workbook.
        """
        for entity_type, row_number, value, parent_type, identifier in self.placed:
            if (parent_type, identifier) not in self.identifiers:
                self.problems.append(
                    f"{entity_type} row {row_number}: {BELONGS_TO} '{value}' names no "
                    f"{parent_type} with identifier {identifier} in this workbook"
                )
        if self.problems:
            raise ValueError(
                "Nothing was imported; fix these rows and import again:\n"
                + "\n".join(self.problems)
            )
        return self.entities


def workbook_to_payload(
    raw: bytes, *, profile: str, version: str, facade: ProfileFacade
) -> dict[str, Any]:
    """Parse an exported workbook back into a loadable dataset payload.

    Args:
        raw: The ``.xlsx`` file contents.
        profile: Profile the dataset belongs to (the workbook does not carry it).
        version: Profile version, for the same reason.
        facade: The profile facade, used to know each sheet's entity type and
            which columns are nested lists to skip.

    Returns:
        A payload for :func:`metaseed.ui.datasets.import_payload`.

    Raises:
        ValueError: If the file is not a readable workbook, or no sheet matches
            an entity type of the profile — which means it was exported from a
            different profile, and loading it would silently produce nothing.
    """
    try:
        workbook = load_workbook(BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError(f"Not a readable Excel workbook: {exc}") from exc

    # The spec says which columns are entity lists (skip: children arrive on
    # their own sheets) and which are scalar lists (split what export joined).
    spec = facade.profile_spec or SpecLoader().load_profile(version, profile)

    reading = _Reading(facade)
    # The export's own sheets are not entities; matching by entity name already
    # skips them, and naming the fact keeps it true if that changes.
    for entity_type in facade.entities:
        if entity_type in workbook.sheetnames:
            fields = (
                {f.name: f for f in spec.entities[entity_type].fields}
                if entity_type in spec.entities
                else {}
            )
            reading.read_sheet(entity_type, workbook[entity_type], fields)
    entities = reading.entities_or_refusal()

    if not entities:
        # An empty result is never what an import meant. The usual cause is a
        # workbook exported from a different profile: sheet names largely miss,
        # and any that coincide hold no rows this profile can read.
        raise ValueError(
            f"Nothing in this workbook matches the {profile} profile — was it "
            "exported from a different profile?"
        )

    return {"profile": profile, "version": version, "entities": entities}
