"""Metaseed: Schema-driven API for MIAPPE-compliant phenotyping metadata.

Example usage:
    >>> from metaseed import get_model, validate
    >>> Investigation = get_model("Investigation")
    >>> inv = Investigation(
    ...     unique_id="INV-001",
    ...     title="Drought Study",
    ...     studies=[Study(unique_id="STU-001", title="Field Trial")],
    ... )
    >>> errors = validate(inv)

Interactive facade usage:
    >>> from metaseed import miappe, isa
    >>> m = miappe()
    >>> m.Investigation.help()  # Show field information
    >>> inv = m.Investigation(unique_id="INV-001", title="My Investigation")
"""

from metaseed.facade import ProfileFacade, isa, miappe
from metaseed.models import get_model
from metaseed.specs import SpecLoader
from metaseed.storage import JsonStorage, YamlStorage
from metaseed.validators import validate

try:
    from metaseed._version import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

__all__ = [
    "JsonStorage",
    "ProfileFacade",
    "SpecLoader",
    "YamlStorage",
    "get_model",
    "isa",
    "miappe",
    "validate",
]
