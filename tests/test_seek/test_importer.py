"""Tests for the SEEK -> metaseed importer.

Hermetic — a fake SEEK client serves canned JSON:API responses (the shapes were
captured from a live SEEK 1.18.1 instance), so no network/SEEK is needed.
"""

from __future__ import annotations

from typing import Any

from metaseed.seek.importer import import_from_seek

# Canned JSON:API resources, keyed by path, mirroring a live instance:
# Investigation 8 -> Study 10 -> ObservationUnit 2 -> Samples 5, 6.
_RESPONSES: dict[str, Any] = {
    "/investigations/8": {
        "data": {
            "id": "8",
            "attributes": {"title": "Unaided Import", "description": "d"},
            "relationships": {"studies": {"data": [{"id": "10"}]}},
        }
    },
    "/studies/10": {
        "data": {
            "id": "10",
            "attributes": {"title": "Trial", "description": None},
            "relationships": {"investigation": {"data": {"id": "8"}}},
        }
    },
    "/studies/10/observation_units": {"data": [{"id": "2"}]},
    "/observation_units/2": {
        "data": {
            "id": "2",
            "attributes": {"title": "OU-CLEAN", "description": None},
            "relationships": {"samples": {"data": [{"id": "5"}, {"id": "6"}]}},
        }
    },
    "/samples/5": {
        "data": {
            "id": "5",
            "attributes": {
                "title": "CLEAN-A",
                "attribute_map": {
                    "Title": "CLEAN-A",
                    "Description": None,
                    "plant_anatomical_entity": "leaf",
                    "collection_date": None,
                },
            },
            "relationships": {"sample_type": {"data": {"id": "20"}}},
        }
    },
    "/samples/6": {
        "data": {
            "id": "6",
            "attributes": {
                "title": "CLEAN-B",
                "attribute_map": {
                    "Title": "CLEAN-B",
                    "plant_anatomical_entity": "root",
                },
            },
            "relationships": {"sample_type": {"data": {"id": "20"}}},
        }
    },
    "/sample_types/20": {
        "data": {
            "attributes": {
                "sample_attributes": [
                    {"title": "Title"},
                    {"title": "Description"},
                    {"title": "plant_anatomical_entity"},
                    {"title": "collection_date"},
                ]
            }
        }
    },
}


class _FakeSeek:
    def __init__(self) -> None:
        self.reads: list[str] = []

    def get(self, path: str) -> Any:
        self.reads.append(path)
        return _RESPONSES[path]


def _imported():
    return import_from_seek(_FakeSeek(), "8")  # type: ignore[arg-type]


def test_import_rebuilds_the_isa_tree():
    dataset = _imported()
    entities = dataset.serialize()["entities"]
    counts: dict[str, int] = {}
    for e in entities:
        counts[e["_type"]] = counts.get(e["_type"], 0) + 1
    assert counts == {
        "Investigation": 1,
        "Study": 1,
        "ObservationUnit": 1,
        "Sample": 2,
    }


def test_import_preserves_sample_field_values():
    entities = _imported().serialize()["entities"]
    samples = {e["title"]: e for e in entities if e["_type"] == "Sample"}
    assert samples["CLEAN-A"]["plant_anatomical_entity"] == "leaf"
    assert samples["CLEAN-B"]["plant_anatomical_entity"] == "root"


def test_imported_dataset_round_trips_to_fds_rdf():
    # The derived-spec dataset must re-export via the FDS RDF path (which reads the
    # facade's in-memory spec, since there is no profile file to load) — closing
    # the SEEK -> metaseed -> SEEK loop.
    from metaseed.seek.fairds import to_fair_data_station_rdf

    ttl = to_fair_data_station_rdf(_imported())
    assert "jerm:Sample" in ttl
    assert "CLEAN-A" in ttl and "leaf" in ttl  # sample value survives the round trip


def test_import_tolerates_instances_without_observation_units():
    # A SEEK instance without ISA-JSON answers the observation_units sub-route with
    # an error; the study must still import (with no samples) rather than aborting.
    class _NoOus(_FakeSeek):
        def get(self, path: str) -> Any:
            if path.endswith("/observation_units"):
                raise RuntimeError("422 Unprocessable Entity")
            return super().get(path)

    dataset = import_from_seek(_NoOus(), "8")  # type: ignore[arg-type]
    types = {e["_type"] for e in dataset.serialize()["entities"]}
    assert types == {"Investigation", "Study"}  # skeleton imported, no samples


def test_import_routes_core_attributes_onto_title():
    entities = _imported().serialize()["entities"]
    inv = next(e for e in entities if e["_type"] == "Investigation")
    assert inv["title"] == "Unaided Import"  # SEEK title -> entity title
    sample = next(
        e for e in entities if e["_type"] == "Sample" and e["title"] == "CLEAN-A"
    )
    # the SEEK "Title" attribute becomes the entity title, not a stray data field
    assert "Title" not in sample
    assert sample["plant_anatomical_entity"] == "leaf"
