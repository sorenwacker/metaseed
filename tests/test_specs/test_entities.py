"""Tests for all MIAPPE v1.1 entity specifications."""

import pytest

from miappe_api.models import get_model
from miappe_api.specs.loader import SpecLoader

MIAPPE_V11_ENTITIES = [
    "investigation",
    "study",
    "person",
    "biological_material",
    "material_source",
    "sample",
    "observation_unit",
    "observed_variable",
    "factor",
    "factor_value",
    "event",
    "environment",
    "data_file",
    "location",
]


class TestAllEntitySpecs:
    """Tests to verify all entity specs are valid and loadable."""

    @pytest.fixture
    def loader(self) -> SpecLoader:
        """Create a spec loader instance."""
        return SpecLoader()

    def test_all_entities_exist(self, loader: SpecLoader) -> None:
        """All 14 MIAPPE entities have specs."""
        entities = loader.list_entities(version="1.1")
        assert len(entities) >= 14, f"Expected at least 14 entities, got {len(entities)}"

        # Check case-insensitively since profile may use PascalCase
        entities_lower = [e.lower() for e in entities]
        for entity in MIAPPE_V11_ENTITIES:
            entity_normalized = entity.replace("_", "").lower()
            assert any(
                e.replace("_", "") == entity_normalized for e in entities_lower
            ), f"Entity {entity} not found"

    @pytest.mark.parametrize("entity", MIAPPE_V11_ENTITIES)
    def test_entity_spec_loads(self, loader: SpecLoader, entity: str) -> None:
        """Each entity spec can be loaded."""
        spec = loader.load_entity(entity, version="1.1")
        assert spec.name is not None
        assert spec.version == "1.1"

    @pytest.mark.parametrize("entity", MIAPPE_V11_ENTITIES)
    def test_entity_has_required_fields(self, loader: SpecLoader, entity: str) -> None:
        """Each entity has at least one required field (unique_id or similar)."""
        spec = loader.load_entity(entity, version="1.1")
        required_fields = spec.get_required_fields()

        # Most entities should have at least one required field
        # (unique_id or name-like field)
        assert len(required_fields) >= 1, f"{entity} has no required fields"

    @pytest.mark.parametrize("entity", MIAPPE_V11_ENTITIES)
    def test_entity_model_can_be_created(self, entity: str) -> None:
        """Each entity spec can generate a Pydantic model."""
        Model = get_model(entity, version="1.1")
        assert Model is not None
        assert hasattr(Model, "model_fields")


class TestEntityRelationships:
    """Tests for entity relationship consistency."""

    def test_investigation_references_study(self) -> None:
        """Investigation spec references Study in studies field."""
        loader = SpecLoader()
        spec = loader.load_entity("investigation", version="1.1")

        studies_field = next((f for f in spec.fields if f.name == "studies"), None)
        assert studies_field is not None
        assert studies_field.items == "Study"

    def test_study_references_all_related_entities(self) -> None:
        """Study spec references all expected related entities."""
        loader = SpecLoader()
        spec = loader.load_entity("study", version="1.1")

        # Check that study references the expected entities
        field_items = {f.name: f.items for f in spec.fields if f.items is not None}

        expected_references = {
            "biological_materials": "BiologicalMaterial",
            "observation_units": "ObservationUnit",
            "observed_variables": "ObservedVariable",
            "factors": "Factor",
            "events": "Event",
            "environments": "Environment",
            "data_files": "DataFile",
            "persons": "Person",
        }

        for field_name, expected_item in expected_references.items():
            assert field_name in field_items, f"Study missing {field_name} field"
            assert field_items[field_name] == expected_item

    def test_observation_unit_references_factor_value(self) -> None:
        """ObservationUnit references FactorValue."""
        loader = SpecLoader()
        spec = loader.load_entity("observation_unit", version="1.1")

        fv_field = next((f for f in spec.fields if f.name == "factor_values"), None)
        assert fv_field is not None
        assert fv_field.items == "FactorValue"

    def test_sample_references_observation_unit(self) -> None:
        """Sample has reference to ObservationUnit."""
        loader = SpecLoader()
        spec = loader.load_entity("sample", version="1.1")

        ou_field = next((f for f in spec.fields if f.name == "observation_unit_id"), None)
        assert ou_field is not None


class TestISAMaterialFlowChain:
    """Tests for ISA material derivation chain: Source -> Sample -> Extract -> LabeledExtract -> DataFile."""

    @pytest.fixture
    def isa_loader(self) -> SpecLoader:
        """Create ISA spec loader."""
        return SpecLoader(profile="isa")

    def test_sample_derives_from_source(self, isa_loader: SpecLoader) -> None:
        """Sample.derives_from references Source."""
        spec = isa_loader.load_entity("Sample", version="1.0")

        derives_from = next((f for f in spec.fields if f.name == "derives_from"), None)
        assert derives_from is not None
        assert derives_from.items == "Source"

    def test_extract_derives_from_sample(self, isa_loader: SpecLoader) -> None:
        """Extract.derives_from references Sample."""
        spec = isa_loader.load_entity("Extract", version="1.0")

        derives_from = next((f for f in spec.fields if f.name == "derives_from"), None)
        assert derives_from is not None
        assert derives_from.items == "Sample"

    def test_labeled_extract_derives_from_extract(self, isa_loader: SpecLoader) -> None:
        """LabeledExtract.derives_from references Extract."""
        spec = isa_loader.load_entity("LabeledExtract", version="1.0")

        derives_from = next((f for f in spec.fields if f.name == "derives_from"), None)
        assert derives_from is not None
        assert derives_from.items == "Extract"

    def test_datafile_derives_from_labeled_extract(self, isa_loader: SpecLoader) -> None:
        """DataFile.derives_from references LabeledExtract."""
        spec = isa_loader.load_entity("DataFile", version="1.0")

        derives_from = next((f for f in spec.fields if f.name == "derives_from"), None)
        assert derives_from is not None, "DataFile must have derives_from field"
        assert derives_from.items == "LabeledExtract"

    def test_complete_material_flow_chain(self, isa_loader: SpecLoader) -> None:
        """Verify complete ISA material flow chain is properly connected."""
        expected_chain = [
            ("Source", None),  # Source has no derives_from
            ("Sample", "Source"),
            ("Extract", "Sample"),
            ("LabeledExtract", "Extract"),
            ("DataFile", "LabeledExtract"),
        ]

        for entity_name, expected_derives_from in expected_chain:
            spec = isa_loader.load_entity(entity_name, version="1.0")
            derives_from = next((f for f in spec.fields if f.name == "derives_from"), None)

            if expected_derives_from is None:
                # Source should not have derives_from
                assert derives_from is None, f"{entity_name} should not have derives_from"
            else:
                assert derives_from is not None, f"{entity_name} missing derives_from"
                assert (
                    derives_from.items == expected_derives_from
                ), f"{entity_name}.derives_from should reference {expected_derives_from}"


class TestMIAPPEEntityReferences:
    """Tests for MIAPPE entity reference fields (Location, MaterialSource)."""

    @pytest.fixture
    def miappe_loader(self) -> SpecLoader:
        """Create MIAPPE spec loader."""
        return SpecLoader(profile="miappe")

    def test_study_geographic_location_references_location(self, miappe_loader: SpecLoader) -> None:
        """Study.geographic_location references Location entity."""
        from miappe_api.specs.schema import FieldType

        spec = miappe_loader.load_entity("Study", version="1.1")

        geo_field = next((f for f in spec.fields if f.name == "geographic_location"), None)
        assert geo_field is not None, "Study must have geographic_location field"
        assert (
            geo_field.type == FieldType.ENTITY
        ), "Study.geographic_location should be entity type, not string"
        assert geo_field.items == "Location"

    def test_biological_material_source_references_material_source(
        self, miappe_loader: SpecLoader
    ) -> None:
        """BiologicalMaterial.material_source references MaterialSource entity."""
        from miappe_api.specs.schema import FieldType

        spec = miappe_loader.load_entity("BiologicalMaterial", version="1.1")

        source_field = next((f for f in spec.fields if f.name == "material_source"), None)
        assert source_field is not None, "BiologicalMaterial must have material_source"
        assert (
            source_field.type == FieldType.ENTITY
        ), "BiologicalMaterial.material_source should be entity type, not string"
        assert source_field.items == "MaterialSource"

    def test_location_entity_exists_and_has_required_fields(
        self, miappe_loader: SpecLoader
    ) -> None:
        """Location entity exists and has expected fields."""
        spec = miappe_loader.load_entity("Location", version="1.1")

        assert spec is not None
        field_names = [f.name for f in spec.fields]
        assert "unique_id" in field_names
        assert "name" in field_names
        assert "latitude" in field_names
        assert "longitude" in field_names

    def test_material_source_entity_exists_and_has_required_fields(
        self, miappe_loader: SpecLoader
    ) -> None:
        """MaterialSource entity exists and has expected fields."""
        spec = miappe_loader.load_entity("MaterialSource", version="1.1")

        assert spec is not None
        field_names = [f.name for f in spec.fields]
        assert "unique_id" in field_names
        assert "name" in field_names
        assert "institute_code" in field_names
