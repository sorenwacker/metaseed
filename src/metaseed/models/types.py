"""Custom types for MIAPPE models.

This module defines custom Pydantic types used in generated models.
"""

# OntologyTerm is just a string - validation is done separately in UI
# This allows saving drafts with incomplete/invalid ontology terms
OntologyTerm = str
"""Type alias for ontology term references.

Expected formats (validated separately, not on save):
- PREFIX:ID (e.g., GO:0001234)
- PREFIX_ID (e.g., PPEO_0000001)
- URL (e.g., http://purl.org/ppeo/PPEO.owl#investigation)
"""
