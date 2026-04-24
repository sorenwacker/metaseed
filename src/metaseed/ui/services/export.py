"""Excel export service.

Builds Excel workbook from AppState entity tree.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import TYPE_CHECKING

from openpyxl import Workbook

from metaseed.ui.helpers import to_dict, walk_nested_entities

if TYPE_CHECKING:
    from metaseed.ui.state import AppState


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
        return len(value)
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

    entities_by_type: dict[str, list[dict]] = {}

    # Collect all entities including nested ones
    for node in state.nodes_by_id.values():
        entity_type = node.entity_type
        if entity_type not in entities_by_type:
            entities_by_type[entity_type] = []

        data = to_dict(node.instance) or {}
        entities_by_type[entity_type].append(data)

        # Walk nested entities using shared helper
        for nested_type, nested_data in walk_nested_entities(data, entity_type, facade):
            if nested_type not in entities_by_type:
                entities_by_type[nested_type] = []
            entities_by_type[nested_type].append(nested_data)

    # Create sheets for each entity type
    for entity_type in facade.entities:
        helper = getattr(facade, entity_type, None)
        if not helper:
            continue

        ws = wb.create_sheet(entity_type)
        nested_fields = set(helper.nested_fields.keys())
        columns = helper.all_fields

        ws.append(columns)

        entities = entities_by_type.get(entity_type, [])
        for entity_data in entities:
            row = []
            for col in columns:
                value = entity_data.get(col, "")
                value = _format_cell_value(value, col in nested_fields)
                row.append(value)
            ws.append(row)

    return wb


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

    date_str = datetime.now().strftime("%y%m%d")
    version_str = facade.version.replace(".", "-")

    entity_id = "export"
    root_nodes = [n for n in state.nodes_by_id.values() if n.parent_id is None]
    if root_nodes:
        root_node = root_nodes[0]
        root_data = to_dict(root_node.instance) or {}
        if root_data.get("unique_id"):
            entity_id = str(root_data["unique_id"]).replace("/", "-").replace(":", "-")[:30]

    return f"{date_str}-{state.profile}-{version_str}-{entity_id}.xlsx"
