"""Metaseed: Schema-driven API for research metadata across scientific standards.

Metadata structure is defined in YAML profiles (MIAPPE, ISA, Darwin Core, DiSSCo,
ENA, JERM, PRIDE, MetaboLights) and used to generate Pydantic models at runtime.

Programmatic API (recommended):
    >>> from metaseed import MetaseedClient
    >>> client = MetaseedClient("miappe", "1.2")
    >>> inv = client.create_entity("Investigation", {
    ...     "unique_id": "INV-001",
    ...     "title": "Drought Study"
    ... })
    >>> result = client.validate()

Interactive facade usage (for Jupyter/notebooks):
    >>> from metaseed import miappe, isa
    >>> m = miappe()
    >>> m.Investigation.help()  # Show field information
    >>> inv = m.Investigation(unique_id="INV-001", title="My Investigation")

Legacy model usage:
    >>> from metaseed import get_model, validate
    >>> Investigation = get_model("Investigation")
    >>> inv = Investigation(unique_id="INV-001", title="Drought Study")
    >>> errors = validate(inv)
"""

# Public API (recommended)
from metaseed.api import (
    Entity,
    EntityNode,
    EntityNotFoundError,
    EntitySchema,
    EntityTypeNotFoundError,
    FieldInfo,
    MetaseedClient,
    MetaseedError,
    ProfileNotFoundError,
    SkippedNode,
    ValidationIssue,
    ValidationResult,
)

# Interactive facade (for notebooks)
from metaseed.facade import (
    ProfileFacade,
    darwin_core,
    dissco,
    ena,
    isa,
    jerm,
    metabolights,
    miappe,
    miappe_htp,
    pride,
)

# Legacy/internal APIs
from metaseed.models import get_model
from metaseed.specs import SpecLoader
from metaseed.storage import JsonStorage, YamlStorage
from metaseed.validators import validate

try:
    from metaseed._version import __version__
except ImportError:
    __version__ = "0.0.0+unknown"


def list_profiles() -> list[str]:
    """List the names of all available profiles.

    Searches both the built-in and user spec directories.

    Returns:
        Profile names, e.g. ``["miappe", "isa", "darwin-core"]``.

    Example:
        >>> import metaseed
        >>> "miappe" in metaseed.list_profiles()
        True
    """
    return SpecLoader().list_profiles()


__all__ = [
    "Entity",
    "EntityNode",
    "EntityNotFoundError",
    "EntitySchema",
    "EntityTypeNotFoundError",
    "FieldInfo",
    "JsonStorage",
    "MetaseedClient",
    "MetaseedError",
    "ProfileFacade",
    "ProfileNotFoundError",
    "SkippedNode",
    "SpecLoader",
    "ValidationIssue",
    "ValidationResult",
    "YamlStorage",
    "darwin_core",
    "dissco",
    "ena",
    "get_model",
    "isa",
    "jerm",
    "list_profiles",
    "metabolights",
    "miappe",
    "miappe_htp",
    "pride",
    "validate",
]
