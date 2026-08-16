"""Helper functions for UI routes.

Contains utility functions for form handling, table rendering,
validation formatting, and breadcrumb navigation.

Submodules:
- entity: Entity traversal and collection utilities
- form: Form context, value collection, and field filtering
- navigation: Breadcrumbs, error responses, and reference fields
- table: Inline table building and formatting
- spec_builder: Spec creation/conversion helpers, imported directly by the
  spec builder routes rather than re-exported here
"""

from __future__ import annotations

# Form generation now lives in the framework-agnostic metaseed.forms package
# (importable without the web app); re-exported here for the UI's existing call
# sites and backward compatibility.
from metaseed.forms import (
    FormContext,
    collect_form_values,
    field_errors_from_validation,
    filter_fields,
    format_missing_required,
    format_validation_errors,
    get_field_data,
    is_nested_field,
    missing_required_fields,
)

# Re-export from entity_helpers
from metaseed.ui.helpers.entity_helpers import (
    collect_entities_by_type,
    extract_nested_from_tree,
    extract_nested_items,
    get_nested_items_for_edit,
    to_dict,
    walk_nested_entities,
)

# Re-export from navigation_helpers
from metaseed.ui.helpers.navigation_helpers import (
    build_breadcrumb,
    error_response,
    get_parent_id_fields,
    get_reference_fields,
)

# Re-export from table_helpers
from metaseed.ui.helpers.table_helpers import (
    build_inline_tables,
    format_table_rows,
    get_items_store,
    get_table_column_info,
    get_table_columns,
    infer_entity_type_from_field,
)

# Re-export from validation helpers
from metaseed.ui.helpers.validation import (
    ValidationResult,
    materialize_nested_children,
    rebuild_nested_items_with_failures,
)

__all__ = [
    "FormContext",
    "ValidationResult",
    "build_breadcrumb",
    "build_inline_tables",
    "collect_entities_by_type",
    "collect_form_values",
    "error_response",
    "extract_nested_from_tree",
    "extract_nested_items",
    "field_errors_from_validation",
    "filter_fields",
    "format_missing_required",
    "format_table_rows",
    "format_validation_errors",
    "get_field_data",
    "get_items_store",
    "get_nested_items_for_edit",
    "get_parent_id_fields",
    "get_reference_fields",
    "get_table_column_info",
    "get_table_columns",
    "infer_entity_type_from_field",
    "is_nested_field",
    "materialize_nested_children",
    "missing_required_fields",
    "rebuild_nested_items_with_failures",
    "to_dict",
    "walk_nested_entities",
]
