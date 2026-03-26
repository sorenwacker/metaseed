"""MIAPPE-API: Schema-driven API for MIAPPE-compliant phenotyping metadata.

Example usage:
    >>> from miappe_api import get_model, validate
    >>> Investigation = get_model("Investigation")
    >>> inv = Investigation(
    ...     unique_id="INV-001",
    ...     title="Drought Study",
    ...     studies=[Study(unique_id="STU-001", title="Field Trial")],
    ... )
    >>> errors = validate(inv)

Interactive facade usage:
    >>> from miappe_api import miappe, isa
    >>> m = miappe()
    >>> m.Investigation.help()  # Show field information
    >>> inv = m.Investigation(unique_id="INV-001", title="My Investigation")
"""

from miappe_api.facade import ProfileFacade, isa, miappe
from miappe_api.models import get_model
from miappe_api.specs import SpecLoader
from miappe_api.storage import JsonStorage, YamlStorage
from miappe_api.validators import validate

__version__ = "0.1.0"

__all__ = [
    "ProfileFacade",
    "get_model",
    "isa",
    "miappe",
    "validate",
    "SpecLoader",
    "JsonStorage",
    "YamlStorage",
]
