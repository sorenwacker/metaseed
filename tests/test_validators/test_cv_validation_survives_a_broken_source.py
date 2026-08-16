"""A broken vocabulary configuration is not a verdict on the data (260816).

`check_term` resolves `source=None` itself, inside a guard that turns a source
which cannot even be built — a malformed local vocabulary file, say — into
`NOT_CHECKED` rather than an exception, and says why: "a configuration problem,
not a verdict on this value. Crashing here buried the cause deep in a
validator."

`validate_cv_terms` resolved the source first, unguarded, which reinstated
exactly that crash: it is declared to return `list[ValidationError]`, and so
are its callers `pride.validate_cv` and `metabolights.validate_cv`, but a bad
configuration raised straight out of all three.
"""

from __future__ import annotations

from metaseed.validators.cv import validate_cv_terms


def test_a_source_that_cannot_be_built_does_not_raise(monkeypatch) -> None:
    def _explode() -> object:
        raise RuntimeError("vocabulary directory is malformed")

    monkeypatch.setattr("metaseed.services.terms.get_term_source", _explode)

    errors = validate_cv_terms([("sample.organism", "NCBITaxon:9606")])

    assert errors == [], errors


def test_a_supplied_source_is_still_used() -> None:
    class _Absent:
        def get_term_sync(self, term_id: str) -> object | None:
            return None

        def has_ontology_sync(self, ontology_id: str) -> bool | None:
            return True

    errors = validate_cv_terms(
        [("sample.organism", "NCBITaxon:0000")], service=_Absent()
    )

    assert len(errors) == 1
    assert errors[0].rule == "cv_compliance"
