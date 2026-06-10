"""Tests for custom types."""

from pydantic import BaseModel

from metaseed.models.types import OntologyTerm, is_valid_ontology_term


class TestOntologyTerm:
    """Tests for OntologyTerm type."""

    def test_valid_ontology_term(self) -> None:
        """Valid ontology term with prefix:id format."""

        class Model(BaseModel):
            term: OntologyTerm

        m = Model(term="GO:0001234")
        assert m.term == "GO:0001234"

    def test_valid_ontology_term_with_underscore(self) -> None:
        """Valid ontology term with underscore in prefix."""

        class Model(BaseModel):
            term: OntologyTerm

        m = Model(term="PPEO_0000001")
        assert m.term == "PPEO_0000001"

    def test_valid_url_ontology_term(self) -> None:
        """Valid ontology term as URL."""

        class Model(BaseModel):
            term: OntologyTerm

        m = Model(term="http://purl.org/ppeo/PPEO.owl#investigation")
        assert m.term == "http://purl.org/ppeo/PPEO.owl#investigation"

    def test_any_string_accepted(self) -> None:
        """OntologyTerm accepts any string (validation is separate)."""

        class Model(BaseModel):
            term: OntologyTerm

        # Invalid format is accepted - validation is done separately
        m = Model(term="invalid term without colon or underscore")
        assert m.term == "invalid term without colon or underscore"

    def test_optional_ontology_term(self) -> None:
        """Optional ontology term can be None."""

        class Model(BaseModel):
            term: OntologyTerm | None = None

        m = Model()
        assert m.term is None


class TestIsValidOntologyTerm:
    """Tests for is_valid_ontology_term function."""

    def test_valid_prefix_colon_id(self) -> None:
        """Valid format: PREFIX:ID."""
        assert is_valid_ontology_term("GO:0001234")
        assert is_valid_ontology_term("PATO:0000001")
        assert is_valid_ontology_term("CO_321:0000994")

    def test_valid_prefix_underscore_id(self) -> None:
        """Valid format: PREFIX_ID."""
        assert is_valid_ontology_term("PPEO_0000001")
        assert is_valid_ontology_term("OBI_0000070")

    def test_valid_url(self) -> None:
        """Valid format: URL."""
        assert is_valid_ontology_term("http://purl.org/ppeo/PPEO.owl#investigation")
        assert is_valid_ontology_term("https://example.com/ontology#term")

    def test_invalid_no_separator(self) -> None:
        """Invalid: no colon or underscore separator."""
        assert not is_valid_ontology_term("invalid")
        assert not is_valid_ontology_term("mouse")
        assert not is_valid_ontology_term("some term")

    def test_invalid_empty(self) -> None:
        """Invalid: empty string."""
        assert not is_valid_ontology_term("")
