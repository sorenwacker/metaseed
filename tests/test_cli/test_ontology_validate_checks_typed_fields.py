"""`metaseed ontology validate` checks ontology_term fields and fails on a wrong term.

It chose fields by name ("ontology" or "_term" in it), which skipped every
MIAPPE ontology field (all named *_accession_number), and it always exited 0,
so a script could not detect an unresolved term.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from metaseed.cli import app
from metaseed.cli.output import ExitCode
from metaseed.repositories.dataset_repository import DatasetData
from metaseed.repositories.filesystem_dataset import FilesystemDatasetRepository
from metaseed.services.term_check import TermSourceUnavailableError
from metaseed.services.terms import TermRouter, _router_var


class _CarriesTo:
    """Carries the TO ontology and none of the terms asked about."""

    def get_term_sync(self, term_id):
        return None

    def has_ontology_sync(self, ontology_id):
        return ontology_id.lower() == "to"


class _Down:
    def get_term_sync(self, term_id):
        raise TermSourceUnavailableError("term endpoint unreachable")

    def has_ontology_sync(self, ontology_id):
        raise TermSourceUnavailableError("term endpoint unreachable")


@pytest.fixture
def dataset_with_trait():
    FilesystemDatasetRepository().save(
        "test-with-trait",
        DatasetData(
            name="test-with-trait",
            profile="miappe",
            version="1.2",
            entities=[
                {
                    "_type": "ObservedVariable",
                    "unique_id": "VAR-1",
                    "name": "plant height",
                    "trait_accession_number": "TO:9999999",
                }
            ],
        ),
    )
    yield "test-with-trait"
    _router_var.set(None)


def _run(name: str) -> tuple[int, dict]:
    result = CliRunner().invoke(app, ["ontology", "validate", name])
    return result.exit_code, json.loads(result.stdout)


def test_a_wrong_term_in_an_ontology_field_fails(dataset_with_trait) -> None:
    _router_var.set(TermRouter(sources=[_CarriesTo()]))

    code, report = _run(dataset_with_trait)

    assert [(t["field"], t["term"]) for t in report["terms"]] == [
        ("trait_accession_number", "TO:9999999")
    ]
    assert report["terms"][0]["outcome"] != "not_checked"
    assert code == ExitCode.VALIDATION_ERROR


def test_an_outage_is_not_checked_and_does_not_fail(dataset_with_trait) -> None:
    _router_var.set(TermRouter(sources=[_Down()]))

    code, report = _run(dataset_with_trait)

    assert [t["outcome"] for t in report["terms"]] == ["not_checked"]
    assert code == 0
