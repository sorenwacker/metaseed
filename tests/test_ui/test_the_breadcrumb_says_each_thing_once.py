"""A breadcrumb says each thing once, in a form that can be read.

The trail read:

    Entities > Catalog: https://example.org/catalog/example-umc-research
             > dataset > Dataset: https://example.org/dataset/example-cohort-2025
             > distribution > Distribution: https://example.org/dataset/...
             > checksum > Checksum: 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b...

Two faults. The field crumb repeats the type of the crumb after it whenever
they are named alike -- ``dataset > Dataset:`` -- and every label is a full
IRI, so the trail wraps over two lines and every crumb begins the same way.
A field whose name differs from the type it holds (``contact_point > Kind:``)
still earns its place: it is the only thing saying which field holds the child.

The two builders also disagreed: the edit form rendered "Catalog: <iri>" and
the nested pages rendered "<iri>" alone, for the same entity.
"""

from __future__ import annotations

from metaseed.ui.helpers.navigation_helpers import (
    crumb_label,
    names_the_same_thing,
    short_label,
)


def test_a_label_is_the_readable_end_of_an_iri() -> None:
    assert short_label("https://example.org/dataset/example-cohort-2025") == (
        "example-cohort-2025"
    )
    assert short_label("https://example.org/catalog/example-umc-research/") == (
        "example-umc-research"
    )


def test_a_plain_label_is_left_alone() -> None:
    """Only an IRI is shortened; a name is already what it says."""
    assert short_label("Example UMC Research Data Desk") == (
        "Example UMC Research Data Desk"
    )
    assert short_label("datadesk@example.org") == "datadesk@example.org"


def test_a_crumb_names_the_type_and_the_thing() -> None:
    assert crumb_label("Catalog", "https://example.org/catalog/x") == "Catalog: x"
    assert crumb_label("Kind", None) == "Kind", "with no label the type stands alone"


def test_a_field_crumb_that_only_repeats_the_type_is_redundant() -> None:
    assert names_the_same_thing("dataset", "Dataset")
    assert names_the_same_thing("dataset_series", "DatasetSeries")
    assert names_the_same_thing("service", "Service")


def test_a_field_crumb_that_says_something_is_kept() -> None:
    """contact_point holds a Kind, publisher holds an Agent: the field is the
    only thing that says which of the parent's fields this child sits in."""
    assert not names_the_same_thing("contact_point", "Kind")
    assert not names_the_same_thing("publisher", "Agent")
    assert not names_the_same_thing("qualified_attribution", "Attribution")
