"""Tests for model registry."""

import pytest
from pydantic import BaseModel

from miappe_api.models.registry import ModelNotFoundError, ModelRegistry


class TestModelRegistry:
    """Tests for ModelRegistry class."""

    @pytest.fixture
    def registry(self) -> ModelRegistry:
        """Create a fresh registry."""
        return ModelRegistry()

    def test_register_and_get_model(self, registry: ModelRegistry) -> None:
        """Register and retrieve a model."""

        class TestModel(BaseModel):
            name: str

        registry.register("Test", "1.0", TestModel)
        retrieved = registry.get("Test", "1.0")

        assert retrieved is TestModel

    def test_get_nonexistent_raises(self, registry: ModelRegistry) -> None:
        """Getting nonexistent model raises error."""
        with pytest.raises(ModelNotFoundError) as exc_info:
            registry.get("NonExistent", "1.0")
        assert "NonExistent" in str(exc_info.value)
        assert "1.0" in str(exc_info.value)

    def test_overwrite_model(self, registry: ModelRegistry) -> None:
        """Can overwrite existing model registration."""

        class TestModel1(BaseModel):
            name: str

        class TestModel2(BaseModel):
            name: str
            count: int

        registry.register("Test", "1.0", TestModel1)
        registry.register("Test", "1.0", TestModel2)

        retrieved = registry.get("Test", "1.0")
        assert retrieved is TestModel2

    def test_list_models(self, registry: ModelRegistry) -> None:
        """List all registered models."""

        class Model1(BaseModel):
            pass

        class Model2(BaseModel):
            pass

        registry.register("Model1", "1.0", Model1)
        registry.register("Model2", "1.0", Model2)
        registry.register("Model1", "1.1", Model1)

        models = registry.list_models()

        assert ("Model1", "1.0") in models
        assert ("Model1", "1.1") in models
        assert ("Model2", "1.0") in models

    def test_list_models_for_version(self, registry: ModelRegistry) -> None:
        """List models for specific version."""

        class Model1(BaseModel):
            pass

        class Model2(BaseModel):
            pass

        registry.register("Model1", "1.0", Model1)
        registry.register("Model2", "1.0", Model2)
        registry.register("Model1", "1.1", Model1)

        models_1_0 = registry.list_models(version="1.0")
        models_1_1 = registry.list_models(version="1.1")

        assert "Model1" in models_1_0
        assert "Model2" in models_1_0
        assert "Model1" in models_1_1
        assert "Model2" not in models_1_1

    def test_has_model(self, registry: ModelRegistry) -> None:
        """Check if model exists."""

        class TestModel(BaseModel):
            pass

        registry.register("Test", "1.0", TestModel)

        assert registry.has("Test", "1.0") is True
        assert registry.has("Test", "1.1") is False
        assert registry.has("Other", "1.0") is False

    def test_clear_registry(self, registry: ModelRegistry) -> None:
        """Clear all registered models."""

        class TestModel(BaseModel):
            pass

        registry.register("Test", "1.0", TestModel)
        registry.clear()

        assert registry.has("Test", "1.0") is False
        assert registry.list_models() == []


class TestGlobalRegistry:
    """Tests for global model registry access."""

    def test_get_model_loads_from_spec(self) -> None:
        """get_model loads model from spec if not in registry."""
        from miappe_api.models import get_model

        # Should load Investigation model from spec
        Investigation = get_model("Investigation", version="1.1")

        assert Investigation.__name__ == "Investigation"

        # Required fields should be present
        field_names = list(Investigation.model_fields.keys())
        assert "unique_id" in field_names
        assert "title" in field_names

    def test_get_model_cached(self) -> None:
        """get_model returns cached model on subsequent calls."""
        from miappe_api.models import get_model

        Model1 = get_model("Investigation", version="1.1")
        Model2 = get_model("Investigation", version="1.1")

        assert Model1 is Model2

    def test_get_model_nonexistent_entity(self) -> None:
        """get_model raises error for nonexistent entity."""
        from miappe_api.models import get_model
        from miappe_api.specs.loader import SpecLoadError

        with pytest.raises(SpecLoadError):
            get_model("NonExistent", version="1.1")

    def test_get_model_camel_case_names(self) -> None:
        """get_model handles CamelCase entity names correctly."""
        from miappe_api.models import get_model

        # Multi-word entity names should work
        BiologicalMaterial = get_model("BiologicalMaterial", version="1.1")
        assert BiologicalMaterial.__name__ == "BiologicalMaterial"
        assert "unique_id" in BiologicalMaterial.model_fields

        ObservedVariable = get_model("ObservedVariable", version="1.1")
        assert ObservedVariable.__name__ == "ObservedVariable"

        FactorValue = get_model("FactorValue", version="1.1")
        assert FactorValue.__name__ == "FactorValue"

        ObservationUnit = get_model("ObservationUnit", version="1.1")
        assert ObservationUnit.__name__ == "ObservationUnit"

        MaterialSource = get_model("MaterialSource", version="1.1")
        assert MaterialSource.__name__ == "MaterialSource"

        DataFile = get_model("DataFile", version="1.1")
        assert DataFile.__name__ == "DataFile"

    def test_get_model_snake_case_names(self) -> None:
        """get_model also handles snake_case entity names."""
        from miappe_api.models import get_model

        # snake_case should also work
        model = get_model("biological_material", version="1.1")
        assert "unique_id" in model.model_fields
