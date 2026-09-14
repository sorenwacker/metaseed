"""A field holding entities is shown once, as its table (ADR 006).

A required single-entity field (``type: entity``) was listed among the Required
Fields as a "(1 item)" / "(not set)" button, by a template branch separate from
the one list fields use, and again as a table under Related Entities. The
Health-RI Catalog's ``publisher`` and ``contact_point`` appeared twice and never
showed the entity they hold. Six routes split the field lists on their own,
so the rule for which list a field belongs to had six homes.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from metaseed.facade import ProfileFacade
from metaseed.forms import get_field_data
from metaseed.ui.app import create_app
from metaseed.ui.state import AppState

UI_SRC = Path(__file__).resolve().parents[2] / "src" / "metaseed" / "ui"


def _assay(with_type: bool = False) -> tuple[TestClient, str]:
    """A SEEK Assay: ``assay_type`` is a required single-entity field."""
    state = AppState(profile="seek", version="1.0")
    facade = state.get_or_create_facade()
    assay = state.add_node(
        "Assay",
        facade.Assay.create(skip_validation=True, identifier="ASSAY-1", title="A"),
        skip_validation=True,
    )
    if with_type:
        state.add_node(
            "OntologyAnnotation",
            facade.OntologyAnnotation.create(skip_validation=True, term="metabolomics"),
            parent_id=assay.id,
            skip_validation=True,
            parent_field="assay_type",
        )
    return TestClient(create_app(state)), assay.id


def test_the_field_lists_have_one_home() -> None:
    from metaseed.forms import form_field_groups

    groups = form_field_groups(get_field_data(ProfileFacade("seek", "1.0").Assay))

    required = [f["name"] for f in groups["required_fields"]]
    optional = [f["name"] for f in groups["optional_fields"]]
    nested = [f["name"] for f in groups["nested_fields"]]
    assert "assay_type" in nested
    assert "samples" in nested
    assert "assay_type" not in required
    assert "samples" not in optional


def test_no_route_splits_the_field_lists_itself() -> None:
    offenders = [
        str(path.relative_to(UI_SRC))
        for path in sorted(UI_SRC.rglob("*.py"))
        if "filter_fields(" in path.read_text()
    ]
    assert not offenders, (
        f"field lists are split outside metaseed.forms in {offenders}; "
        "use form_field_groups so a field is listed in exactly one section"
    )


def test_a_single_entity_field_is_rendered_once_on_the_edit_form() -> None:
    client, assay_id = _assay()

    html = client.get(f"/form/Assay/{assay_id}").text

    assert html.count('data-testid="inline-table-assay_type"') == 1
    assert 'data-testid="btn-nested-assay-type"' not in html
    assert "(not set)" not in html and "(1 item)" not in html


def test_a_single_entity_field_is_listed_once_on_the_new_form() -> None:
    state = AppState(profile="seek", version="1.0")
    client = TestClient(create_app(state))

    html = client.get("/form/Assay?profile=seek").text

    assert html.count("Create first, then add assay_type") == 1


def test_a_required_table_is_marked_required() -> None:
    client, assay_id = _assay()

    html = client.get(f"/form/Assay/{assay_id}").text

    assert 'data-testid="inline-table-required-assay_type"' in html
    assert 'data-testid="inline-table-required-samples"' not in html


def test_a_single_entity_table_takes_no_second_row() -> None:
    empty_client, empty_id = _assay()
    typed_client, typed_id = _assay(with_type=True)

    empty = empty_client.get(f"/form/Assay/{empty_id}").text
    typed = typed_client.get(f"/form/Assay/{typed_id}").text

    assert 'data-testid="inline-add-row-assay_type"' in empty
    assert "metabolomics" in typed
    assert 'data-testid="inline-add-row-assay_type"' not in typed
    assert 'data-testid="inline-add-row-samples"' in typed


def test_the_add_row_route_refuses_a_second_row_for_a_single_entity() -> None:
    client, assay_id = _assay()
    client.get(f"/form/Assay/{assay_id}")

    first = client.post("/table/Assay/assay_type/row")
    second = client.post("/table/Assay/assay_type/row")
    list_rows = [client.post("/table/Assay/samples/row") for _ in range(2)]

    assert first.status_code == 200
    assert second.status_code == 409
    assert "exactly one" in second.text
    assert [r.status_code for r in list_rows] == [200, 200]
