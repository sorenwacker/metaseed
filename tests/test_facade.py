"""Tests for the interactive facade module."""

from unittest.mock import MagicMock

import pytest

from metaseed.facade import (
    EntityHelper,
    ProfileFacade,
    isa,
    miappe,
    validate_ontology_term,
)
from metaseed.services.ontology import (
    OntologyService,
    get_ontology_service,
    reset_ontology_service,
)
from metaseed.specs.loader import SpecLoader
from metaseed.specs.schema import (
    EntityDefSpec,
    EntitySpec,
    FieldSpec,
    FieldType,
    ProfileSpec,
)


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

    def test_require_helper_resolves_case_insensitively(self) -> None:
        """require_helper matches an entity type ignoring case."""
        facade = ProfileFacade("miappe", "1.1")

        helper = facade.require_helper("study")
        assert helper.name == "Study"

    def test_require_helper_unknown_lists_supported_types(self) -> None:
        """An unsupported type is rejected with the profile's vocabulary.

        The LLM driving the MCP tools must learn what the active profile
        expects instead of receiving a dead-end rejection.
        """
        facade = ProfileFacade("miappe", "1.1")

        with pytest.raises(ValueError) as exc_info:
            facade.require_helper("Banana")

        message = str(exc_info.value)
        assert "is not supported by profile 'miappe'" in message
        assert "Investigation" in message  # supported types are listed

    def test_require_helper_suggests_closest_match(self) -> None:
        """A near-miss type name yields a 'did you mean' suggestion."""
        facade = ProfileFacade("miappe", "1.1")

        with pytest.raises(ValueError, match="Did you mean 'Investigation'"):
            facade.require_helper("Investigaton")

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

    def test_get_label_uses_first_field(
        self, investigation_helper: EntityHelper
    ) -> None:
        """get_label uses first field (unique_id for Investigation) by convention."""
        inv = investigation_helper.create(
            unique_id="INV-001",
            title="My Research Project",
        )
        label = investigation_helper.get_label(inv)
        # By convention, first field (unique_id) is used as label
        assert label == "INV-001"

    def test_get_label_with_dict(self, investigation_helper: EntityHelper) -> None:
        """get_label works with dict input, using first field by convention."""
        data = {"unique_id": "INV-002", "title": "Dict Investigation"}
        label = investigation_helper.get_label(data)
        # By convention, first field (unique_id) is used as label
        assert label == "INV-002"

    def test_get_label_with_only_first_field(
        self, investigation_helper: EntityHelper
    ) -> None:
        """get_label uses first field value."""
        data = {"unique_id": "INV-003"}
        label = investigation_helper.get_label(data)
        assert label == "INV-003"

    def test_get_label_person_name(self, miappe_facade: ProfileFacade) -> None:
        """get_label combines first_name and last_name for Person."""
        person_helper = miappe_facade.Person
        person = person_helper.create(
            name="Dr. Jane Smith",
        )
        label = person_helper.get_label(person)
        assert label == "Dr. Jane Smith"


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


class TestEntityHelperOutput:
    """Tests for EntityHelper output methods (help, example)."""

    @pytest.fixture
    def miappe_facade(self) -> ProfileFacade:
        """Create MIAPPE facade."""
        return ProfileFacade("miappe", "1.1")

    def test_help_prints_entity_info(
        self, miappe_facade: ProfileFacade, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """help() prints entity information."""
        miappe_facade.Investigation.help()
        output = capsys.readouterr().out

        assert "Investigation" in output
        assert "Required Fields" in output
        assert "Optional Fields" in output
        assert "unique_id" in output
        assert "title" in output

    def test_help_shows_ontology_term(
        self, miappe_facade: ProfileFacade, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """help() shows ontology term if present."""
        miappe_facade.Investigation.help()
        output = capsys.readouterr().out

        # Investigation should have an ontology term
        assert "Ontology" in output or "investigation" in output.lower()

    def test_example_prints_code(
        self, miappe_facade: ProfileFacade, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """example() prints example code."""
        miappe_facade.Investigation.example()
        output = capsys.readouterr().out

        assert "Create a Investigation" in output
        assert "profile.Investigation" in output
        assert ".create(" in output

    def test_example_includes_required_fields(
        self, miappe_facade: ProfileFacade, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """example() includes required fields."""
        miappe_facade.Investigation.example()
        output = capsys.readouterr().out

        assert "unique_id=" in output
        assert "title=" in output

    def test_ontology_term_property(self, miappe_facade: ProfileFacade) -> None:
        """ontology_term property returns ontology identifier."""
        term = miappe_facade.Investigation.ontology_term

        # May be None or a string
        assert term is None or isinstance(term, str)

    def test_example_data_property(self, miappe_facade: ProfileFacade) -> None:
        """example_data property returns example values."""
        data = miappe_facade.Investigation.example_data

        assert isinstance(data, dict)

    def test_field_info_with_constraints(self, miappe_facade: ProfileFacade) -> None:
        """field_info includes constraints when present."""
        # unique_id usually has pattern constraint
        info = miappe_facade.Investigation.field_info("unique_id")

        assert "name" in info
        # Constraints may or may not be present
        if "constraints" in info:
            assert isinstance(info["constraints"], dict)


class TestProfileFacadeOutput:
    """Tests for ProfileFacade output methods."""

    def test_help_profile_overview(self, capsys: pytest.CaptureFixture[str]) -> None:
        """help() without argument shows profile overview."""
        facade = ProfileFacade("miappe", "1.1")
        facade.help()
        output = capsys.readouterr().out

        assert "MIAPPE" in output
        assert "1.1" in output
        assert "Entities" in output
        assert "Usage" in output

    def test_help_specific_entity(self, capsys: pytest.CaptureFixture[str]) -> None:
        """help() with entity name shows entity help."""
        facade = ProfileFacade("miappe", "1.1")
        facade.help("Investigation")
        output = capsys.readouterr().out

        assert "Investigation" in output
        assert "Required Fields" in output

    def test_private_attr_raises(self) -> None:
        """Accessing private attributes raises AttributeError."""
        facade = ProfileFacade("miappe", "1.1")

        with pytest.raises(AttributeError):
            _ = facade._private_attr

    def test_search_field_names(self) -> None:
        """search finds field names."""
        facade = ProfileFacade("miappe", "1.1")

        results = facade.search("unique_id")
        assert len(results) > 0
        assert any("unique_id" in r for r in results)

    def test_invalid_profile_raises(self) -> None:
        """Creating facade with invalid profile raises."""
        from metaseed.specs.loader import SpecLoadError

        with pytest.raises(SpecLoadError):
            ProfileFacade("nonexistent_profile", "1.0")


class TestDependencyInjection:
    """Tests for ProfileFacade dependency injection support."""

    @pytest.fixture
    def mock_loader(self) -> MagicMock:
        """Create a mock SpecLoader."""
        loader = MagicMock(spec=SpecLoader)
        loader.list_versions.return_value = ["1.0", "2.0"]
        loader.list_entities.return_value = ["TestEntity"]
        loader.load_entity.return_value = EntitySpec(
            name="TestEntity",
            version="2.0",
            description="Test entity",
            ontology_term=None,
            fields=[
                FieldSpec(
                    name="id", type=FieldType.STRING, required=True, description="ID"
                ),
            ],
            example=None,
        )
        return loader

    @pytest.fixture
    def sample_spec(self) -> ProfileSpec:
        """Create a sample ProfileSpec for testing."""
        return ProfileSpec(
            version="3.0",
            name="test-profile",
            description="Test profile",
            entities={
                "CustomEntity": EntityDefSpec(
                    description="A custom entity for testing",
                    fields=[
                        FieldSpec(
                            name="identifier",
                            type=FieldType.STRING,
                            required=True,
                            description="Unique identifier",
                        ),
                        FieldSpec(
                            name="name",
                            type=FieldType.STRING,
                            required=False,
                            description="Display name",
                        ),
                    ],
                ),
            },
        )

    def test_inject_loader(self, mock_loader: MagicMock) -> None:
        """ProfileFacade uses injected loader."""
        facade = ProfileFacade("miappe", version="2.0", loader=mock_loader)

        # Should use the mock loader's list_entities
        mock_loader.list_entities.assert_called_once_with("2.0")
        assert facade.version == "2.0"

    def test_inject_loader_version_autodetect(self, mock_loader: MagicMock) -> None:
        """Injected loader used for version autodetection."""
        facade = ProfileFacade("miappe", loader=mock_loader)

        # Should call list_versions on mock loader
        mock_loader.list_versions.assert_called_once()
        # Should use last version from mock
        assert facade.version == "2.0"

    def test_inject_spec_bypasses_loader(self, sample_spec: ProfileSpec) -> None:
        """Injected spec bypasses loader for entity loading."""
        mock_loader = MagicMock(spec=SpecLoader)

        facade = ProfileFacade("test-profile", loader=mock_loader, spec=sample_spec)

        # Loader should not be used for entity loading
        mock_loader.list_entities.assert_not_called()
        mock_loader.load_entity.assert_not_called()

        # Should have entities from spec
        assert "CustomEntity" in facade.entities
        assert facade.version == "3.0"

    def test_spec_version_takes_precedence(self, sample_spec: ProfileSpec) -> None:
        """Spec version takes precedence over explicit version parameter."""
        facade = ProfileFacade("test-profile", version="1.0", spec=sample_spec)

        # Spec version (3.0) should override the explicit version (1.0)
        assert facade.version == "3.0"

    def test_inject_both_loader_and_spec(
        self, mock_loader: MagicMock, sample_spec: ProfileSpec
    ) -> None:
        """Both loader and spec can be provided; spec is used for entities."""
        facade = ProfileFacade("test-profile", loader=mock_loader, spec=sample_spec)

        # Loader should not be used since spec is provided
        mock_loader.list_entities.assert_not_called()

        # Entities come from spec
        assert "CustomEntity" in facade.entities
        assert facade.version == "3.0"

    def test_backward_compatibility_positional(self) -> None:
        """Existing positional argument usage still works."""
        facade = ProfileFacade("miappe", "1.1")

        assert facade.profile == "miappe"
        assert facade.version == "1.1"
        assert len(facade.entities) > 0

    def test_backward_compatibility_keyword(self) -> None:
        """Existing keyword argument usage still works."""
        facade = ProfileFacade(profile="miappe", version="1.1")

        assert facade.profile == "miappe"
        assert facade.version == "1.1"
        assert len(facade.entities) > 0

    def test_entity_creation_with_injected_spec(self, sample_spec: ProfileSpec) -> None:
        """Entities created from injected spec work normally."""
        facade = ProfileFacade("test-profile", spec=sample_spec)

        # Get entity helper
        helper = facade.CustomEntity
        assert helper.name == "CustomEntity"
        assert "identifier" in helper.required_fields
        assert "name" in helper.optional_fields

        # Create instance
        instance = helper.create(identifier="TEST-001", name="Test Instance")
        assert instance.identifier == "TEST-001"
        assert instance.name == "Test Instance"


class TestOntologyValidation:
    """Tests for ontology term validation using OntologyService."""

    def setup_method(self) -> None:
        """Reset ontology service before each test."""
        reset_ontology_service()

    def teardown_method(self) -> None:
        """Clean up after each test."""
        reset_ontology_service()

    def test_ontology_service_singleton(self) -> None:
        """get_ontology_service returns the same instance."""
        service1 = get_ontology_service()
        service2 = get_ontology_service()
        assert service1 is service2

    def test_ontology_service_cache(self) -> None:
        """OntologyService caches results."""
        service = OntologyService(cache_ttl=3600)

        # Manually populate cache
        import time

        from metaseed.services.ontology import CacheEntry, OntologyTerm

        service._cache["term:CACHED:0001"] = CacheEntry(
            value=OntologyTerm(term_id="CACHED:0001", label="Test Term"),
            expires_at=time.time() + 3600,
        )
        service._cache["term:CACHED:0002"] = CacheEntry(
            value=None,  # Cached negative result
            expires_at=time.time() + 3600,
        )

        # Validate using cache
        is_valid, warning = service.validate_term_sync("CACHED:0001")
        assert is_valid is True
        assert warning is None

        is_valid, warning = service.validate_term_sync("CACHED:0002")
        assert is_valid is False
        assert "not found" in warning

    def test_ontology_service_cache_clear(self) -> None:
        """Cache can be cleared."""
        service = OntologyService()
        import time

        from metaseed.services.ontology import CacheEntry, OntologyTerm

        service._cache["term:TEST:0001"] = CacheEntry(
            value=OntologyTerm(term_id="TEST:0001", label="Test"),
            expires_at=time.time() + 3600,
        )

        assert len(service._cache) == 1
        service.clear_cache()
        assert len(service._cache) == 0

    def test_ontology_service_cache_stats(self) -> None:
        """Cache stats are reported correctly."""
        service = OntologyService()
        import time

        from metaseed.services.ontology import CacheEntry, OntologyTerm

        # Add valid entry
        service._cache["term:VALID:0001"] = CacheEntry(
            value=OntologyTerm(term_id="VALID:0001", label="Valid"),
            expires_at=time.time() + 3600,
        )
        # Add expired entry
        service._cache["term:EXPIRED:0001"] = CacheEntry(
            value=OntologyTerm(term_id="EXPIRED:0001", label="Expired"),
            expires_at=time.time() - 1,  # Already expired
        )

        stats = service.get_cache_stats()
        assert stats["total_entries"] == 2
        assert stats["expired_entries"] == 1
        assert stats["valid_entries"] == 1

    def test_validate_ontology_term_empty(self) -> None:
        """Empty term values are considered valid."""
        is_valid, warning = validate_ontology_term("")
        assert is_valid is True
        assert warning is None

        is_valid, warning = validate_ontology_term(None)
        assert is_valid is True
        assert warning is None

    def test_validate_ontology_term_no_prefix(self) -> None:
        """Terms without prefix are skipped (assumed valid)."""
        is_valid, warning = validate_ontology_term("nocolon")
        assert is_valid is True
        assert warning is None

    def test_entity_helper_validate_ontology_terms(self) -> None:
        """EntityHelper can validate ontology terms in data."""
        # Create a spec with an ontology_term field
        spec = EntitySpec(
            name="TestEntity",
            version="1.0",
            fields=[
                FieldSpec(name="identifier", type=FieldType.STRING, required=True),
                FieldSpec(
                    name="organism", type=FieldType.ONTOLOGY_TERM, required=False
                ),
            ],
        )
        import time

        from metaseed.models.factory import create_model_from_spec
        from metaseed.services.ontology import CacheEntry

        model = create_model_from_spec(spec)
        helper = EntityHelper("TestEntity", spec, model, "test", "1.0")

        # Pre-populate service cache with invalid term (None = not found)
        service = get_ontology_service()
        service._cache["term:INVALID:9999"] = CacheEntry(
            value=None,
            expires_at=time.time() + 3600,
        )

        warnings = helper.validate_ontology_terms(
            {"identifier": "TEST-001", "organism": "INVALID:9999"}, warn=False
        )

        assert len(warnings) == 1
        assert "INVALID:9999" in warnings[0]


class TestEntityStoreIndex:
    """Tests for EntityStore identifier-index management."""

    @staticmethod
    def _make_store():
        """Build an EntityStore whose helper exposes no extra identifier field."""
        from pydantic import BaseModel

        from metaseed.facade.store import EntityStore

        class _Model(BaseModel):
            alias: str | None = None
            unique_id: str | None = None
            study_ref: str | None = None

        helper = MagicMock()
        helper.identifier_field = None
        helper.reference_fields = ["study_ref"]
        helper.all_fields = ["alias", "unique_id", "study_ref"]

        def create_instance(_entity_type, data):
            return _Model(**{k: v for k, v in data.items() if k in _Model.model_fields})

        return EntityStore(
            helper_getter=lambda _entity_type: helper,
            instance_creator=create_instance,
        )

    def test_delete_entity_preserves_index_owned_by_other_node(self) -> None:
        """Deleting a node must not drop an index entry owned by a surviving node.

        When two nodes share an identifier value, the index points at whichever
        was added last. Deleting the earlier node must leave that index entry
        intact so the surviving node stays resolvable via get_entity_by_ref.
        """
        store = self._make_store()

        first = store.add_entity("Study", {"alias": "shared"})
        second = store.add_entity("Study", {"alias": "shared"})

        assert store._index["shared"] == second.id

        store.delete_entity(first.id)

        assert store.get_entity_by_ref("shared") is not None
        assert store._index["shared"] == second.id

    def test_reload_indexes_all_identifier_fields(self) -> None:
        """load_from_dict must index every identifier field, like add_entity.

        A node reloaded from disk must be resolvable by any of its identifier
        values, not only the helper's primary identifier field.
        """
        store = self._make_store()

        store.load_from_dict([{"_type": "Study", "unique_id": "STU1", "alias": "A1"}])

        assert store.get_entity_by_ref("STU1") is not None
        assert store.get_entity_by_ref("A1") is not None
