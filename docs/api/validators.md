# Validators

The validation system provides cross-field and cross-entity validation beyond what Pydantic handles at the field level.

## Overview

Validation occurs in two layers:

1. **Pydantic validation** - Field-level constraints (type, pattern, min/max) handled by generated models
2. **Rule-based validation** - Cross-field logic, date ranges, conditional requirements

The validators module handles the second layer.

## Quick Start

```python
from metaseed.validators.engine import validate, create_engine_for_entity

# Simple validation
errors = validate(
    data={"unique_id": "STUDY001", "start_date": "2024-03-01"},
    entity="Study",
    profile="miappe",
    version="1.1"
)

for error in errors:
    print(f"{error.field}: {error.message}")
```

## Validation Engine

The `ValidationEngine` collects rules and runs them against data.

```python
from metaseed.validators.engine import ValidationEngine
from metaseed.validators.rules import DateRangeRule, RequiredFieldsRule

engine = ValidationEngine()
engine.add_rule(RequiredFieldsRule(fields=["unique_id", "title"]))
engine.add_rule(DateRangeRule(start_field="start_date", end_field="end_date"))

errors = engine.validate({
    "unique_id": "STUDY001",
    "title": "",  # Error: empty required field
    "start_date": "2024-03-15",
    "end_date": "2024-03-01"  # Error: before start
})
```

### Factory Functions

Create pre-configured engines from profile specs:

```python
from metaseed.validators.engine import (
    create_engine_for_entity,
    create_engine_from_profile
)

# Single entity
engine = create_engine_for_entity("Study", version="1.1", profile="miappe")

# All entities in profile
engines = create_engine_from_profile(version="1.1", profile="miappe")
study_engine = engines["Study"]
```

## Validation Rules

### RequiredFieldsRule

Validates that fields are present and non-empty.

```python
from metaseed.validators.rules import RequiredFieldsRule

rule = RequiredFieldsRule(fields=["unique_id", "title", "description"])
errors = rule.validate({"unique_id": "INV001", "title": ""})
# Error: Field 'title' is required
```

### DateRangeRule

Validates that an end date is not before a start date.

```python
from metaseed.validators.rules import DateRangeRule

rule = DateRangeRule(start_field="start_date", end_field="end_date")
errors = rule.validate({
    "start_date": "2024-03-15",
    "end_date": "2024-03-01"
})
# Error: end_date (2024-03-01) must not be before start_date (2024-03-15)
```

Accepts both date strings and `datetime.date` objects.

### UniqueIdPatternRule

Validates that identifiers match expected patterns.

```python
from metaseed.validators.rules import UniqueIdPatternRule

# Default pattern: alphanumeric, underscores, hyphens
rule = UniqueIdPatternRule(field="unique_id")
errors = rule.validate({"unique_id": "STUDY@001"})
# Error: Field 'unique_id' contains invalid characters

# Custom pattern
rule = UniqueIdPatternRule(field="code", pattern=r"^[A-Z]{3}[0-9]{3}$")
errors = rule.validate({"code": "ABC123"})  # Valid
```

### EntityReferenceRule

Validates that references point to existing entities.

```python
from metaseed.validators.rules import EntityReferenceRule

# Available study IDs
available_ids = {"STUDY001", "STUDY002", "STUDY003"}

rule = EntityReferenceRule(
    field="study",
    reference_id_field="study_id",
    available_ids=available_ids
)

errors = rule.validate({"study": {"study_id": "STUDY999"}})
# Error: Reference 'STUDY999' not found in available study_ids
```

For list fields, set `is_list=True`:

```python
rule = EntityReferenceRule(
    field="studies",
    reference_id_field="study_id",
    available_ids=available_ids,
    is_list=True
)
```

### ConditionalRule

Validates conditional field requirements using boolean expressions.

```python
from metaseed.validators.rules import ConditionalRule

# At least one identifier required
rule = ConditionalRule(
    condition="doi OR pubmed_id OR title",
    rule_name="publication_identifier"
)

# Both or neither
rule = ConditionalRule(
    condition="(latitude AND longitude) OR (NOT latitude AND NOT longitude)",
    rule_name="coordinates_complete"
)
```

Supported operators:

| Operator | Description |
|----------|-------------|
| `AND` | Both conditions must be true |
| `OR` | At least one must be true |
| `NOT` | Negates the condition |
| `()` | Groups conditions |

### CoordinatePairRule

Validates that latitude and longitude are provided together.

```python
from metaseed.validators.rules import CoordinatePairRule

rule = CoordinatePairRule(lat_field="latitude", lon_field="longitude")
errors = rule.validate({"latitude": 51.5})
# Error: 'longitude' is required when 'latitude' is provided
```

### ListCardinalityRule

Validates list field item counts.

```python
from metaseed.validators.rules import ListCardinalityRule

rule = ListCardinalityRule(
    field="samples",
    min_items=1,
    max_items=100
)

errors = rule.validate({"samples": []})
# Error: 'samples' must have at least 1 item(s), but has 0
```

## ValidationError

All rules return `ValidationError` objects:

```python
from metaseed.validators.base import ValidationError

error = ValidationError(
    field="end_date",
    message="Must not be before start_date",
    rule="date_range"
)

print(error)  # end_date: Must not be before start_date (rule: date_range)
```

| Attribute | Description |
|-----------|-------------|
| `field` | Name of the field that failed |
| `message` | Human-readable error description |
| `rule` | Name of the rule that generated the error |

## Custom Rules

Create custom rules by subclassing `ValidationRule`:

```python
from metaseed.validators.base import ValidationRule, ValidationError
from typing import Any

class EmailDomainRule(ValidationRule):
    """Validates email domain matches allowed list."""

    def __init__(self, field: str, allowed_domains: list[str]):
        self.field = field
        self.allowed_domains = allowed_domains

    @property
    def name(self) -> str:
        return "email_domain"

    def validate(self, data: dict[str, Any]) -> list[ValidationError]:
        email = data.get(self.field)
        if not email:
            return []

        domain = email.split("@")[-1]
        if domain not in self.allowed_domains:
            return [ValidationError(
                field=self.field,
                message=f"Email domain must be one of: {self.allowed_domains}",
                rule=self.name
            )]
        return []
```

## Integration with Profile Specs

Validation rules defined in profile YAML specs are automatically loaded:

```yaml
# profile.yaml
validation_rules:
  - name: date_range_valid
    applies_to: [Study]
    condition: "end_date >= start_date"

  - name: coordinates_complete
    applies_to: [Location]
    condition: "(latitude AND longitude) OR (NOT latitude AND NOT longitude)"
```

When using `create_engine_for_entity()`, these rules are converted to `ValidationRule` instances and added to the engine.

## See Also

- [Schema Specs](schema-specs.md) - Defining validation rules in YAML
- [Model Factory](../architecture/model-factory.md) - How Pydantic handles field-level validation
