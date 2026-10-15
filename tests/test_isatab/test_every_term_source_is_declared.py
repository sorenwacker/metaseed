"""Every Term Source REF an archive writes is declared in its investigation file.

The ONTOLOGY SOURCE REFERENCE section was built by re-scanning a few entity
types, separately from the code that writes each Term Source REF. A qualifier
embedded in its Sample's ``characteristics`` list was written with its source
and never declared, which the section exists to prevent. The section is now
built from the references the archive actually writes.
"""

from __future__ import annotations

from metaseed import MetaseedClient
from metaseed.isatab import to_isatab


def _declared(investigation_file: str) -> set[str]:
    for line in investigation_file.splitlines():
        label, *cells = line.split("\t")
        if label == "Term Source Name":
            return {c for c in cells if c}
    return set()


def _referenced(documents: dict[str, str]) -> set[str]:
    found: set[str] = set()
    for name, text in documents.items():
        lines = text.splitlines()
        if name.startswith("i_"):
            for line in lines:
                label, *cells = line.split("\t")
                if label.endswith("Term Source REF"):
                    found.update(c for c in cells if c)
        elif lines:
            columns = [
                i for i, h in enumerate(lines[0].split("\t")) if h == "Term Source REF"
            ]
            for row in lines[1:]:
                cells = row.split("\t")
                found.update(cells[i] for i in columns if i < len(cells) and cells[i])
    return found


def _check(client: MetaseedClient) -> None:
    documents = to_isatab(client)
    referenced = _referenced(documents)
    assert referenced, "the archive references no source, so the test proves nothing"
    assert referenced <= _declared(documents["i_Investigation.txt"])


def test_a_characteristic_embedded_in_its_sample_has_its_source_declared() -> None:
    client = MetaseedClient("metabolights", "1.0")
    investigation = client.create_entity(
        "Investigation", {"identifier": "I1", "title": "t"}, skip_validation=True
    )
    study = client.create_entity(
        "Study",
        {"identifier": "S1", "title": "s"},
        parent_id=investigation.id,
        skip_validation=True,
    )
    client.create_entity(
        "Sample",
        {
            "name": "sample-1",
            "characteristics": [
                {
                    "category": "disease",
                    "value": "healthy",
                    "term_accession": "PATO:0000461",
                }
            ],
        },
        parent_id=study.id,
        skip_validation=True,
    )
    _check(client)
