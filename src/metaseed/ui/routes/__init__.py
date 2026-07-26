"""Routes package for the UI module.

This package contains route handlers split by domain:
- core: App setup, home, profile selection
- forms: Entity form rendering
- crud: Entity create, update, delete
- table: Table routes for nested entity lists
- nested: Nested entity editing
- import_export: Data import/export
- validation: Form validation
- examples: Example loading
- api: JSON API endpoints
- explore: Profile exploration and comparison
- seek: SEEK provisioning and export
- dcat: DCAT catalog export
- settings: Application settings
"""

from .api import register_api_routes
from .core import get_profile_display_info, register_core_routes
from .crud import (
    register_entity_crud_routes,
    render_entity_form,
)
from .dcat import register_dcat_routes
from .examples import register_example_routes
from .explore import register_explore_routes
from .forms import register_form_routes
from .import_export import register_export_routes, register_import_routes
from .nested import register_nested_routes
from .seek import register_seek_routes
from .settings import register_settings_routes
from .table import register_table_routes
from .validation import register_validation_routes

__all__ = [
    "get_profile_display_info",
    "register_api_routes",
    "register_core_routes",
    "register_dcat_routes",
    "register_entity_crud_routes",
    "register_example_routes",
    "register_explore_routes",
    "register_export_routes",
    "register_form_routes",
    "register_import_routes",
    "register_nested_routes",
    "register_seek_routes",
    "register_settings_routes",
    "register_table_routes",
    "register_validation_routes",
    "render_entity_form",
]
