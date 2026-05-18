"""Metadata extraction agent.

AI-powered agent that helps users fill in metadata by analyzing source files
and mapping them to a selected metadata profile.
"""

from metaseed.agent.core import (
    ExtractionContext,
    ExtractionResult,
    ValidationError,
    extract_instances,
    parse_file,
)
from metaseed.agent.mapping import (
    ColumnMapping,
    FieldMapping,
    create_mapping,
    mapping_from_dict,
    mapping_to_dict,
    suggest_mapping,
)
from metaseed.agent.questions import Answer, Question, QuestionType

__all__ = [
    "Answer",
    "ColumnMapping",
    "ExtractionContext",
    "ExtractionResult",
    "FieldMapping",
    "Question",
    "QuestionType",
    "ValidationError",
    "create_mapping",
    "extract_instances",
    "mapping_from_dict",
    "mapping_to_dict",
    "parse_file",
    "suggest_mapping",
]
