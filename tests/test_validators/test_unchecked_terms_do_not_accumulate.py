"""Each validation run reports only its own not-checked ontology terms.

_unchecked_terms was filled during a run and never reset, so a validator
reused for a second file reported the first file's unverified terms again.
"""

from __future__ import annotations

import json

from metaseed.services.term_check import TermSourceUnavailableError
from metaseed.services.terms import TermRouter
from metaseed.validators.dataset import DatasetValidator


class _Down:
    def get_term_sync(self, term_id):
        raise TermSourceUnavailableError("term endpoint unreachable")

    def has_ontology_sync(self, ontology_id):
        raise TermSourceUnavailableError("term endpoint unreachable")


def _not_checked(result) -> list[str]:
    return [w.field for w in result.warnings if w.rule == "ontology_term_not_checked"]


def test_a_second_file_does_not_repeat_the_first_files_unchecked_terms(
    tmp_path,
) -> None:
    path = tmp_path / "variable.json"
    path.write_text(
        json.dumps(
            {
                "_type": "ObservedVariable",
                "unique_id": "VAR-1",
                "name": "plant height",
                "trait_accession_number": "TO:0000207",
            }
        )
    )
    validator = DatasetValidator(
        "miappe", "1.2", term_source=TermRouter(sources=[_Down()])
    )

    first = validator.validate_file(path)
    second = validator.validate_file(path)

    assert _not_checked(first) == ["trait_accession_number"]
    assert _not_checked(second) == ["trait_accession_number"]
