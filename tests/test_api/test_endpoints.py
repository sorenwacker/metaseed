"""Tests for REST API endpoints."""

from fastapi.testclient import TestClient

from miappe_api.api import app

client = TestClient(app)


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_returns_ok(self) -> None:
        """Health endpoint returns OK status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestSchemasEndpoint:
    """Tests for schemas endpoints."""

    def test_list_versions(self) -> None:
        """List available schema versions."""
        response = client.get("/schemas")
        assert response.status_code == 200
        data = response.json()
        assert "versions" in data
        assert "1.1" in data["versions"]

    def test_list_entities_for_version(self) -> None:
        """List entities for a specific version."""
        response = client.get("/schemas/1.1")
        assert response.status_code == 200
        data = response.json()
        assert "entities" in data
        # Case-insensitive check since profile may use PascalCase
        entities_lower = [e.lower() for e in data["entities"]]
        assert "investigation" in entities_lower
        assert "study" in entities_lower

    def test_get_entity_schema(self) -> None:
        """Get JSON schema for an entity."""
        response = client.get("/schemas/1.1/investigation")
        assert response.status_code == 200
        data = response.json()
        assert "properties" in data
        assert "unique_id" in data["properties"]
        assert "title" in data["properties"]

    def test_get_nonexistent_entity(self) -> None:
        """Get schema for nonexistent entity returns 404."""
        response = client.get("/schemas/1.1/nonexistent")
        assert response.status_code == 404

    def test_get_nonexistent_version(self) -> None:
        """Get schema for nonexistent version returns 404."""
        response = client.get("/schemas/99.99")
        assert response.status_code == 404


class TestValidateEndpoint:
    """Tests for validate endpoint."""

    def test_validate_valid_data(self) -> None:
        """Validate valid data returns success."""
        data = {
            "entity": "investigation",
            "version": "1.1",
            "data": {
                "unique_id": "INV001",
                "title": "Test Investigation",
                "contacts": [{"name": "Test Contact"}],
                "studies": [{"unique_id": "STU001", "title": "Test Study"}],
            },
        }
        response = client.post("/validate", json=data)
        assert response.status_code == 200
        result = response.json()
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_validate_missing_required_field(self) -> None:
        """Validate data missing required field returns errors."""
        data = {
            "entity": "investigation",
            "version": "1.1",
            "data": {
                "unique_id": "INV001",
                # missing title
            },
        }
        response = client.post("/validate", json=data)
        assert response.status_code == 200
        result = response.json()
        assert result["valid"] is False
        assert len(result["errors"]) > 0
        assert any("title" in e["field"] for e in result["errors"])

    def test_validate_invalid_entity(self) -> None:
        """Validate with invalid entity returns error."""
        data = {
            "entity": "nonexistent",
            "version": "1.1",
            "data": {"unique_id": "TEST001"},
        }
        response = client.post("/validate", json=data)
        assert response.status_code == 404
