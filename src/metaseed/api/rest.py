"""REST API endpoints for metaseed.

This module provides FastAPI endpoints for validating and accessing
metadata schemas via HTTP.
"""

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from metaseed.models import get_model
from metaseed.specs.loader import SpecLoader, SpecLoadError
from metaseed.validators import validate as validate_data

try:
    from metaseed._version import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

app = FastAPI(
    title="MIAPPE-API",
    description="Schema-driven API for MIAPPE-compliant phenotyping metadata",
    version=__version__,
)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str


class VersionsResponse(BaseModel):
    """Available versions response."""

    versions: list[str]


class EntitiesResponse(BaseModel):
    """Available entities response."""

    version: str
    entities: list[str]


class ValidationRequest(BaseModel):
    """Validation request body."""

    entity: str
    version: str = "1.2"
    data: dict[str, Any]


class ValidationErrorItem(BaseModel):
    """Single validation error."""

    field: str
    message: str
    rule: str


class ValidationResponse(BaseModel):
    """Validation response."""

    valid: bool
    errors: list[ValidationErrorItem]


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Health check endpoint.

    Returns:
        Health status.
    """
    return HealthResponse(status="ok")


@app.get("/schemas", response_model=VersionsResponse)
def list_versions() -> VersionsResponse:
    """List available MIAPPE schema versions.

    Returns:
        List of available versions.
    """
    loader = SpecLoader()
    versions = loader.list_versions()
    return VersionsResponse(versions=versions)


@app.get("/schemas/{version}", response_model=EntitiesResponse)
def list_entities(version: str) -> EntitiesResponse:
    """List available entities for a version.

    Args:
        version: MIAPPE version (e.g., "1.1").

    Returns:
        List of available entities.

    Raises:
        HTTPException: If version not found.
    """
    loader = SpecLoader()
    try:
        entities = loader.list_entities(version)
    except SpecLoadError:
        raise HTTPException(
            status_code=404, detail=f"Version not found: {version}"
        ) from None
    return EntitiesResponse(version=version, entities=entities)


@app.get("/schemas/{version}/{entity}")
def get_entity_schema(version: str, entity: str) -> dict[str, Any]:
    """Get JSON schema for an entity.

    Args:
        version: MIAPPE version.
        entity: Entity name.

    Returns:
        JSON schema for the entity.

    Raises:
        HTTPException: If entity or version not found.
    """
    try:
        Model = get_model(entity, version)
        return Model.model_json_schema()
    except SpecLoadError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@app.post("/validate", response_model=ValidationResponse)
def validate_entity(request: ValidationRequest) -> ValidationResponse:
    """Validate entity data.

    Args:
        request: Validation request with entity type and data.

    Returns:
        Validation result with any errors.

    Raises:
        HTTPException: If entity not found.
    """
    try:
        errors = validate_data(request.data, request.entity, request.version)
    except SpecLoadError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    return ValidationResponse(
        valid=len(errors) == 0,
        errors=[
            ValidationErrorItem(
                field=e.field,
                message=e.message,
                rule=e.rule,
            )
            for e in errors
        ],
    )
