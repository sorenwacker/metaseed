"""Custom types for MIAPPE models.

This module defines custom Pydantic types used in generated models.
"""

import re
from typing import Annotated

from pydantic import AfterValidator

# Pattern for ontology terms: prefix:id, prefix_id, or URL
_ONTOLOGY_TERM_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9]*[:_][A-Za-z0-9_]+|https?://.+)$")


def _validate_ontology_term(value: str) -> str:
    """Validate ontology term format.

    Args:
        value: The ontology term string.

    Returns:
        The validated string.

    Raises:
        ValueError: If the term doesn't match expected patterns.
    """
    if not value:
        raise ValueError("Ontology term cannot be empty")
    if not _ONTOLOGY_TERM_PATTERN.match(value):
        raise ValueError(
            f"Invalid ontology term format: {value}. Expected format: PREFIX:ID, PREFIX_ID, or URL"
        )
    return value


OntologyTerm = Annotated[str, AfterValidator(_validate_ontology_term)]
"""Custom type for ontology term references.

Accepts formats:
- PREFIX:ID (e.g., GO:0001234)
- PREFIX_ID (e.g., PPEO_0000001)
- URL (e.g., http://purl.org/ppeo/PPEO.owl#investigation)
"""
