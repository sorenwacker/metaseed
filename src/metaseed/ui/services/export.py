"""Excel export service.

Builds Excel workbook from AppState entity tree.
"""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from typing import TYPE_CHECKING, Any

from openpyxl import Workbook

from metaseed.ui.helpers import to_dict, walk_nested_entities
from metaseed.ui.services.controlled_terms import (
    apply_reference_validations,
    apply_uniqueness_validations,
    apply_validations,
    flag_invalid_cells,
)
from metaseed.ui.services.sheet_style import style_sheet

if TYPE_CHECKING:
    from metaseed.ui.state import AppState

# Characters that make Excel/LibreOffice interpret a cell as a formula. A string
# value beginning with one of these (e.g. a collaborator-supplied field like
# ``=HYPERLINK(...)``) would otherwise round-trip into a live formula on export.
FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _escape_formula(value: object) -> object:
    """Neutralize a formula-injection payload in a string cell value.

    Prefixes a single quote so the value is stored/opened as literal text, not a
    formula (also stops openpyxl from emitting a leading-``=`` string as a
    formula). Non-strings can't be formulas and are returned unchanged.
    """
    if isinstance(value, str) and value.startswith(FORMULA_TRIGGERS):
        return "'" + value
    return value


def _format_cell_value(value: object, is_nested_field: bool) -> object:
    """Format a value for Excel cell.

    Args:
        value: The value to format.
        is_nested_field: Whether this field contains nested entities.

    Returns:
        Formatted value suitable for Excel.
    """
    if is_nested_field:
        if isinstance(value, list):
            return len(value)
        if value:
            return 1
        return 0
    if isinstance(value, list):
        if value and not isinstance(value[0], dict):
            return ", ".join(str(v) for v in value)
        # An empty scalar list must export as an empty cell: "0" would fail
        # list validation on reimport and silently drop the whole entity.
        return len(value) if value else ""
    if isinstance(value, dict):
        return "[object]"
    if not isinstance(value, str | int | float | bool | type(None)):
        return str(value)
    return value


def build_workbook(state: AppState) -> Workbook:
    """Build Excel workbook from entity tree.

    Args:
        state: The current AppState containing the entity tree.

    Returns:
        Openpyxl Workbook with sheets for each entity type.
    """
    facade = state.get_or_create_facade()

    wb = Workbook()
    wb.remove(wb.active)

    entities_by_type: dict[str, list[dict[str, Any]]] = {}

    # The tree, as business keys: node id -> the parent's identifier. Without
    # this column the export cannot be reimported -- no profile declares
    # parent_ref fields, so the linkage must ride along explicitly.
    from metaseed import MetaseedClient

    parent_by_node = {
        e.get("_node_id"): e.get("_parent_unique_id")
        for e in MetaseedClient.from_facade(facade).serialize().get("entities", [])
    }

    # Collect all entities including nested ones
    for node in state.nodes_by_id.values():
        entity_type = node.entity_type
        if entity_type not in entities_by_type:
            entities_by_type[entity_type] = []

        data = to_dict(node.instance) or {}
        if parent_by_node.get(node.id):
            data["_parent"] = parent_by_node[node.id]
        entities_by_type[entity_type].append(data)

        # Walk nested entities using shared helper
        for nested_type, nested_data in walk_nested_entities(data, entity_type, facade):
            if nested_type not in entities_by_type:
                entities_by_type[nested_type] = []
            entities_by_type[nested_type].append(nested_data)

    # Kept so the controlled columns can be restricted once every sheet exists.
    sheets: dict[str, Any] = {}
    columns_by_entity: dict[str, list[str]] = {}
    fields_by_entity: dict[str, dict[str, Any]] = {}

    # Create sheets for each entity type
    for entity_type in facade.entities:
        helper = getattr(facade, entity_type, None)
        if not helper:
            continue

        ws = wb.create_sheet(entity_type)
        sheets[entity_type] = ws
        nested_fields = set(helper.nested_fields.keys())
        columns = [*helper.all_fields, "_parent"]
        columns_by_entity[entity_type] = columns
        fields_by_entity[entity_type] = _field_specs(facade, entity_type)

        ws.append(columns)

        entities = entities_by_type.get(entity_type, [])
        for row_offset, entity_data in enumerate(entities, start=2):
            for col_offset, col in enumerate(columns, start=1):
                value = entity_data.get(col, "")
                value = _format_cell_value(value, col in nested_fields)
                value = _escape_formula(value)
                cell = ws.cell(
                    row=row_offset,
                    column=col_offset,
                    value=str(value) if value != "" else "",
                )
                # Every data cell is text. Excel otherwise reinterprets what it
                # recognises -- gene names become dates, identifiers lose their
                # leading zeros -- and a metadata value must survive the round
                # trip byte for byte.
                cell.number_format = "@"

        style_sheet(ws, columns, fields_by_entity[entity_type], len(entities))

    # A column the specification controls becomes a dropdown, and the terms are
    # written into a hidden sheet with what they came from. See
    # metaseed.ui.services.controlled_terms.
    term_ranges: dict[tuple[str, str], str] = {}
    apply_validations(wb, sheets, columns_by_entity, fields_by_entity, term_ranges)
    apply_reference_validations(facade, sheets, columns_by_entity)
    apply_uniqueness_validations(facade, sheets, columns_by_entity, fields_by_entity)
    # Validation stops at the keyboard; pasted values need a check that keeps
    # looking.
    flag_invalid_cells(facade, sheets, columns_by_entity, fields_by_entity, term_ranges)

    return wb


def _field_specs(facade: Any, entity_type: str) -> dict[str, Any]:
    """Field name -> its :class:`FieldSpec` for one entity, or empty if unknown.

    The facade is built from a profile but does not expose it uniformly; a
    workbook must still export when the specification cannot be reached, just
    without dropdowns.
    """
    from metaseed.specs.loader import SpecLoader

    try:
        spec = SpecLoader().load_profile(facade.version, facade.profile)
    except Exception:
        return {}
    entity = spec.entities.get(entity_type)
    fields = getattr(entity, "fields", None)
    return {field.name: field for field in fields} if fields else {}


def export_to_bytes(state: AppState) -> BytesIO:
    """Export entity tree to Excel bytes.

    Args:
        state: The current AppState containing the entity tree.

    Returns:
        BytesIO containing the Excel file.
    """
    wb = build_workbook(state)
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def generate_filename(state: AppState) -> str:
    """Generate filename for the export.

    Args:
        state: The current AppState containing the entity tree.

    Returns:
        Filename string for the Excel export.
    """
    facade = state.get_or_create_facade()

    date_str = datetime.now(UTC).strftime("%y%m%d")
    version_str = facade.version.replace(".", "-")

    entity_id = "export"
    root_nodes = [n for n in state.nodes_by_id.values() if n.parent_id is None]
    if root_nodes:
        root_node = root_nodes[0]
        root_data = to_dict(root_node.instance) or {}
        if root_data.get("unique_id"):
            entity_id = (
                str(root_data["unique_id"]).replace("/", "-").replace(":", "-")[:30]
            )

    return f"{date_str}-{state.profile}-{version_str}-{entity_id}.xlsx"
