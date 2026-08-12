"""Two claims that must not be enforced identically.

"This value is wrong" holds now and keeps holding. "This is not finished yet"
is true of every dataset the moment it is created. Enforced the same way, the
second makes a specification unenforceable: a metabolights Study declaring
`min_items: 3` on its design descriptors cannot be saved at all, because no
value the person types clears a rule about a list they have not reached (#246).
Its mirror is #217, absence going unchecked entirely.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from metaseed.validators.base import Kind
from metaseed.validators.dataset import DatasetValidator
from metaseed.validators.rules import ListCardinalityRule, RequiredFieldsRule


class _NoService:
    """A term source that carries nothing and says so.

    Hermetic on purpose: the ontology check reaches the network by default, and
    a test asserting how errors are *classified* must not depend on EBI.
    """

    def get_term_sync(self, term_id: str) -> object | None:
        return None

    def has_ontology_sync(self, ontology_id: str) -> bool | None:
        return False


class TestWhatEachRuleClaims:
    def test_a_missing_required_field_is_unfinished_not_wrong(self) -> None:
        errors = RequiredFieldsRule(fields=["title"]).validate({})

        assert [e.kind for e in errors] == [Kind.COMPLETENESS]
        assert not errors[0].blocks

    def test_too_few_items_is_unfinished(self) -> None:
        errors = ListCardinalityRule(field="descriptors", min_items=3).validate(
            {"descriptors": []}
        )

        assert [e.kind for e in errors] == [Kind.COMPLETENESS]

    def test_too_many_items_is_wrong(self) -> None:
        """Not the mirror image: a list over its maximum is wrong now, and
        nothing the person does later makes it right except removing one."""
        errors = ListCardinalityRule(field="descriptors", max_items=1).validate(
            {"descriptors": ["a", "b"]}
        )

        assert [e.kind for e in errors] == [Kind.VALUE]
        assert errors[0].blocks

    def test_an_unclassified_rule_is_treated_as_a_value_error(self) -> None:
        """The stricter reading by default: a rule nobody has classified must
        not be quietly downgraded to advisory."""
        from metaseed.validators.base import ValidationError

        assert ValidationError(field="f", message="m", rule="r").blocks


class TestSeparatingThemOnADataset:
    def _result(self, tmp_path):
        path = tmp_path / "dataset.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "unique_id": "INV-1",
                    # title is required and absent: unfinished.
                    "studies": [
                        {
                            "unique_id": "STU-1",
                            "investigation_id": "INV-1",
                            "title": "S",
                            "observed_variables": [
                                {
                                    "unique_id": "VAR-1",
                                    "study_id": "STU-1",
                                    "name": "height",
                                    # a phenotype term in a field that takes a
                                    # unit: wrong, and stays wrong.
                                    "scale_accession_number": "PATO:0000001",
                                }
                            ],
                        }
                    ],
                }
            )
        )
        return DatasetValidator("miappe", "1.1", _NoService()).validate_file(path)

    def test_the_two_are_reported_apart(self, tmp_path) -> None:
        result = self._result(tmp_path)

        assert any(e.rule == "ontology_term" for e in result.wrong_values)
        assert any(e.rule == "required_fields" for e in result.unfinished)

    def test_every_error_lands_in_exactly_one_of_them(self, tmp_path) -> None:
        result = self._result(tmp_path)

        assert len(result.wrong_values) + len(result.unfinished) == len(result.errors)

    def test_is_valid_still_counts_both(self, tmp_path) -> None:
        """Unchanged on purpose: reclassifying rules must not silently turn
        invalid datasets into valid ones."""
        result = self._result(tmp_path)

        assert not result.is_valid


def test_the_shipped_examples_are_finished_but_may_be_incomplete() -> None:
    """What the distinction is worth: measuring it on real data.

    Reported per example so a change in either number is visible rather than
    averaged away.
    """
    examples = sorted(Path("src/metaseed/examples").glob("*/*/*.yaml"))
    assert examples, "no examples found"

    for path in examples:
        profile, version = path.parent.parent.name, path.parent.name
        result = DatasetValidator(profile, version, _NoService()).validate_file(path)
        assert len(result.wrong_values) + len(result.unfinished) == len(
            result.errors
        ), f"{profile}/{version}: an error was neither wrong nor unfinished"
