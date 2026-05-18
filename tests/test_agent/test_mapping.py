"""Tests for the mapping module."""

from metaseed.agent.mapping import (
    ColumnMapping,
    FieldMapping,
    compute_similarity,
    create_mapping,
    mapping_from_dict,
    mapping_to_dict,
    normalize_name,
)


class TestNormalizeName:
    """Tests for normalize_name function."""

    def test_lowercase(self) -> None:
        """Convert to lowercase."""
        assert normalize_name("HelloWorld") == "hello world"

    def test_snake_case(self) -> None:
        """Handle snake_case."""
        assert normalize_name("hello_world") == "hello world"

    def test_kebab_case(self) -> None:
        """Handle kebab-case."""
        assert normalize_name("hello-world") == "hello world"

    def test_camel_case(self) -> None:
        """Handle camelCase."""
        assert normalize_name("helloWorld") == "hello world"

    def test_mixed(self) -> None:
        """Handle mixed case."""
        assert normalize_name("Hello_World-Test") == "hello world test"

    def test_special_chars(self) -> None:
        """Remove special characters."""
        assert normalize_name("hello@world!") == "helloworld"


class TestComputeSimilarity:
    """Tests for compute_similarity function."""

    def test_exact_match(self) -> None:
        """Exact match returns 1.0."""
        assert compute_similarity("identifier", "identifier") == 1.0

    def test_case_insensitive(self) -> None:
        """Case differences don't matter."""
        assert compute_similarity("Identifier", "identifier") == 1.0

    def test_format_differences(self) -> None:
        """Different formats of same name match."""
        # snake_case vs camelCase
        score = compute_similarity("experiment_id", "experimentId")
        assert score >= 0.7

    def test_partial_match(self) -> None:
        """Partial matches get intermediate scores."""
        score = compute_similarity("investigation_title", "title")
        assert 0.3 < score < 0.9

    def test_no_match(self) -> None:
        """Unrelated names get low scores."""
        score = compute_similarity("identifier", "xyz123")
        assert score < 0.5


class TestFieldMapping:
    """Tests for FieldMapping class."""

    def test_create_with_column(self) -> None:
        """Create mapping with source column."""
        mapping = FieldMapping(
            field_name="identifier",
            source_column="id",
            confidence=0.9,
        )

        assert mapping.field_name == "identifier"
        assert mapping.source_column == "id"
        assert mapping.confidence == 0.9
        assert mapping.default_value is None

    def test_create_with_default(self) -> None:
        """Create mapping with default value."""
        mapping = FieldMapping(
            field_name="status",
            source_column=None,
            default_value="active",
            confidence=1.0,
        )

        assert mapping.source_column is None
        assert mapping.default_value == "active"


class TestColumnMapping:
    """Tests for ColumnMapping class."""

    def test_create_empty(self) -> None:
        """Create empty mapping."""
        mapping = ColumnMapping(entity_name="Investigation")

        assert mapping.entity_name == "Investigation"
        assert mapping.fields == []
        assert mapping.source_table is None

    def test_create_with_fields(self) -> None:
        """Create mapping with fields."""
        mapping = ColumnMapping(
            entity_name="Investigation",
            fields=[
                FieldMapping(field_name="identifier", source_column="id"),
                FieldMapping(field_name="title", source_column="name"),
            ],
            source_table="Sheet1",
        )

        assert len(mapping.fields) == 2
        assert mapping.source_table == "Sheet1"

    def test_get_field_mapping(self) -> None:
        """Get a specific field mapping."""
        mapping = ColumnMapping(
            entity_name="Test",
            fields=[
                FieldMapping(field_name="foo", source_column="col1"),
                FieldMapping(field_name="bar", source_column="col2"),
            ],
        )

        foo = mapping.get_field_mapping("foo")
        assert foo is not None
        assert foo.source_column == "col1"

        missing = mapping.get_field_mapping("nonexistent")
        assert missing is None

    def test_set_field_mapping_new(self) -> None:
        """Add a new field mapping."""
        mapping = ColumnMapping(entity_name="Test", fields=[])

        mapping.set_field_mapping("foo", "col1", confidence=0.9)

        assert len(mapping.fields) == 1
        assert mapping.fields[0].field_name == "foo"
        assert mapping.fields[0].source_column == "col1"
        assert mapping.fields[0].confidence == 0.9

    def test_set_field_mapping_update(self) -> None:
        """Update an existing field mapping."""
        mapping = ColumnMapping(
            entity_name="Test",
            fields=[
                FieldMapping(field_name="foo", source_column="col1", confidence=0.5),
            ],
        )

        mapping.set_field_mapping("foo", "col2", confidence=1.0)

        assert len(mapping.fields) == 1
        assert mapping.fields[0].source_column == "col2"
        assert mapping.fields[0].confidence == 1.0


class TestCreateMapping:
    """Tests for create_mapping function."""

    def test_create(self) -> None:
        """Create a ColumnMapping from field mappings."""
        field_mappings = [
            FieldMapping(field_name="identifier", source_column="id"),
            FieldMapping(field_name="title", source_column="name"),
        ]

        mapping = create_mapping("Investigation", field_mappings, "data")

        assert mapping.entity_name == "Investigation"
        assert len(mapping.fields) == 2
        assert mapping.source_table == "data"


class TestMappingToDictAndBack:
    """Tests for mapping serialization."""

    def test_to_dict(self) -> None:
        """Convert mapping to dictionary."""
        mapping = ColumnMapping(
            entity_name="Investigation",
            fields=[
                FieldMapping(
                    field_name="identifier",
                    source_column="id",
                    confidence=0.9,
                    default_value=None,
                ),
                FieldMapping(
                    field_name="status",
                    source_column=None,
                    confidence=1.0,
                    default_value="active",
                ),
            ],
            source_table="Sheet1",
        )

        data = mapping_to_dict(mapping)

        assert data["entity"] == "Investigation"
        assert data["source_table"] == "Sheet1"
        assert "identifier" in data["fields"]
        assert data["fields"]["identifier"]["column"] == "id"
        assert data["fields"]["status"]["default"] == "active"

    def test_from_dict(self) -> None:
        """Create mapping from dictionary."""
        data = {
            "entity": "Investigation",
            "source_table": "Sheet1",
            "fields": {
                "identifier": {"column": "id", "confidence": 0.9},
                "status": {"column": None, "default": "active"},
            },
        }

        mapping = mapping_from_dict(data)

        assert mapping.entity_name == "Investigation"
        assert mapping.source_table == "Sheet1"
        assert len(mapping.fields) == 2

        id_field = mapping.get_field_mapping("identifier")
        assert id_field is not None
        assert id_field.source_column == "id"

        status_field = mapping.get_field_mapping("status")
        assert status_field is not None
        assert status_field.default_value == "active"

    def test_round_trip(self) -> None:
        """Convert to dict and back preserves data."""
        original = ColumnMapping(
            entity_name="Test",
            fields=[
                FieldMapping(field_name="a", source_column="col_a", confidence=0.8),
                FieldMapping(field_name="b", source_column=None, default_value="default"),
            ],
            source_table=0,
        )

        data = mapping_to_dict(original)
        restored = mapping_from_dict(data)

        assert restored.entity_name == original.entity_name
        assert len(restored.fields) == len(original.fields)
