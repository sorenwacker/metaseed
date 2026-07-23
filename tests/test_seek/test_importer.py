"""Tests for the SEEK -> metaseed importer.

Hermetic — a fake SEEK client serves canned JSON:API responses (the shapes were
captured from a live SEEK 1.18.1 instance), so no network/SEEK is needed.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

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
                    "traits": ["drought", "salt"],
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
                    {"title": "Title", "sample_attribute_type": {"title": "String"}},
                    {
                        "title": "Description",
                        "sample_attribute_type": {"title": "Text"},
                    },
                    {
                        "title": "plant_anatomical_entity",
                        "sample_attribute_type": {"title": "String"},
                    },
                    {
                        "title": "collection_date",
                        "sample_attribute_type": {"title": "Date"},
                    },
                    {
                        "title": "traits",
                        "sample_attribute_type": {
                            "title": "Controlled Vocabulary List"
                        },
                    },
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


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "http://seek.test/studies/10/observation_units")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(f"{status}", request=request, response=response)


def test_import_tolerates_instances_without_observation_units():
    # A 4xx on the observation_units sub-route means no ISA-JSON; the study still
    # imports (with no samples) rather than aborting.
    class _NoOus(_FakeSeek):
        def get(self, path: str) -> Any:
            if path.endswith("/observation_units"):
                raise _http_error(422)
            return super().get(path)

    dataset = import_from_seek(_NoOus(), "8")  # type: ignore[arg-type]
    types = {e["_type"] for e in dataset.serialize()["entities"]}
    assert types == {"Investigation", "Study"}  # skeleton imported, no samples


def test_import_reraises_server_errors_on_observation_units():
    # A 5xx / transport error is a real failure and must NOT be swallowed into an
    # empty study.
    class _Boom(_FakeSeek):
        def get(self, path: str) -> Any:
            if path.endswith("/observation_units"):
                raise _http_error(500)
            return super().get(path)

    with pytest.raises(httpx.HTTPStatusError):
        import_from_seek(_Boom(), "8")  # type: ignore[arg-type]


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


def test_import_uses_external_identifier_not_internal_row_id():
    # For the round trip to update (not duplicate) via "Update from FAIR Data
    # Station", identity must be the FDS external identifier, never SEEK's row id.
    entities = _imported().serialize()["entities"]
    sample = next(e for e in entities if e["title"] == "CLEAN-A")
    assert sample["identifier"] == "CLEAN-A"  # not "5"


def test_import_preserves_attribute_types_from_sample_type():
    # SEEK base types map onto metaseed field types instead of collapsing to
    # ``string``: a Date stays a date and a Controlled Vocabulary List stays a
    # list (so its array value survives the FDS re-export rather than being
    # dropped as a non-scalar in a string field).
    profile = _imported()._facade._spec
    fields = {f.name: f for f in profile.entities["Sample"].fields}
    assert fields["collection_date"].type.value == "date"
    assert fields["traits"].type.value == "list"
    assert fields["traits"].items == "string"


def test_import_caches_sample_type_lookups():
    # The Sample Type schema is fetched once per type, not once per sample: both
    # samples share type 20, so exactly one GET /sample_types/20 is issued.
    fake = _FakeSeek()
    import_from_seek(fake, "8")  # type: ignore[arg-type]
    assert fake.reads.count("/sample_types/20") == 1
