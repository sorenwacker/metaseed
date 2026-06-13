"""Tests for EntityStore load resilience in metaseed.facade.store."""

import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from metaseed.facade.store import EntityStore


class _FakeHelper:
    """Minimal stand-in for EntityHelper used by EntityStore loading."""

    def __init__(self, identifier_field: str, fields: list[str]) -> None:
        self.identifier_field = identifier_field
        self.all_fields = fields
        self.nested_fields: dict[str, str] = {}
        self.reference_fields: dict[str, tuple[str, str]] = {}


class _FakeInstance(BaseModel):
    """Minimal validated model used in place of generated entity models."""

    name: str


def _build_store(
    instance_creator: Any,
) -> EntityStore:
    """Build an EntityStore with a single 'Thing' entity type.

    Args:
        instance_creator: Callback producing model instances or raising.

    Returns:
        Configured EntityStore.
    """
    helper = _FakeHelper(identifier_field="name", fields=["name"])
    return EntityStore(
        helper_getter=lambda _type: helper,
        instance_creator=instance_creator,
    )


class _RecordingHandler(logging.Handler):
    """Captures emitted records directly, independent of propagation settings."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_malformed_entity_skipped_logged_and_rest_load() -> None:
    """A malformed entity is skipped and logged, others still load."""

    def instance_creator(entity_type: str, data: dict) -> BaseModel:
        if data.get("name") == "bad":
            raise ValidationError.from_exception_data("Thing", [])
        return _FakeInstance(name=data["name"])

    store = _build_store(instance_creator)

    entities = [
        {"_type": "Thing", "_node_id": "n1", "name": "good-1"},
        {"_type": "Thing", "_node_id": "n2", "name": "bad"},
        {"_type": "Thing", "_node_id": "n3", "name": "good-2"},
    ]

    # Attach a handler directly to the module logger so capture does not depend
    # on root propagation, which configure_logging disables for "metaseed".
    logger = logging.getLogger("metaseed.facade.store")
    handler = _RecordingHandler()
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    try:
        loaded = store.load_from_dict(entities)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)

    assert loaded == 2
    labels = {node.instance.name for node in store._instances.values()}
    assert labels == {"good-1", "good-2"}

    warnings = [r for r in handler.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "Thing" in message
    assert "n2" in message
