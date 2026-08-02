"""Comprehensive tests for the specification language.

This module tests all features documented in docs/api/schema-specs.md:
- Field types (string, integer, float, boolean, date, datetime, uri, ontology_term, list, entity)
- Field constraints (pattern, min_length, max_length, minimum, maximum, min_items, max_items, enum)
- Validation rules (conditional, date_range, coordinate_pair, cardinality, uniqueness, reference)
- Combined constraints and edge cases
"""

import datetime

import pytest
from pydantic import ValidationError

from metaseed.models.factory import create_model_from_spec
from metaseed.specs.schema import Constraints, EntitySpec, FieldSpec, FieldType

# =============================================================================
# Field Types
# =============================================================================


class TestFieldTypeString:
    """Tests for string field type."""

    def test_string_basic(self) -> None:
        """Basic string field works."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="value", type=FieldType.STRING, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(value="hello")
        assert instance.value == "hello"

    def test_string_empty_allowed(self) -> None:
        """Empty string is allowed by default."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="value", type=FieldType.STRING, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(value="")
        assert instance.value == ""

    def test_string_unicode(self) -> None:
        """Unicode strings are supported."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="value", type=FieldType.STRING, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(value="Arabidopsis thaliana - 拟南芥")
        assert instance.value == "Arabidopsis thaliana - 拟南芥"


class TestFieldTypeInteger:
    """Tests for integer field type."""

    def test_integer_basic(self) -> None:
        """Basic integer field works."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="count", type=FieldType.INTEGER, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(count=42)
        assert instance.count == 42

    def test_integer_zero(self) -> None:
        """Zero is a valid integer."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="count", type=FieldType.INTEGER, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(count=0)
        assert instance.count == 0

    def test_integer_negative(self) -> None:
        """Negative integers work."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="count", type=FieldType.INTEGER, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(count=-100)
        assert instance.count == -100

    def test_integer_rejects_float(self) -> None:
        """Float values are rejected for integer fields."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="count", type=FieldType.INTEGER, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        with pytest.raises(ValidationError):
            Model(count=3.14)


class TestFieldTypeFloat:
    """Tests for float field type."""

    def test_float_basic(self) -> None:
        """Basic float field works."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="value", type=FieldType.FLOAT, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(value=3.14159)
        assert instance.value == 3.14159

    def test_float_accepts_integer(self) -> None:
        """Integer values are coerced to float."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="value", type=FieldType.FLOAT, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(value=42)
        assert instance.value == 42.0

    def test_float_negative(self) -> None:
        """Negative floats work."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="value", type=FieldType.FLOAT, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(value=-273.15)
        assert instance.value == -273.15

    def test_float_scientific_notation(self) -> None:
        """Scientific notation works."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="value", type=FieldType.FLOAT, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(value=1.23e-10)
        assert instance.value == 1.23e-10


class TestFieldTypeBoolean:
    """Tests for boolean field type."""

    def test_boolean_true(self) -> None:
        """True value works."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="enabled",
                    type=FieldType.BOOLEAN,
                    required=True,
                    description="",
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(enabled=True)
        assert instance.enabled is True

    def test_boolean_false(self) -> None:
        """False value works."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="enabled",
                    type=FieldType.BOOLEAN,
                    required=True,
                    description="",
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(enabled=False)
        assert instance.enabled is False


class TestFieldTypeDate:
    """Tests for date field type."""

    def test_date_from_string(self) -> None:
        """ISO date string is parsed."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="date", type=FieldType.DATE, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(date="2024-03-15")
        assert instance.date == datetime.date(2024, 3, 15)

    def test_date_from_object(self) -> None:
        """Date object is accepted."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="date", type=FieldType.DATE, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(date=datetime.date(2024, 3, 15))
        assert instance.date == datetime.date(2024, 3, 15)

    def test_date_invalid_format(self) -> None:
        """Invalid date format raises error."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="date", type=FieldType.DATE, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        with pytest.raises(ValidationError):
            Model(date="15-03-2024")  # Wrong format

    def test_date_invalid_value(self) -> None:
        """Invalid date value raises error."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="date", type=FieldType.DATE, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        with pytest.raises(ValidationError):
            Model(date="2024-02-30")  # Feb 30 doesn't exist


class TestFieldTypeDatetime:
    """Tests for datetime field type."""

    def test_datetime_from_string(self) -> None:
        """ISO datetime string is parsed."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="timestamp",
                    type=FieldType.DATETIME,
                    required=True,
                    description="",
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(timestamp="2024-03-15T14:30:00")
        assert instance.timestamp == datetime.datetime(2024, 3, 15, 14, 30, 0)

    def test_datetime_with_timezone(self) -> None:
        """Datetime with timezone is parsed."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="timestamp",
                    type=FieldType.DATETIME,
                    required=True,
                    description="",
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(timestamp="2024-03-15T14:30:00Z")
        assert instance.timestamp.year == 2024
        assert instance.timestamp.hour == 14


class TestFieldTypeUri:
    """Tests for URI field type."""

    def test_uri_https(self) -> None:
        """HTTPS URL works."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="url", type=FieldType.URI, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(url="https://example.com/path")
        assert "example.com" in str(instance.url)

    def test_uri_http(self) -> None:
        """HTTP URL works."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="url", type=FieldType.URI, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(url="http://example.com")
        assert "example.com" in str(instance.url)

    def test_uri_invalid(self) -> None:
        """Invalid URL raises error."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="url", type=FieldType.URI, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        with pytest.raises(ValidationError):
            Model(url="not-a-url")


class TestFieldTypeOntologyTerm:
    """Tests for ontology_term field type."""

    def test_ontology_term_curie_format(self) -> None:
        """CURIE format (PREFIX:ID) works."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="term",
                    type=FieldType.ONTOLOGY_TERM,
                    required=True,
                    description="",
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(term="GO:0008150")
        assert instance.term == "GO:0008150"

    def test_ontology_term_underscore_format(self) -> None:
        """Underscore format (PREFIX_ID) works."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="term",
                    type=FieldType.ONTOLOGY_TERM,
                    required=True,
                    description="",
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(term="PPEO_0000001")
        assert instance.term == "PPEO_0000001"

    def test_ontology_term_url_format(self) -> None:
        """URL format ontology term works."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="term",
                    type=FieldType.ONTOLOGY_TERM,
                    required=True,
                    description="",
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(term="http://purl.obolibrary.org/obo/GO_0008150")
        assert "GO_0008150" in instance.term


class TestFieldTypeList:
    """Tests for list field type."""

    def test_list_of_strings(self) -> None:
        """List of strings works."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="tags", type=FieldType.LIST, items="string", description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(tags=["a", "b", "c"])
        assert instance.tags == ["a", "b", "c"]

    def test_list_of_integers(self) -> None:
        """List of integers works.

        Note: PRIMITIVE_TYPES uses "int" not "integer".
        """
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="numbers", type=FieldType.LIST, items="int", description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(numbers=[1, 2, 3])
        assert instance.numbers == [1, 2, 3]

    def test_list_empty(self) -> None:
        """Empty list is valid."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="tags", type=FieldType.LIST, items="string", description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(tags=[])
        assert instance.tags == []

    def test_list_defaults_to_empty(self) -> None:
        """List field defaults to empty list, not None."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="tags",
                    type=FieldType.LIST,
                    items="string",
                    required=False,
                    description="",
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model()
        assert instance.tags == []


# =============================================================================
# Field Constraints
# =============================================================================


class TestConstraintPattern:
    """Tests for pattern constraint."""

    def test_pattern_matches(self) -> None:
        """Value matching pattern passes."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType.STRING,
                    required=True,
                    description="",
                    constraints=Constraints(pattern=r"^[A-Z]{3}-\d{3}$"),
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(id="ABC-123")
        assert instance.id == "ABC-123"

    def test_pattern_not_matches(self) -> None:
        """Value not matching pattern fails."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType.STRING,
                    required=True,
                    description="",
                    constraints=Constraints(pattern=r"^[A-Z]{3}-\d{3}$"),
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        with pytest.raises(ValidationError):
            Model(id="abc-123")

    def test_pattern_email(self) -> None:
        """Email pattern validation."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="email",
                    type=FieldType.STRING,
                    required=True,
                    description="",
                    constraints=Constraints(
                        pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
                    ),
                ),
            ],
        )
        Model = create_model_from_spec(spec)

        # Valid email
        instance = Model(email="test@example.com")
        assert instance.email == "test@example.com"

        # Invalid email
        with pytest.raises(ValidationError):
            Model(email="not-an-email")

    def test_pattern_orcid(self) -> None:
        """ORCID pattern validation."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="orcid",
                    type=FieldType.STRING,
                    required=True,
                    description="",
                    constraints=Constraints(
                        pattern=r"^[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]$"
                    ),
                ),
            ],
        )
        Model = create_model_from_spec(spec)

        # Valid ORCID
        instance = Model(orcid="0000-0002-1825-0097")
        assert instance.orcid == "0000-0002-1825-0097"

        # ORCID with X checksum
        instance = Model(orcid="0000-0002-1694-233X")
        assert instance.orcid == "0000-0002-1694-233X"

        # Invalid ORCID
        with pytest.raises(ValidationError):
            Model(orcid="1234-5678")

    def test_pattern_doi(self) -> None:
        """DOI pattern validation."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="doi",
                    type=FieldType.STRING,
                    required=True,
                    description="",
                    constraints=Constraints(pattern=r"^10\.[0-9]{4,}/.*$"),
                ),
            ],
        )
        Model = create_model_from_spec(spec)

        # Valid DOI
        instance = Model(doi="10.1234/example.2024")
        assert instance.doi == "10.1234/example.2024"

        # Invalid DOI
        with pytest.raises(ValidationError):
            Model(doi="doi:10.1234/example")


class TestConstraintLength:
    """Tests for min_length and max_length constraints."""

    def test_min_length_satisfied(self) -> None:
        """Value meeting min_length passes."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="name",
                    type=FieldType.STRING,
                    required=True,
                    description="",
                    constraints=Constraints(min_length=3),
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(name="abc")
        assert instance.name == "abc"

    def test_min_length_violated(self) -> None:
        """Value below min_length fails."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="name",
                    type=FieldType.STRING,
                    required=True,
                    description="",
                    constraints=Constraints(min_length=3),
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        with pytest.raises(ValidationError):
            Model(name="ab")

    def test_max_length_satisfied(self) -> None:
        """Value within max_length passes."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="code",
                    type=FieldType.STRING,
                    required=True,
                    description="",
                    constraints=Constraints(max_length=5),
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(code="ABCDE")
        assert instance.code == "ABCDE"

    def test_max_length_violated(self) -> None:
        """Value exceeding max_length fails."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="code",
                    type=FieldType.STRING,
                    required=True,
                    description="",
                    constraints=Constraints(max_length=5),
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        with pytest.raises(ValidationError):
            Model(code="ABCDEF")

    def test_length_range(self) -> None:
        """Combined min_length and max_length."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="code",
                    type=FieldType.STRING,
                    required=True,
                    description="",
                    constraints=Constraints(min_length=2, max_length=5),
                ),
            ],
        )
        Model = create_model_from_spec(spec)

        # Valid
        instance = Model(code="ABC")
        assert instance.code == "ABC"

        # Too short
        with pytest.raises(ValidationError):
            Model(code="A")

        # Too long
        with pytest.raises(ValidationError):
            Model(code="ABCDEF")


class TestConstraintNumeric:
    """Tests for minimum and maximum constraints."""

    def test_minimum_integer(self) -> None:
        """Integer minimum constraint."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="count",
                    type=FieldType.INTEGER,
                    required=True,
                    description="",
                    constraints=Constraints(minimum=0),
                ),
            ],
        )
        Model = create_model_from_spec(spec)

        # At minimum
        instance = Model(count=0)
        assert instance.count == 0

        # Above minimum
        instance = Model(count=100)
        assert instance.count == 100

        # Below minimum
        with pytest.raises(ValidationError):
            Model(count=-1)

    def test_maximum_integer(self) -> None:
        """Integer maximum constraint."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="count",
                    type=FieldType.INTEGER,
                    required=True,
                    description="",
                    constraints=Constraints(maximum=100),
                ),
            ],
        )
        Model = create_model_from_spec(spec)

        # At maximum
        instance = Model(count=100)
        assert instance.count == 100

        # Above maximum
        with pytest.raises(ValidationError):
            Model(count=101)

    def test_minimum_float(self) -> None:
        """Float minimum constraint."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="latitude",
                    type=FieldType.FLOAT,
                    required=True,
                    description="",
                    constraints=Constraints(minimum=-90.0),
                ),
            ],
        )
        Model = create_model_from_spec(spec)

        # Valid
        instance = Model(latitude=45.5)
        assert instance.latitude == 45.5

        # At boundary
        instance = Model(latitude=-90.0)
        assert instance.latitude == -90.0

        # Below minimum
        with pytest.raises(ValidationError):
            Model(latitude=-90.1)

    def test_maximum_float(self) -> None:
        """Float maximum constraint."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="latitude",
                    type=FieldType.FLOAT,
                    required=True,
                    description="",
                    constraints=Constraints(maximum=90.0),
                ),
            ],
        )
        Model = create_model_from_spec(spec)

        # At boundary
        instance = Model(latitude=90.0)
        assert instance.latitude == 90.0

        # Above maximum
        with pytest.raises(ValidationError):
            Model(latitude=90.1)

    def test_latitude_range(self) -> None:
        """Latitude range -90 to 90."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="latitude",
                    type=FieldType.FLOAT,
                    required=True,
                    description="",
                    constraints=Constraints(minimum=-90.0, maximum=90.0),
                ),
            ],
        )
        Model = create_model_from_spec(spec)

        # Valid latitudes
        for lat in [-90.0, -45.0, 0.0, 45.0, 90.0]:
            instance = Model(latitude=lat)
            assert instance.latitude == lat

        # Invalid latitudes
        with pytest.raises(ValidationError):
            Model(latitude=-91.0)
        with pytest.raises(ValidationError):
            Model(latitude=91.0)

    def test_longitude_range(self) -> None:
        """Longitude range -180 to 180."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="longitude",
                    type=FieldType.FLOAT,
                    required=True,
                    description="",
                    constraints=Constraints(minimum=-180.0, maximum=180.0),
                ),
            ],
        )
        Model = create_model_from_spec(spec)

        # Valid longitudes
        for lon in [-180.0, -90.0, 0.0, 90.0, 180.0]:
            instance = Model(longitude=lon)
            assert instance.longitude == lon

        # Invalid longitudes
        with pytest.raises(ValidationError):
            Model(longitude=-181.0)
        with pytest.raises(ValidationError):
            Model(longitude=181.0)


class TestConstraintEnum:
    """Tests for enum constraint."""

    def test_enum_valid_value(self) -> None:
        """Value in enum list passes."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="status",
                    type=FieldType.STRING,
                    required=True,
                    description="",
                    constraints=Constraints(enum=["draft", "submitted", "published"]),
                ),
            ],
        )
        Model = create_model_from_spec(spec)

        for status in ["draft", "submitted", "published"]:
            instance = Model(status=status)
            assert instance.status == status

    def test_enum_invalid_value(self) -> None:
        """Value not in enum list fails."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="status",
                    type=FieldType.STRING,
                    required=True,
                    description="",
                    constraints=Constraints(enum=["draft", "submitted", "published"]),
                ),
            ],
        )
        Model = create_model_from_spec(spec)

        with pytest.raises(ValidationError):
            Model(status="unknown")

    def test_enum_case_sensitive(self) -> None:
        """Enum comparison is case-sensitive."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="status",
                    type=FieldType.STRING,
                    required=True,
                    description="",
                    constraints=Constraints(enum=["draft", "submitted", "published"]),
                ),
            ],
        )
        Model = create_model_from_spec(spec)

        with pytest.raises(ValidationError):
            Model(status="Draft")  # Capital D


class TestConstraintListItems:
    """Tests for min_items and max_items constraints.

    Note: min_items and max_items for lists are enforced via validation rules
    (ListCardinalityRule), not at the Pydantic model level. These tests verify
    that the constraints are properly stored in the spec and validated by rules.
    """

    def test_min_items_constraint_stored(self) -> None:
        """min_items constraint is stored in field spec."""
        field = FieldSpec(
            name="tags",
            type=FieldType.LIST,
            items="string",
            required=True,
            description="",
            constraints=Constraints(min_items=1),
        )
        assert field.constraints.min_items == 1

    def test_min_items_validated_by_rule(self) -> None:
        """min_items is enforced by ListCardinalityRule."""
        from metaseed.validators.rules import ListCardinalityRule

        rule = ListCardinalityRule(field="tags", min_items=1)

        # Satisfied
        errors = rule.validate({"tags": ["a"]})
        assert len(errors) == 0

        # Violated
        errors = rule.validate({"tags": []})
        assert len(errors) == 1
        assert "at least 1" in errors[0].message

    def test_max_items_constraint_stored(self) -> None:
        """max_items constraint is stored in field spec."""
        field = FieldSpec(
            name="tags",
            type=FieldType.LIST,
            items="string",
            required=True,
            description="",
            constraints=Constraints(max_items=3),
        )
        assert field.constraints.max_items == 3

    def test_max_items_validated_by_rule(self) -> None:
        """max_items is enforced by ListCardinalityRule."""
        from metaseed.validators.rules import ListCardinalityRule

        rule = ListCardinalityRule(field="tags", max_items=3)

        # Satisfied
        errors = rule.validate({"tags": ["a", "b", "c"]})
        assert len(errors) == 0

        # Violated
        errors = rule.validate({"tags": ["a", "b", "c", "d"]})
        assert len(errors) == 1
        assert "at most 3" in errors[0].message

    def test_items_range_validated_by_rule(self) -> None:
        """Combined min_items and max_items enforced by rule."""
        from metaseed.validators.rules import ListCardinalityRule

        rule = ListCardinalityRule(field="tags", min_items=1, max_items=5)

        # Valid counts
        assert len(rule.validate({"tags": ["a"]})) == 0
        assert len(rule.validate({"tags": ["a", "b", "c", "d", "e"]})) == 0

        # Too few
        errors = rule.validate({"tags": []})
        assert len(errors) == 1

        # Too many
        errors = rule.validate({"tags": ["a", "b", "c", "d", "e", "f"]})
        assert len(errors) == 1


class TestCombinedConstraints:
    """Tests for multiple constraints on the same field."""

    def test_pattern_and_length(self) -> None:
        """Pattern and length constraints together."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="code",
                    type=FieldType.STRING,
                    required=True,
                    description="",
                    constraints=Constraints(
                        pattern=r"^[A-Z]+$",
                        min_length=2,
                        max_length=5,
                    ),
                ),
            ],
        )
        Model = create_model_from_spec(spec)

        # Valid: matches pattern and length
        instance = Model(code="ABC")
        assert instance.code == "ABC"

        # Invalid: wrong pattern (lowercase)
        with pytest.raises(ValidationError):
            Model(code="abc")

        # Invalid: too short
        with pytest.raises(ValidationError):
            Model(code="A")

        # Invalid: too long
        with pytest.raises(ValidationError):
            Model(code="ABCDEF")

    def test_numeric_range(self) -> None:
        """Minimum and maximum together."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="percentage",
                    type=FieldType.FLOAT,
                    required=True,
                    description="",
                    constraints=Constraints(minimum=0.0, maximum=100.0),
                ),
            ],
        )
        Model = create_model_from_spec(spec)

        # Valid percentages
        for pct in [0.0, 50.0, 100.0]:
            instance = Model(percentage=pct)
            assert instance.percentage == pct

        # Invalid
        with pytest.raises(ValidationError):
            Model(percentage=-0.1)
        with pytest.raises(ValidationError):
            Model(percentage=100.1)


# =============================================================================
# Validation Rules
# =============================================================================


class TestValidationRuleDateRange:
    """Tests for date_range validation rule."""

    def test_valid_range(self) -> None:
        """Start before end passes."""
        from metaseed.validators.rules import DateRangeRule

        rule = DateRangeRule(start_field="start_date", end_field="end_date")
        data = {
            "start_date": datetime.date(2024, 1, 1),
            "end_date": datetime.date(2024, 12, 31),
        }
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_same_date_valid(self) -> None:
        """Same start and end date is valid."""
        from metaseed.validators.rules import DateRangeRule

        rule = DateRangeRule(start_field="start_date", end_field="end_date")
        data = {
            "start_date": datetime.date(2024, 6, 15),
            "end_date": datetime.date(2024, 6, 15),
        }
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_invalid_range(self) -> None:
        """End before start fails."""
        from metaseed.validators.rules import DateRangeRule

        rule = DateRangeRule(start_field="start_date", end_field="end_date")
        data = {
            "start_date": datetime.date(2024, 12, 31),
            "end_date": datetime.date(2024, 1, 1),
        }
        errors = rule.validate(data)
        assert len(errors) == 1

    def test_missing_field_skipped(self) -> None:
        """Missing field is skipped."""
        from metaseed.validators.rules import DateRangeRule

        rule = DateRangeRule(start_field="start_date", end_field="end_date")
        data = {"start_date": datetime.date(2024, 1, 1)}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_custom_message(self) -> None:
        """Custom error message is used."""
        from metaseed.validators.rules import DateRangeRule

        rule = DateRangeRule(
            start_field="start_date",
            end_field="end_date",
            message="Study end date must be after start date",
        )
        data = {
            "start_date": datetime.date(2024, 12, 31),
            "end_date": datetime.date(2024, 1, 1),
        }
        errors = rule.validate(data)
        assert errors[0].message == "Study end date must be after start date"


class TestValidationRuleConditional:
    """Tests for conditional validation rule."""

    def test_or_both_present(self) -> None:
        """OR: both fields present passes."""
        from metaseed.validators.rules import ConditionalRule

        rule = ConditionalRule(condition="doi OR pubmed_id")
        data = {"doi": "10.1234/example", "pubmed_id": "12345678"}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_or_one_present(self) -> None:
        """OR: one field present passes."""
        from metaseed.validators.rules import ConditionalRule

        rule = ConditionalRule(condition="doi OR pubmed_id")
        data = {"doi": "10.1234/example"}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_or_none_present(self) -> None:
        """OR: no fields present fails."""
        from metaseed.validators.rules import ConditionalRule

        rule = ConditionalRule(condition="doi OR pubmed_id")
        data = {}
        errors = rule.validate(data)
        assert len(errors) == 1

    def test_and_both_present(self) -> None:
        """AND: both fields present passes."""
        from metaseed.validators.rules import ConditionalRule

        rule = ConditionalRule(condition="latitude AND longitude")
        data = {"latitude": 45.0, "longitude": -90.0}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_and_one_missing(self) -> None:
        """AND: one field missing fails."""
        from metaseed.validators.rules import ConditionalRule

        rule = ConditionalRule(condition="latitude AND longitude")
        data = {"latitude": 45.0}
        errors = rule.validate(data)
        assert len(errors) == 1

    def test_triple_or(self) -> None:
        """Triple OR condition."""
        from metaseed.validators.rules import ConditionalRule

        rule = ConditionalRule(condition="doi OR pubmed_id OR title")

        # Any one passes
        assert len(rule.validate({"doi": "10.1234/x"})) == 0
        assert len(rule.validate({"pubmed_id": "123"})) == 0
        assert len(rule.validate({"title": "Test"})) == 0

        # None fails
        assert len(rule.validate({})) == 1


class TestValidationRuleCoordinatePair:
    """Tests for coordinate_pair validation rule."""

    def test_both_present(self) -> None:
        """Both coordinates present passes."""
        from metaseed.validators.rules import CoordinatePairRule

        rule = CoordinatePairRule(lat_field="latitude", lon_field="longitude")
        data = {"latitude": 45.0, "longitude": -90.0}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_neither_present(self) -> None:
        """Neither coordinate present passes."""
        from metaseed.validators.rules import CoordinatePairRule

        rule = CoordinatePairRule(lat_field="latitude", lon_field="longitude")
        data = {}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_only_lat(self) -> None:
        """Only latitude fails."""
        from metaseed.validators.rules import CoordinatePairRule

        rule = CoordinatePairRule(lat_field="latitude", lon_field="longitude")
        data = {"latitude": 45.0}
        errors = rule.validate(data)
        assert len(errors) == 1
        assert "longitude" in errors[0].message

    def test_only_lon(self) -> None:
        """Only longitude fails."""
        from metaseed.validators.rules import CoordinatePairRule

        rule = CoordinatePairRule(lat_field="latitude", lon_field="longitude")
        data = {"longitude": -90.0}
        errors = rule.validate(data)
        assert len(errors) == 1
        assert "latitude" in errors[0].message

    def test_custom_field_names(self) -> None:
        """Custom field names work."""
        from metaseed.validators.rules import CoordinatePairRule

        rule = CoordinatePairRule(lat_field="lat", lon_field="lon")
        data = {"lat": 45.0, "lon": -90.0}
        errors = rule.validate(data)
        assert len(errors) == 0


class TestValidationRuleCardinality:
    """Tests for cardinality validation rule."""

    def test_min_items_satisfied(self) -> None:
        """List meeting min_items passes."""
        from metaseed.validators.rules import ListCardinalityRule

        rule = ListCardinalityRule(field="samples", min_items=1)
        data = {"samples": [{"id": "S1"}]}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_min_items_violated(self) -> None:
        """Empty list violates min_items."""
        from metaseed.validators.rules import ListCardinalityRule

        rule = ListCardinalityRule(field="samples", min_items=1)
        data = {"samples": []}
        errors = rule.validate(data)
        assert len(errors) == 1

    def test_max_items_satisfied(self) -> None:
        """List within max_items passes."""
        from metaseed.validators.rules import ListCardinalityRule

        rule = ListCardinalityRule(field="samples", max_items=3)
        data = {"samples": [{"id": "S1"}, {"id": "S2"}]}
        errors = rule.validate(data)
        assert len(errors) == 0

    def test_max_items_violated(self) -> None:
        """List exceeding max_items fails."""
        from metaseed.validators.rules import ListCardinalityRule

        rule = ListCardinalityRule(field="samples", max_items=2)
        data = {"samples": [{"id": "S1"}, {"id": "S2"}, {"id": "S3"}]}
        errors = rule.validate(data)
        assert len(errors) == 1


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_optional_field_none(self) -> None:
        """Optional field can be None."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="value", type=FieldType.STRING, required=False, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(value=None)
        assert instance.value is None

    def test_required_field_cannot_be_none(self) -> None:
        """Required field cannot be None."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="value", type=FieldType.STRING, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        with pytest.raises(ValidationError):
            Model(value=None)

    def test_extra_fields_rejected(self) -> None:
        """Extra fields not in spec are rejected."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="name", type=FieldType.STRING, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        with pytest.raises(ValidationError):
            Model(name="test", extra="value")

    def test_assignment_validation(self) -> None:
        """Assignment validation enforces constraints."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="count",
                    type=FieldType.INTEGER,
                    required=True,
                    description="",
                    constraints=Constraints(minimum=0, maximum=100),
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(count=50)

        # Valid assignment
        instance.count = 75
        assert instance.count == 75

        # Invalid assignment
        with pytest.raises(ValidationError):
            instance.count = 150

    def test_whitespace_string(self) -> None:
        """Whitespace-only string handling."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="name", type=FieldType.STRING, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        # Whitespace-only is technically valid (no min_length constraint)
        instance = Model(name="   ")
        assert instance.name == "   "

    def test_zero_is_valid_required_integer(self) -> None:
        """Zero is valid for required integer field."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="count", type=FieldType.INTEGER, required=True, description=""
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(count=0)
        assert instance.count == 0

    def test_false_is_valid_required_boolean(self) -> None:
        """False is valid for required boolean field."""
        spec = EntitySpec(
            name="Test",
            version="1.0",
            description="Test",
            fields=[
                FieldSpec(
                    name="enabled",
                    type=FieldType.BOOLEAN,
                    required=True,
                    description="",
                ),
            ],
        )
        Model = create_model_from_spec(spec)
        instance = Model(enabled=False)
        assert instance.enabled is False
