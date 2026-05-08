"""Helper functions for UI routes.

Contains utility functions for form handling, table rendering,
validation formatting, and breadcrumb navigation.

This module re-exports all helper functions from the focused modules
for backwards compatibility. New code should import directly from:
- form_helpers: FormContext, collect_form_values, filter_fields, etc.
- table_helpers: build_inline_tables, format_table_rows, etc.
- entity_helpers: walk_nested_entities, extract_nested_items, etc.
- navigation_helpers: build_breadcrumb, error_response, etc.
"""

from __future__ import annotations

# Re-export from entity_helpers
from metaseed.ui.entity_helpers import (
    collect_entities_by_type,
    extract_nested_items,
    to_dict,
    walk_nested_entities,
)

# Re-export from form_helpers
from metaseed.ui.form_helpers import (
    FormContext,
    collect_form_values,
    filter_fields,
    format_validation_errors,
    get_field_data,
    is_nested_field,
)

# Re-export from navigation_helpers
from metaseed.ui.navigation_helpers import (
    build_breadcrumb,
    error_response,
    get_parent_id_fields,
    get_parent_identifier,
    get_reference_fields,
)

# Re-export from table_helpers
from metaseed.ui.table_helpers import (
    build_inline_tables,
    format_table_rows,
    get_items_store,
    get_table_column_info,
    get_table_columns,
)

__all__ = [
    "FormContext",
    "build_breadcrumb",
    "build_inline_tables",
    "collect_entities_by_type",
    "collect_form_values",
    "error_response",
    "extract_nested_items",
    "filter_fields",
    "format_table_rows",
    "format_validation_errors",
    "get_field_data",
    "get_items_store",
    "get_parent_id_fields",
    "get_parent_identifier",
    "get_reference_fields",
    "get_table_column_info",
    "get_table_columns",
    "is_nested_field",
    "to_dict",
    "walk_nested_entities",
]
