"""A catalogue card is never named after the profile.

`build_card` fell back to the profile name, and `metaseed dcat show` passed no
identifier, so every unidentified dataset of a profile became
`urn:metaseed:isa`, one IRI shared by unrelated datasets.
"""

from __future__ import annotations

from typer.testing import CliRunner

from metaseed import MetaseedClient
from metaseed.cli import app
from metaseed.dcat.export import build_card
from metaseed.repositories.dataset_repository import DatasetData
from metaseed.repositories.filesystem_dataset import FilesystemDatasetRepository

UNIDENTIFIED = [{"_type": "Investigation", "title": "An investigation"}]


def test_an_unidentified_card_has_no_identifier() -> None:
    client = MetaseedClient("isa", "1.0")
    client.create_entity(
        "Investigation", {"title": "An investigation"}, skip_validation=True
    )

    card = build_card(client)

    assert card is not None
    assert card.identifier is None


def test_the_cli_names_the_card_after_the_dataset() -> None:
    FilesystemDatasetRepository().save(
        "test-dcat-card",
        DatasetData(
            name="test-dcat-card", profile="isa", version="1.0", entities=UNIDENTIFIED
        ),
    )

    result = CliRunner().invoke(app, ["dcat", "show", "test-dcat-card"])

    assert result.exit_code == 0, result.output
    assert "urn:metaseed:test-dcat-card" in result.stdout
    assert "urn:metaseed:isa" not in result.stdout
