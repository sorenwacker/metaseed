"""Tests for EntityStore load resilience in metaseed.facade.store."""

import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from metaseed.facade import ProfileFacade
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


def test_entities_sharing_identifier_are_not_overwritten() -> None:
    """Two entities with the same identifier value both survive the load.

    The node id is derived from the identifier; without a uniqueness guard the
    second entity would overwrite the first in the store and silently vanish.
    """

    def instance_creator(entity_type: str, data: dict) -> BaseModel:
        return _FakeInstance(name=data["name"])

    store = _build_store(instance_creator)

    entities = [
        {"_type": "Thing", "name": "John Smith"},
        {"_type": "Thing", "name": "John Smith"},
        {"_type": "Thing", "name": "Jane Doe"},
    ]

    loaded = store.load_from_dict(entities)

    assert loaded == 3
    assert len(store._instances) == 3
    names = sorted(node.instance.name for node in store._instances.values())
    assert names == ["Jane Doe", "John Smith", "John Smith"]


def test_persisted_node_id_is_restored_verbatim() -> None:
    """A stored ``_node_id`` becomes the node id verbatim on load."""

    def instance_creator(entity_type: str, data: dict) -> BaseModel:
        return _FakeInstance(name=data["name"])

    store = _build_store(instance_creator)
    store.load_from_dict([{"_type": "Thing", "_node_id": "fixed-1", "name": "alpha"}])

    assert list(store._instances.keys()) == ["fixed-1"]


def test_node_ids_are_stable_across_reloads_without_identifier() -> None:
    """Serialized entities keep their node ids when reloaded repeatedly.

    The graph endpoint reloads the dataset from disk on every poll. An entity
    without an identifier value must keep the same node id across reloads;
    otherwise the graph treats it as removed and re-added on every tick. The id
    persisted by ``to_dict`` is what makes the reload deterministic.
    """

    def instance_creator(entity_type: str, data: dict) -> BaseModel:
        return _FakeInstance(name=data["name"])

    # No identifier field -> ids cannot be derived from the data and must come
    # from the persisted ``_node_id`` instead of being generated afresh.
    helper = _FakeHelper(identifier_field=None, fields=["name"])

    def make_store() -> EntityStore:
        return EntityStore(
            helper_getter=lambda _type: helper,
            instance_creator=instance_creator,
        )

    first = make_store()
    first.load_from_dict(
        [{"_type": "Thing", "name": "alpha"}, {"_type": "Thing", "name": "beta"}]
    )

    # to_dict() is what the dataset file stores; subsequent polls reload it.
    serialized = first.to_dict()
    ids_by_name = {n.instance.name: nid for nid, n in first._instances.items()}

    for _ in range(3):
        reloaded = make_store()
        reloaded.load_from_dict(serialized)
        reloaded_ids = {n.instance.name: nid for nid, n in reloaded._instances.items()}
        assert reloaded_ids == ids_by_name


def _walk_types(nodes: list, out: list[str]) -> list[str]:
    for node in nodes:
        out.append(node.entity_type)
        _walk_types(node.children, out)
    return out


def test_incomplete_draft_survives_reload() -> None:
    """Drafts must not be dropped by the read path.

    The UI persists incomplete entities on purpose (a root can be saved before
    its required children exist). Validating on load discarded exactly those
    entities with only a log warning, so a saved draft vanished the moment any
    route reloaded the dataset from disk.
    """
    facade = ProfileFacade("miappe", "1.2")
    root = facade.add_entity(
        "Investigation", {"unique_id": "INV-1", "title": "root"}, skip_validation=True
    )
    # Draft Study: missing the required investigation_id and title.
    facade.add_entity(
        "Study", {"unique_id": "STU-1"}, parent_id=root.id, skip_validation=True
    )

    serialized = facade.to_dict()
    assert len(serialized) == 2

    reloaded = ProfileFacade("miappe", "1.2")
    reloaded.load_from_dict(serialized)

    types = _walk_types(reloaded.get_roots(), [])
    assert "Study" in types, f"draft dropped on reload; got {types}"
    assert len(types) == 2


def test_reloaded_draft_is_still_reported_invalid() -> None:
    """Lenient loading must not hide incompleteness -- validate() still flags it."""
    from metaseed import MetaseedClient

    client = MetaseedClient("miappe", "1.2")
    root = client.create_entity(
        "Investigation", {"unique_id": "INV-1", "title": "root"}, skip_validation=True
    )
    client.create_entity(
        "Study", {"unique_id": "STU-1"}, parent_id=root.id, skip_validation=True
    )

    reloaded = MetaseedClient("miappe", "1.2")
    reloaded.load(client.serialize())

    assert reloaded.validate().valid is False


def test_hierarchy_survives_reload_without_a_unique_id_parent() -> None:
    """Structure must persist for profiles not keyed on unique_id/alias.

    ``_parent_unique_id`` is derived from the parent's identifier *value*, so it
    was derived from a hardcoded unique_id/alias lookup, so it was empty for the
    seven profiles keyed on anything else (pride/isa/seek/dissco/metabolights/
    darwin-core/miappe-htp) and their whole hierarchy flattened on reload --
    every child came back as a root. The parent's declared identifier field is
    consulted instead.
    """
    facade = ProfileFacade("pride", "1.0")
    root = facade.add_entity(
        "Dataset",
        {
            "identifier": "PXD000001",
            "title": "A proteomics dataset",
            "description": "A longer description of the dataset contents, well over any minimum length constraint.",
            "sample_processing_protocol": "Samples were processed according to the standard protocol described at length here.",
            "data_processing_protocol": "Data were processed according to the standard protocol described at length here.",
            "submission_type": "COMPLETE",
            "keywords": ["k"],
        },
        skip_validation=True,
    )
    facade.add_entity(
        "Sample",
        {"name": "S1", "species": "Homo sapiens", "ncbi_taxonomy_id": "9606"},
        parent_id=root.id,
        skip_validation=True,
    )

    serialized = facade.to_dict()
    child = next(e for e in serialized if e["_type"] == "Sample")
    assert child.get("_parent_unique_id") == "PXD000001", (
        f"child must reference its parent by identifier value, got {child}"
    )

    reloaded = ProfileFacade("pride", "1.0")
    reloaded.load_from_dict(serialized)

    roots = reloaded.get_roots()
    assert [r.entity_type for r in roots] == ["Dataset"]
    assert [c.entity_type for c in roots[0].children] == ["Sample"]
