"""A child records the parent field that holds it (ADR 006).

A DCAT catalogue holds Agents in two fields, ``creator`` and ``publisher``. The
field a child belonged to was never stored: every component re-derived it from
the child's type and took the first matching field, so a publisher was loaded,
shown and saved as a second creator, and a loaded example had its ``publisher``
empty.
"""

from __future__ import annotations

import pytest

from metaseed.facade import ProfileFacade
from metaseed.specs.schema import EntityDefSpec, FieldSpec, FieldType, ProfileSpec

CATALOG = "https://example.org/catalog"


def _spec() -> ProfileSpec:
    entities = {
        "Catalog": EntityDefSpec(
            fields=[
                FieldSpec(name="identifier", type=FieldType.STRING, required=True),
                FieldSpec(name="creator", type=FieldType.LIST, items="Agent"),
                FieldSpec(name="publisher", type=FieldType.ENTITY, items="Agent"),
                FieldSpec(name="datasets", type=FieldType.LIST, items="Dataset"),
            ]
        ),
        "Agent": EntityDefSpec(
            fields=[
                FieldSpec(
                    name="email",
                    type=FieldType.STRING,
                    required=True,
                    is_identifier=True,
                ),
            ]
        ),
        "Dataset": EntityDefSpec(
            fields=[FieldSpec(name="identifier", type=FieldType.STRING, required=True)]
        ),
    }
    return ProfileSpec(
        name="test-parent-field",
        version="1.0",
        root_entity="Catalog",
        entities=entities,
    )


def _facade() -> ProfileFacade:
    return ProfileFacade("test-parent-field", "1.0", spec=_spec())


def _field_of(facade: ProfileFacade, email_or_id: str) -> str | None:
    root = facade.get_roots()[0]
    for child in root.children:
        data = child.instance.model_dump()
        if email_or_id in (data.get("email"), data.get("identifier")):
            return child.parent_field
    raise AssertionError(f"{email_or_id} is not a child of the catalogue")


@pytest.fixture
def built() -> ProfileFacade:
    facade = _facade()
    catalog = facade.add_entity("Catalog", {"identifier": CATALOG})
    facade.add_entity(
        "Agent",
        {"email": "creator@example.org"},
        parent_id=catalog.id,
        parent_field="creator",
    )
    facade.add_entity(
        "Agent",
        {"email": "publisher@example.org"},
        parent_id=catalog.id,
        parent_field="publisher",
    )
    facade.add_entity("Dataset", {"identifier": "ds-1"}, parent_id=catalog.id)
    return facade


def test_a_child_records_the_field_it_was_created_for(
    built: ProfileFacade,
) -> None:
    assert _field_of(built, "creator@example.org") == "creator"
    assert _field_of(built, "publisher@example.org") == "publisher"


def test_a_field_is_not_needed_when_the_parent_has_one_for_the_type(
    built: ProfileFacade,
) -> None:
    assert _field_of(built, "ds-1") == "datasets"


def test_an_ambiguous_parent_field_is_rejected_with_the_candidates() -> None:
    facade = _facade()
    catalog = facade.add_entity("Catalog", {"identifier": CATALOG})

    with pytest.raises(ValueError, match=r"creator.*publisher|publisher.*creator"):
        facade.add_entity("Agent", {"email": "who@example.org"}, parent_id=catalog.id)


def test_a_field_that_does_not_hold_the_type_is_rejected() -> None:
    facade = _facade()
    catalog = facade.add_entity("Catalog", {"identifier": CATALOG})

    with pytest.raises(ValueError, match="datasets"):
        facade.add_entity(
            "Agent",
            {"email": "who@example.org"},
            parent_id=catalog.id,
            parent_field="datasets",
        )


def test_the_parent_field_survives_a_save_and_reload(built: ProfileFacade) -> None:
    saved = built.to_dict()
    assert {e.get("_parent_field") for e in saved if e["_type"] == "Agent"} == {
        "creator",
        "publisher",
    }

    reloaded = _facade()
    reloaded.load_from_dict(saved)

    assert _field_of(reloaded, "creator@example.org") == "creator"
    assert _field_of(reloaded, "publisher@example.org") == "publisher"


def test_a_file_without_parent_field_is_read_by_the_field_that_names_the_child() -> (
    None
):
    older = [
        {
            "_type": "Catalog",
            "identifier": CATALOG,
            "creator": ["creator@example.org"],
            "publisher": "publisher@example.org",
        },
        {
            "_type": "Agent",
            "_parent_unique_id": CATALOG,
            "email": "creator@example.org",
        },
        {
            "_type": "Agent",
            "_parent_unique_id": CATALOG,
            "email": "publisher@example.org",
        },
    ]
    facade = _facade()
    facade.load_from_dict(older)

    assert _field_of(facade, "creator@example.org") == "creator"
    assert _field_of(facade, "publisher@example.org") == "publisher"


def test_an_older_child_no_field_names_is_kept_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    older = [
        {"_type": "Catalog", "identifier": CATALOG},
        {"_type": "Agent", "_parent_unique_id": CATALOG, "email": "who@example.org"},
    ]
    facade = _facade()
    with caplog.at_level("WARNING", logger="metaseed.facade.store"):
        facade.load_from_dict(older)

    assert _field_of(facade, "who@example.org") is None
    assert "creator, publisher" in caplog.text


def test_an_embedded_document_keeps_each_child_in_its_field() -> None:
    facade = _facade()
    facade.load_nested(
        {
            "identifier": CATALOG,
            "creator": [{"email": "creator@example.org"}],
            "publisher": {"email": "publisher@example.org"},
            "datasets": [{"identifier": "ds-1"}],
        },
        "Catalog",
    )

    assert _field_of(facade, "creator@example.org") == "creator"
    assert _field_of(facade, "publisher@example.org") == "publisher"
    assert _field_of(facade, "ds-1") == "datasets"
