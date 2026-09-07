"""An incomplete entity still holds its declared types.

The loader tolerates an incomplete entity on purpose: the UI persists a draft
before its required children or fields exist, and dropping those on read lost
user data. That tolerance is implemented by retrying construction with
validation skipped -- which also skipped coercion, so every field that *was*
present kept whatever type the serialized form used. A date read from YAML or
from a workbook cell stayed a string, in a field the profile declares a date.

Nothing failed, because pydantic serializes the string anyway and only warns,
which is why this survived. It surfaces at export, where a string in a date
field fails the receiving schema.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from metaseed.facade import ProfileFacade


@pytest.fixture
def facade() -> ProfileFacade:
    return ProfileFacade("ena", "1.0")


def _run_nodes(facade: ProfileFacade) -> list[Any]:
    return [
        node for node in facade._store._instances.values() if node.entity_type == "Run"
    ]


class TestADraftKeepsItsDeclaredTypes:
    """A missing required field must not cost the present fields their types."""

    def test_a_complete_run_reads_its_date_as_a_date(
        self, facade: ProfileFacade
    ) -> None:
        """The baseline: full validation coerces, and always did."""
        instance = facade.Run.create(
            alias="ERR-1", experiment_ref="ERX-1", run_date="2024-04-01"
        )

        assert instance.run_date == dt.date(2024, 4, 1)

    def test_a_nested_document_reads_its_date_as_a_date(
        self, facade: ProfileFacade
    ) -> None:
        """The path every shipped example and every exported YAML takes."""
        facade.load_nested(
            {
                "alias": "STUDY-1",
                "title": "T",
                "experiments": [
                    {
                        "alias": "ERX-1",
                        "runs": [{"alias": "ERR-1", "run_date": "2024-04-01"}],
                    }
                ],
            },
            "Study",
        )

        nodes = _run_nodes(facade)
        assert len(nodes) == 1
        assert nodes[0].instance.run_date == dt.date(2024, 4, 1)

    def test_a_nested_document_keeps_its_numbers_numeric(
        self, facade: ProfileFacade
    ) -> None:
        """Every declared type, not only dates: a workbook writes all of them as text."""
        facade.load_nested(
            {
                "alias": "STUDY-1",
                "title": "T",
                "samples": [{"alias": "SAMP-1", "taxon_id": "3702"}],
            },
            "Study",
        )

        node = next(
            n for n in facade._store._instances.values() if n.entity_type == "Sample"
        )
        assert node.instance.taxon_id == 3702

    def test_an_unparseable_value_is_kept_rather_than_dropped(
        self, facade: ProfileFacade
    ) -> None:
        """Coercion must not delete what a person typed.

        `n/a` in a taxon_id is not an integer. Coercing it to None would drop
        their input to satisfy a schema, and refusing the entity would lose the
        rest of the record with it. The value stays as written and
        ``validate()`` reports the mismatch, which leaves something to correct.
        """
        facade.load_nested(
            {
                "alias": "STUDY-1",
                "title": "T",
                "samples": [{"alias": "SAMP-1", "taxon_id": "n/a"}],
            },
            "Study",
        )

        node = next(
            n for n in facade._store._instances.values() if n.entity_type == "Sample"
        )
        assert node.instance.taxon_id == "n/a"
