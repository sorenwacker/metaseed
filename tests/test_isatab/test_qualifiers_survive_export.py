"""Every characteristic and factor value reaches the study table (260816 review).

Two ways to lose one, both found in `_sample_qualifiers`:

- It read only the sample's embedded `characteristics` / `factor_values`
  lists. The MetaboLights importer creates those as CHILD ENTITIES of the
  sample, so an import-then-export round trip emitted `Characteristics[Organism]`
  and nothing else — every imported qualifier was dropped on the way out.
- It read `category` for both kinds. `Characteristic` declares `category`, but
  `FactorValue` declares `factor_name` in every ISA-shaped profile that ships,
  so a factor value produced an anonymous `Factor Value[]` column with no name.

The second survived because the existing round-trip fixture authored
`factor_values=[{"category": ...}]` with `skip_validation=True` — a shape the
profile forbids — so the test agreed with the bug instead of catching it.
"""

from __future__ import annotations

from metaseed import MetaseedClient
from metaseed.isatab import to_isatab


def _study_table(documents: dict[str, str]) -> str:
    return next(text for name, text in documents.items() if name.startswith("s_"))


def _client_with_child_qualifiers() -> MetaseedClient:
    """A sample whose qualifiers are child entities, as the importer creates."""
    client = MetaseedClient("metabolights", "1.0")
    inv = client.create_entity(
        "Investigation", {"identifier": "MTBLS1", "title": "I"}, skip_validation=True
    )
    study = client.create_entity(
        "Study",
        {"identifier": "s_1", "title": "S"},
        parent_id=inv.id,
        skip_validation=True,
    )
    sample = client.create_entity(
        "Sample",
        {"name": "SAMP1", "organism": "Homo sapiens"},
        parent_id=study.id,
        skip_validation=True,
    )
    client.create_entity(
        "Characteristic",
        {"category": "Age", "value": "42"},
        parent_id=sample.id,
        skip_validation=True,
    )
    client.create_entity(
        "FactorValue",
        {"factor_name": "Dose", "value": "high"},
        parent_id=sample.id,
        skip_validation=True,
    )
    return client


def test_a_characteristic_authored_as_a_child_reaches_the_table() -> None:
    table = _study_table(to_isatab(_client_with_child_qualifiers()))

    assert "Characteristics[Age]" in table, table.splitlines()[0]
    assert "42" in table


def test_a_factor_value_authored_as_a_child_reaches_the_table() -> None:
    table = _study_table(to_isatab(_client_with_child_qualifiers()))

    assert "Factor Value[Dose]" in table, table.splitlines()[0]
    assert "high" in table


def test_a_factor_value_is_named_by_the_field_the_profile_declares() -> None:
    """`factor_name`, not `category` — an unnamed column is a lost factor."""
    client = MetaseedClient("metabolights", "1.0")
    inv = client.create_entity(
        "Investigation", {"identifier": "MTBLS1", "title": "I"}, skip_validation=True
    )
    study = client.create_entity(
        "Study",
        {"identifier": "s_1", "title": "S"},
        parent_id=inv.id,
        skip_validation=True,
    )
    client.create_entity(
        "Sample",
        {
            "name": "SAMP1",
            "organism": "Homo sapiens",
            "factor_values": [{"factor_name": "Dose", "value": "high"}],
        },
        parent_id=study.id,
        skip_validation=True,
    )

    table = _study_table(to_isatab(client))

    assert "Factor Value[Dose]" in table, table.splitlines()[0]
    assert "Factor Value[]" not in table
