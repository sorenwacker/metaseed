"""Every accession in a shipped example must be a real term.

Nothing checked this, which is how the MIAPPE example came to carry
`AGRO:00000007` labelled "Sowing" — a real term meaning *desuckering* — and
`AGRO:00000012`, which does not exist at all, while the ISA example carries
five EFO accessions that resolve in no form. Identifiers that look real and are
not survive every check that only asks whether a value is filled in.

Marked ``network`` because answering the question means asking an ontology
service. That makes it a release gate rather than a per-push one: the shipped
examples change rarely, and CI minutes are a budget.

Three outcomes, not two, exactly as the term check has: a value that could not
be checked — because no configured source carries its ontology, CO_321 and
CO_715 among them — is reported here rather than counted as a pass, so the
unverifiable surface stays visible instead of being quietly trusted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from metaseed.validators.dataset import DatasetValidator

EXAMPLES = sorted(Path("src/metaseed/examples").glob("*/*/*.yaml"))


def _cases() -> list[tuple[str, str, Path]]:
    return [(p.parent.parent.name, p.parent.name, p) for p in EXAMPLES]


@pytest.mark.network
@pytest.mark.parametrize(
    ("profile", "version", "path"),
    _cases(),
    ids=[f"{p}-{v}" for p, v, _ in _cases()],
)
def test_every_accession_in_an_example_resolves(
    profile: str, version: str, path: Path
) -> None:
    result = DatasetValidator(profile, version).validate_file(path)

    unresolved = [e for e in result.errors if e.rule == "ontology_term"]

    assert not unresolved, "\n".join(f"{e.field}: {e.message}" for e in unresolved)
