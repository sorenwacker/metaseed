"""Tests for the interactive facade module."""

import pytest

from miappe_api.facade import EntityHelper, ProfileFacade, isa, miappe


class TestProfileFacade:
    """Tests for ProfileFacade class."""

    def test_create_miappe_facade(self) -> None:
        """Create a MIAPPE profile facade."""
        facade = ProfileFacade("miappe", "1.1")

        assert facade.profile == "miappe"
        assert facade.version == "1.1"

    def test_create_isa_facade(self) -> None:
        """Create an ISA profile facade."""
        facade = ProfileFacade("isa", "1.0")

        assert facade.profile == "isa"
        assert facade.version == "1.0"

    def test_list_entities(self) -> None:
        """List available entities."""
        facade = ProfileFacade("miappe", "1.1")

        entities = facade.entities
        assert isinstance(entities, list)
        assert len(entities) > 0
        assert "Investigation" in entities

    def test_get_entity_helper(self) -> None:
        """Get an entity helper via attribute access."""
        facade = ProfileFacade("miappe", "1.1")

        helper = facade.Investigation
        assert isinstance(helper, EntityHelper)
        assert helper.name == "Investigation"

    def test_case_insensitive_access(self) -> None:
        """Access entities case-insensitively."""
        facade = ProfileFacade("miappe", "1.1")

        # These should all work
        helper1 = facade.Investigation
        helper2 = facade.investigation

        assert helper1.name == helper2.name

    def test_invalid_entity_raises(self) -> None:
        """Accessing invalid entity raises AttributeError."""
        facade = ProfileFacade("miappe", "1.1")

        with pytest.raises(AttributeError) as exc_info:
            _ = facade.NonexistentEntity

        assert "NonexistentEntity" in str(exc_info.value)
        assert "not found" in str(exc_info.value)

    def test_dir_includes_entities(self) -> None:
        """dir() includes entity names for tab completion."""
        facade = ProfileFacade("miappe", "1.1")

        attrs = dir(facade)
        assert "Investigation" in attrs
        assert "Study" in attrs
        assert "help" in attrs
        assert "entities" in attrs

    def test_search_entities(self) -> None:
        """Search for entities or fields."""
        facade = ProfileFacade("miappe", "1.1")

        results = facade.search("investigation")
        assert len(results) > 0
        assert any("Investigation" in r for r in results)

    def test_repr(self) -> None:
        """Repr shows profile info."""
        facade = ProfileFacade("miappe", "1.1")

        repr_str = repr(facade)
        assert "miappe" in repr_str
        assert "1.1" in repr_str

    def test_default_version(self) -> None:
        """Use latest version when not specified."""
        facade = ProfileFacade("miappe")

        # Should use latest version without raising
        assert facade.version is not None
        assert len(facade.entities) > 0


class TestEntityHelper:
    """Tests for EntityHelper class."""

    @pytest.fixture
    def miappe_facade(self) -> ProfileFacade:
        """Create MIAPPE facade."""
        return ProfileFacade("miappe", "1.1")

    @pytest.fixture
    def investigation_helper(self, miappe_facade: ProfileFacade) -> EntityHelper:
        """Get Investigation entity helper."""
        return miappe_facade.Investigation

    def test_name_property(self, investigation_helper: EntityHelper) -> None:
        """Get entity name."""
        assert investigation_helper.name == "Investigation"

    def test_description_property(self, investigation_helper: EntityHelper) -> None:
        """Get entity description."""
        assert len(investigation_helper.description) > 0

    def test_required_fields(self, investigation_helper: EntityHelper) -> None:
        """Get required fields."""
        required = investigation_helper.required_fields

        assert isinstance(required, list)
        assert "unique_id" in required
        assert "title" in required

    def test_optional_fields(self, investigation_helper: EntityHelper) -> None:
        """Get optional fields."""
        optional = investigation_helper.optional_fields

        assert isinstance(optional, list)
        # Description should be optional
        assert len(optional) > 0

    def test_all_fields(self, investigation_helper: EntityHelper) -> None:
        """Get all fields."""
        all_fields = investigation_helper.all_fields
        required = investigation_helper.required_fields
        optional = investigation_helper.optional_fields

        assert len(all_fields) == len(required) + len(optional)

    def test_nested_fields(self, investigation_helper: EntityHelper) -> None:
        """Get nested entity fields."""
        nested = investigation_helper.nested_fields

        assert isinstance(nested, dict)
        # Investigation has studies as nested
        assert "studies" in nested
        assert nested["studies"] == "Study"

    def test_field_info(self, investigation_helper: EntityHelper) -> None:
        """Get detailed field information."""
        info = investigation_helper.field_info("unique_id")

        assert info["name"] == "unique_id"
        assert info["required"] is True
        assert "type" in info
        assert "description" in info

    def test_field_info_not_found(self, investigation_helper: EntityHelper) -> None:
        """Getting info for unknown field raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            investigation_helper.field_info("nonexistent_field")

        assert "nonexistent_field" in str(exc_info.value)

    def test_create_entity(self, investigation_helper: EntityHelper) -> None:
        """Create an entity instance."""
        inv = investigation_helper.create(
            unique_id="INV-001",
            title="Test Investigation",
        )

        assert inv.unique_id == "INV-001"
        assert inv.title == "Test Investigation"

    def test_call_creates_entity(self, investigation_helper: EntityHelper) -> None:
        """Calling helper creates entity."""
        inv = investigation_helper(
            unique_id="INV-002",
            title="Another Investigation",
        )

        assert inv.unique_id == "INV-002"

    def test_repr(self, investigation_helper: EntityHelper) -> None:
        """Repr shows field counts."""
        repr_str = repr(investigation_helper)

        assert "Investigation" in repr_str
        assert "required" in repr_str
        assert "optional" in repr_str


class TestConvenienceFunctions:
    """Tests for miappe() and isa() convenience functions."""

    def test_miappe_function(self) -> None:
        """miappe() returns MIAPPE facade."""
        m = miappe()

        assert m.profile == "miappe"
        assert "Investigation" in m.entities

    def test_miappe_with_version(self) -> None:
        """miappe() accepts version parameter."""
        m = miappe(version="1.1")

        assert m.version == "1.1"

    def test_isa_function(self) -> None:
        """isa() returns ISA facade."""
        i = isa()

        assert i.profile == "isa"
        assert "Investigation" in i.entities
        assert "Study" in i.entities
        assert "Assay" in i.entities

    def test_isa_with_version(self) -> None:
        """isa() accepts version parameter."""
        i = isa(version="1.0")

        assert i.version == "1.0"


class TestISAFacade:
    """Tests specific to ISA profile facade."""

    @pytest.fixture
    def isa_facade(self) -> ProfileFacade:
        """Create ISA facade."""
        return ProfileFacade("isa", "1.0")

    def test_isa_entities(self, isa_facade: ProfileFacade) -> None:
        """ISA profile has expected entities."""
        entities = isa_facade.entities

        assert "Investigation" in entities
        assert "Study" in entities
        assert "Assay" in entities
        assert "Person" in entities
        assert "Protocol" in entities
        assert "Sample" in entities
        assert "Source" in entities

    def test_create_isa_investigation(self, isa_facade: ProfileFacade) -> None:
        """Create ISA Investigation via facade."""
        inv = isa_facade.Investigation(
            identifier="ISA-001",
            title="ISA Test Investigation",
        )

        assert inv.identifier == "ISA-001"
        assert inv.title == "ISA Test Investigation"

    def test_isa_nested_fields(self, isa_facade: ProfileFacade) -> None:
        """ISA entities have nested fields."""
        inv_helper = isa_facade.Investigation
        nested = inv_helper.nested_fields

        assert "studies" in nested
        assert nested["studies"] == "Study"


class TestCombinedFacade:
    """Tests specific to combined ISA+MIAPPE profile facade."""

    @pytest.fixture
    def combined_facade(self) -> ProfileFacade:
        """Create combined facade."""
        return ProfileFacade("combined", "1.0")

    def test_combined_loads(self, combined_facade: ProfileFacade) -> None:
        """Combined profile loads successfully."""
        assert combined_facade.profile == "combined"
        assert combined_facade.version == "1.0"

    def test_combined_has_isa_entities(self, combined_facade: ProfileFacade) -> None:
        """Combined profile has ISA-specific entities."""
        entities = combined_facade.entities

        assert "Assay" in entities
        assert "Protocol" in entities
        assert "Source" in entities
        assert "Extract" in entities
        assert "Process" in entities

    def test_combined_has_miappe_entities(self, combined_facade: ProfileFacade) -> None:
        """Combined profile has MIAPPE-specific entities."""
        entities = combined_facade.entities

        assert "BiologicalMaterial" in entities
        assert "ObservationUnit" in entities
        assert "ObservedVariable" in entities
        assert "Event" in entities
        assert "Environment" in entities

    def test_combined_has_shared_entities(self, combined_facade: ProfileFacade) -> None:
        """Combined profile has shared core entities."""
        entities = combined_facade.entities

        assert "Investigation" in entities
        assert "Study" in entities
        assert "Sample" in entities
        assert "Person" in entities
        assert "Factor" in entities
        assert "DataFile" in entities

    def test_combined_create_investigation(self, combined_facade: ProfileFacade) -> None:
        """Create Investigation from combined profile."""
        inv = combined_facade.Investigation(
            identifier="COMB-001",
            title="Combined Test Investigation",
        )

        assert inv.identifier == "COMB-001"
        assert inv.title == "Combined Test Investigation"

    def test_combined_create_miappe_entity(self, combined_facade: ProfileFacade) -> None:
        """Create MIAPPE-specific entity from combined profile."""
        bm = combined_facade.BiologicalMaterial(
            identifier="BM-001",
            organism="Zea mays",
        )

        assert bm.identifier == "BM-001"
        assert bm.organism == "Zea mays"

    def test_combined_create_isa_entity(self, combined_facade: ProfileFacade) -> None:
        """Create ISA-specific entity from combined profile."""
        prot = combined_facade.Protocol(
            name="Test Protocol",
            protocol_type="sample collection",
        )

        assert prot.name == "Test Protocol"
        assert prot.protocol_type == "sample collection"
