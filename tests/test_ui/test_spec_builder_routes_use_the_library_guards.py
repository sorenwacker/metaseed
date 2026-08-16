"""The routes must go through the guards the library already states (260816).

`SpecBuilder.set_root_entity` exists to refuse a root that is not a defined
entity, and `SpecBuilder.add_rule` to refuse a duplicate rule name. Two routes
assigned and appended directly instead, so the UI produced drafts the library
would have rejected — a profile whose root points at nothing, and two rules of
the same name.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from metaseed.ui.app import create_app


def _client() -> TestClient:
    client = TestClient(create_app())
    client.get("/spec-builder/new")
    client.post("/spec-builder/entity", data={"name": "Thing"})
    return client


def _spec(client: TestClient):
    return client.app.state.ui_state.spec_builder.spec  # type: ignore[attr-defined]


def test_a_root_entity_that_does_not_exist_is_refused() -> None:
    client = _client()

    client.post(
        "/spec-builder/profile-metadata",
        data={
            "name": "guard-probe",
            "version": "1.0",
            "description": "",
            "root_entity": "NoSuchEntity",
        },
    )

    assert _spec(client).root_entity != "NoSuchEntity", (
        "the profile's root now points at an entity that does not exist"
    )


def test_a_duplicate_rule_name_is_refused() -> None:
    client = _client()
    client.post("/spec-builder/validation-rule", data={"name": "only_once"})

    client.post("/spec-builder/validation-rule", data={"name": "only_once"})

    names = [r.name for r in _spec(client).validation_rules]
    assert len(names) == len(set(names)), names
