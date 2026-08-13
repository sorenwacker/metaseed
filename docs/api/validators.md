# Validators

The validation system provides cross-field and cross-entity validation beyond what Pydantic handles at the field level.

## Overview

Validation occurs in two layers:

1. **Pydantic validation** - Field-level constraints (type, pattern, min/max) handled by generated models
2. **Rule-based validation** - Cross-field logic, date ranges, conditional requirements

The validators module handles the second layer.

## Quick Start

```python
from metaseed.validators import validate

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

### Factory Function

Create a pre-configured engine for an entity from its profile spec:

```python
from metaseed.validators.engine import create_engine_for_entity

# Engine with all rules defined for the entity in the profile
engine = create_engine_for_entity("Study", version="1.1", profile="miappe")
errors = engine.validate({"unique_id": "STUDY001", "start_date": "2024-03-01"})
```

The engine loads the `validation_rules` declared for the entity in the profile
YAML and applies them alongside any rules you add manually.

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

With a `where` predicate the rule counts only the items the predicate selects,
which is how a constraint about *some* of a collection is written (spec_version
0.7 — see [Rule Predicates](schema-specs.md#rule-predicates)):

```python
from metaseed.specs.predicates import parse_predicate

rule = ListCardinalityRule(
    field="attributes",
    min_items=1,
    max_items=1,
    where=parse_predicate({"field": "is_display_column", "op": "==", "value": True}),
    label_field="name",
)

errors = rule.validate({"attributes": [{"name": "Title", "is_display_column": False}]})
# Error: expected exactly 1 of 1 'attributes' to match is_display_column == true, found 0
```

The message states the bound, the matched count, the population and the
predicate, and names the matched members when there are too many: "expected
exactly 1, got 0" cannot be acted on against 24 children when the reader cannot
see which of them were counted. `label_field` is how a member is named, resolved
by the engine from the item entity's `is_label` / `is_identifier` markers.

A predicate that cannot be applied to an item — an ordering operator over
operands that are not both numbers or both dates — is reported as an error
against the record. It is not counted as "did not match", which would leave the
rule quietly satisfied by a predicate that never worked.

### ConditionalRequirementRule

Requires fields when a predicate holds of the record (spec_version 0.7 `when` /
`require`).

```python
from metaseed.specs.predicates import parse_predicate
from metaseed.validators.rules import ConditionalRequirementRule

rule = ConditionalRequirementRule(
    when=parse_predicate(
        {"field": "data_type", "op": "==", "value": "Controlled Vocabulary"}
    ),
    require=["cv_terms"],
    rule_name="cv_terms_required_for_controlled_vocabulary",
)

errors = rule.validate({"data_type": "Controlled Vocabulary"})
# Error: Field 'cv_terms' is required when data_type == 'Controlled Vocabulary'
```

`ConditionalRule` reads a condition string and asks only whether the fields it
names are *present*. This is the value-dependent form; the two are alternatives,
and a rule setting both `when` and `condition` is rejected at profile load. A
missing field is reported as incompleteness, like any other required field.

## Rules on a single extracted record

`ExtractionContext.validate_instance` validates one row extracted from a source
file. A row is a flat record: its child entities are extracted separately, and
sibling rows are not visible to it. `create_engine_for_extracted_record` builds
an engine from a loaded `ProfileSpec` containing only the rules that such a
record can answer.

```python
from metaseed.validators.engine import create_engine_for_extracted_record
from metaseed.specs.loader import SpecLoader

profile_spec = SpecLoader(profile="miappe").load_profile("1.2", "miappe")
engine = create_engine_for_extracted_record("ObservedVariable", profile_spec)
errors = engine.validate({"unique_id": "OV-1", "trait": "plant height"})
```

Which of the profile's `validation_rules` run:

| Rule type | On a single extracted record | Reason |
|-----------|------------------------------|--------|
| `conditional` | Runs | Reads only the record's own fields. |
| `date_range` | Runs | Reads only the record's own fields. |
| `coordinate_pair` | Runs | Reads only the record's own fields. |
| `pattern` on a `uri` / `ontology_term` field | Runs | Single-value check. A pattern on a `string` field is merged onto the field's constraints at load and is applied by the field-level checks instead. |
| `minimum` / `maximum` / `enum` | Runs as a field constraint | Merged onto the field at load; applied by the field-level checks, not by an engine rule. |
| `cardinality` over a list of scalars | Runs | The list is a value of the record. A missing field counts as zero items, as it does on every other path. |
| `cardinality` over a child collection | Skipped | The children are extracted as their own records, so the parent record never holds them and the rule would report zero items for every row. A `where` does not change this: a predicated rule over children is skipped on this path for the same reason. |
| `conditional` with `when` / `require` | Runs | Reads only the record's own fields. |
| `uniqueness` | Not built by any engine | Needs the sibling records, which no engine sees. Enforced over the whole tree by `DatasetValidator`, including its `where` predicate. |
| `reference` | Not built by any engine | Needs the identifiers held elsewhere in the dataset. Enforced over the whole tree by `DatasetValidator`. |

Rules derived from the entity spec rather than declared in the profile
(`RequiredFieldsRule`, `UniqueIdPatternRule`) are not added either:
`validate_instance` reports missing required fields itself.

`uniqueness` and `reference` remain valid rule types in a profile; they are
simply enforced somewhere other than the engine. `create_engine_for_entity`
does not build them either, so a rule of either type never reaches a
`ValidationEngine`.

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
