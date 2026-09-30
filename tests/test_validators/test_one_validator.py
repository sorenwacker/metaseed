"""``validate()`` and ``check`` are one validator.

``MetaseedClient.validate()`` ran only the per-entity checks: a reference to a
record that does not exist, or two records sharing an identifier declared
unique, went unreported -- while ``metaseed check`` on the same data reported
both. Every consumer built on ``validate()`` (the CLI's ``dataset validate``,
the hub's MCP and web validation) inherited the gap. These hold the two paths
to the same answer and pin that the dataset-level issues name their node.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

from metaseed import MetaseedClient
from metaseed.validators import DatasetValidator


def _investigation(client: MetaseedClient):
    inv = client.create_entity("Investigation", {"unique_id": "INV-1", "title": "T"})
    study = client.create_entity(
        "Study",
        {"unique_id": "STU-1", "title": "S"},
        parent_id=inv.id,
        skip_validation=True,
    )
    return inv, study


def test_validate_reports_a_reference_to_a_record_that_does_not_exist() -> None:
    client = MetaseedClient("miappe", "1.2")
    _inv, study = _investigation(client)
    unit = client.create_entity(
        "ObservationUnit",
        {"unique_id": "OU-1", "study_id": "STU-9"},
        parent_id=study.id,
        skip_validation=True,
    )

    broken = [i for i in client.validate().issues if i.rule == "reference_integrity"]

    assert [(i.entity_id, i.field) for i in broken] == [(unit.id, "study_id")]
    assert "STU-9" in broken[0].message


def test_a_reference_that_resolves_is_not_reported() -> None:
    client = MetaseedClient("miappe", "1.2")
    _inv, study = _investigation(client)
    client.create_entity(
        "ObservationUnit",
        {"unique_id": "OU-1", "study_id": "STU-1"},
        parent_id=study.id,
        skip_validation=True,
    )

    assert not [i for i in client.validate().issues if i.rule == "reference_integrity"]


def test_validate_reports_two_records_sharing_a_unique_identifier() -> None:
    """MIAPPE declares observation-unit ids unique within their parent."""
    client = MetaseedClient("miappe", "1.2")
    _inv, study = _investigation(client)
    for _ in range(2):
        twin = client.create_entity(
            "ObservationUnit",
            {"unique_id": "OU-1", "study_id": "STU-1"},
            parent_id=study.id,
            skip_validation=True,
        )

    duplicates = [i for i in client.validate().issues if i.rule == "uniqueness"]

    assert [(i.entity_id, i.field) for i in duplicates] == [(twin.id, "unique_id")]


def test_a_client_built_from_a_supplied_spec_checks_references_too() -> None:
    """Nothing is re-resolved by name: the supplied spec is what is enforced."""
    spec = {
        "version": "1.0",
        "name": "reference_probe",
        "root_entity": "Sample",
        "entities": {
            "Sample": {
                "fields": [
                    {"name": "unique_id", "type": "string", "required": True},
                    {"name": "measurements", "type": "list", "items": "Measurement"},
                ]
            },
            "Measurement": {
                "fields": [
                    {"name": "unique_id", "type": "string", "required": True},
                    {
                        "name": "sample_ref",
                        "type": "string",
                        "reference": "Sample.unique_id",
                    },
                ]
            },
        },
    }
    client = MetaseedClient.from_spec(spec)
    sample = client.create_entity("Sample", {"unique_id": "S1"})
    measurement = client.create_entity(
        "Measurement", {"unique_id": "M1", "sample_ref": "S2"}, parent_id=sample.id
    )

    broken = [i for i in client.validate().issues if i.rule == "reference_integrity"]

    assert [(i.entity_id, i.field) for i in broken] == [(measurement.id, "sample_ref")]


def _strip_node_ids(data):
    if isinstance(data, dict):
        return {k: _strip_node_ids(v) for k, v in data.items() if k != "_node_id"}
    if isinstance(data, list):
        return [_strip_node_ids(v) for v in data]
    return data


def test_validate_and_check_report_the_same_issues(tmp_path: Path) -> None:
    """The same records, nested the same way, through both paths.

    Ontology-term checks are ``check``'s alone (they may need a network) and
    are left out of the comparison.
    """
    client = MetaseedClient("miappe", "1.2")
    inv = client.create_entity(
        "Investigation",
        {"unique_id": "INV-1", "title": "T", "submission_date": "15.03.2024"},
        skip_validation=True,
    )
    study = client.create_entity(
        "Study",
        {"unique_id": "STU-1", "title": "S"},
        parent_id=inv.id,
        skip_validation=True,
    )
    for unique_id in ("OU-1", "OU-1"):
        client.create_entity(
            "ObservationUnit",
            {"unique_id": unique_id, "study_id": "STU-1"},
            parent_id=study.id,
            skip_validation=True,
        )
    client.create_entity(
        "ObservationUnit",
        {"unique_id": "OU-1", "study_id": "STU-9"},
        parent_id=study.id,
        skip_validation=True,
    )
    client.create_entity(
        "ObservedVariable",
        {"unique_id": "VAR-1"},
        parent_id=study.id,
        skip_validation=True,
    )

    document = _strip_node_ids(
        copy.deepcopy(client._nested_document(client._facade.get_roots()[0]))
    )
    path = tmp_path / "investigation.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    checked = DatasetValidator("miappe", "1.2").validate_file(path)

    validated = client.validate()

    def rules(items):
        return sorted(i.rule for i in items if not i.rule.startswith("ontology_term"))

    assert rules(validated.issues) == rules(checked.errors)
    assert {
        "constraint",
        "required_fields",
        "reference_integrity",
        "uniqueness",
    } <= set(rules(validated.issues))


def test_per_entity_issues_still_name_their_node() -> None:
    client = MetaseedClient("miappe", "1.2")
    inv, _study = _investigation(client)

    for issue in client.validate().issues:
        assert issue.entity_id is not None, issue
    assert inv.id in {i.entity_id for i in client.validate().issues}
