"""Interactive facade for creating profile entities.

This module provides a user-friendly API with tab completion and help
for creating MIAPPE, ISA, and other profile entities.

ProfileFacade serves as the single source of truth for:
- Entity schema helpers (EntityHelper instances)
- Entity instance storage (via EntityStore)
- Relationship resolution via reference fields
- Tree/graph generation for visualization

This enables reuse across JupyterLab, CLI, MCP, and UI without
duplicating relationship logic.

Example:
    >>> from metaseed.facade import ProfileFacade
    >>> miappe = ProfileFacade("miappe", "1.1")
    >>> miappe.entities  # List all entities
    >>> miappe.Investigation.help()  # Show help for Investigation
    >>> inv = miappe.Investigation(unique_id="INV-001", title="My Investigation")

Convenience functions:
    >>> from metaseed.facade import miappe, isa, ena
    >>> m = miappe()
    >>> i = isa()
    >>> e = ena()
"""

from metaseed.facade.core import ProfileFacade
from metaseed.facade.helper import EntityHelper, validate_ontology_term
from metaseed.facade.node import IDENTIFIER_FIELDS, EntityNode
from metaseed.facade.profiles import (
    darwin_core,
    dissco,
    ena,
    isa,
    metabolights,
    miappe,
    pride,
)
from metaseed.facade.store import EntityStore

__all__ = [
    "IDENTIFIER_FIELDS",
    "EntityHelper",
    "EntityNode",
    "EntityStore",
    "ProfileFacade",
    "darwin_core",
    "dissco",
    "ena",
    "isa",
    "metabolights",
    "miappe",
    "pride",
    "validate_ontology_term",
]
