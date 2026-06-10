"""Custom types for MIAPPE models.

This module defines custom Pydantic types used in generated models.
"""

import re

# Pattern for ontology terms: prefix:id, prefix_id, or URL
# Prefix can contain letters, digits, and underscores (e.g., CO_321, GO, PATO)
ONTOLOGY_TERM_PATTERN = re.compile(
    r"^([A-Za-z][A-Za-z0-9_]*[:_][A-Za-z0-9_]+|https?://.+)$"
)


def is_valid_ontology_term(value: str) -> bool:
    """Check if a string is a valid ontology term format.

    Args:
        value: The ontology term string.

    Returns:
        True if valid format, False otherwise.
    """
    if not value:
        return False
    return bool(ONTOLOGY_TERM_PATTERN.match(value))


# OntologyTerm is just a string - validation is done separately in UI
# This allows saving drafts with incomplete/invalid ontology terms
OntologyTerm = str
"""Type alias for ontology term references.

Expected formats (validated separately, not on save):
- PREFIX:ID (e.g., GO:0001234)
- PREFIX_ID (e.g., PPEO_0000001)
- URL (e.g., http://purl.org/ppeo/PPEO.owl#investigation)
"""
