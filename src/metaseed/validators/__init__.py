"""Validation module for MIAPPE entities.

Provides validation rules and an engine for validating MIAPPE-compliant
metadata beyond basic type checking. The entry-point functions live in
:mod:`metaseed.validators.api`; this package re-exports the public surface.
"""

from metaseed.validators.api import (
    validate,
    validate_entity,
    validate_entity_with_report,
)
from metaseed.validators.base import (
    ValidationCheck,
    ValidationError,
    ValidationRule,
    has_value,
)
from metaseed.validators.dataset import DatasetValidationResult, DatasetValidator
from metaseed.validators.engine import (
    ValidationEngine,
    create_engine_for_entity,
    create_engine_for_extracted_record,
)
from metaseed.validators.rules import (
    DateRangeRule,
    PatternRule,
    RequiredFieldsRule,
    UniqueIdPatternRule,
)

__all__ = [
    "DatasetValidationResult",
    "DatasetValidator",
    "DateRangeRule",
    "PatternRule",
    "RequiredFieldsRule",
    "UniqueIdPatternRule",
    "ValidationCheck",
    "ValidationEngine",
    "ValidationError",
    "ValidationRule",
    "create_engine_for_entity",
    "create_engine_for_extracted_record",
    "has_value",
    "validate",
    "validate_entity",
    "validate_entity_with_report",
]
