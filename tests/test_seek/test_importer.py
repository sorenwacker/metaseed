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
    # A study serves its assays too; the API sync hangs Samples off an Assay
    # rather than an ObservationUnit, so the importer reads both routes.
    "/studies/10/assays": {"data": []},
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


# A second canned instance carrying the ISA material chain the sync builds:
# Investigation 9 -> Study 11 -> assay stream 30 + Assay 31, whose sample 50 is
# an assay material naming collection Sample 51 as its input, which names
# Source 52 as its own. (Shapes captured from a live SEEK 1.18.1.)
_CHAIN_RESPONSES: dict[str, Any] = {
    "/investigations/9": {
        "data": {
            "id": "9",
            "attributes": {"title": "Chained Import", "description": "d"},
            "relationships": {"studies": {"data": [{"id": "11"}]}},
        }
    },
    "/studies/11": {
        "data": {
            "id": "11",
            "attributes": {"title": "chain study", "description": None},
            "relationships": {"investigation": {"data": {"id": "9"}}},
        }
    },
    "/studies/11/observation_units": {"data": []},
    "/studies/11/assays": {"data": [{"id": "30"}, {"id": "31"}]},
    "/assays/30": {
        "data": {
            "id": "30",
            "attributes": {
                "title": "chain study - stream",
                "assay_class": {"title": "Assay Stream", "key": "STREAM"},
            },
            "relationships": {"samples": {"data": []}},
        }
    },
    "/assays/31": {
        "data": {
            "id": "31",
            "attributes": {
                "title": "measuring",
                "assay_class": {"title": "Experimental assay", "key": "EXP"},
            },
            "relationships": {"samples": {"data": [{"id": "50"}]}},
        }
    },
    "/samples/50": {
        "data": {
            "id": "50",
            "attributes": {
                "title": "MAT-1",
                "attribute_map": {
                    "Input (Title)": [{"id": 51, "type": "Sample", "title": "SMP-1"}],
                    "Protocol": "measuring",
                    "Title": "MAT-1",
                    "material_name": "MAT-1",
                },
            },
            "relationships": {"sample_type": {"data": {"id": "40"}}},
        }
    },
    "/samples/51": {
        "data": {
            "id": "51",
            "attributes": {
                "title": "SMP-1",
                "attribute_map": {
                    "Input (Title)": [{"id": 52, "type": "Sample", "title": "SRC-1"}],
                    "Title": "SMP-1",
                    "sample_name": "SMP-1",
                    "organism_part": "leaf",
                },
            },
            "relationships": {"sample_type": {"data": {"id": "41"}}},
        }
    },
    "/samples/52": {
        "data": {
            "id": "52",
            "attributes": {
                "title": "SRC-1",
                "attribute_map": {
                    "Title": "SRC-1",
                    "source_name": "SRC-1",
                    "organism": "Arabidopsis thaliana",
                },
            },
            "relationships": {"sample_type": {"data": {"id": "42"}}},
        }
    },
    "/sample_types/40": {
        "data": {
            "attributes": {
                "sample_attributes": [
                    {"title": "Title", "sample_attribute_type": {"title": "String"}},
                    {
                        "title": "Input (Title)",
                        "sample_attribute_type": {"title": "Registered Sample List"},
                    },
                    {"title": "Protocol", "sample_attribute_type": {"title": "String"}},
                    {
                        "title": "material_name",
                        "sample_attribute_type": {"title": "String"},
                    },
                ]
            }
        }
    },
    "/sample_types/41": {
        "data": {
            "attributes": {
                "sample_attributes": [
                    {"title": "Title", "sample_attribute_type": {"title": "String"}},
                    {
                        "title": "Input (Title)",
                        "sample_attribute_type": {"title": "Registered Sample List"},
                    },
                    {
                        "title": "sample_name",
                        "sample_attribute_type": {"title": "String"},
                    },
                    {
                        "title": "organism_part",
                        "sample_attribute_type": {"title": "String"},
                    },
                ]
            }
        }
    },
    "/sample_types/42": {
        "data": {
            "attributes": {
                "sample_attributes": [
                    {"title": "Title", "sample_attribute_type": {"title": "String"}},
                    {
                        "title": "source_name",
                        "sample_attribute_type": {"title": "String"},
                    },
                    {"title": "organism", "sample_attribute_type": {"title": "String"}},
                ]
            }
        }
    },
}


class _FakeSeek:
    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.reads: list[str] = []
        self._responses = _RESPONSES if responses is None else responses

    def get(self, path: str) -> Any:
        self.reads.append(path)
        return self._responses[path]


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


def _seek_api_error(status: int):
    """What the real client actually raises — not httpx's exception."""
    from metaseed.seek.client import SeekApiError

    request = httpx.Request("GET", "http://seek.test/studies/10/observation_units")
    response = httpx.Response(
        status, request=request, json={"errors": [{"detail": "no ISA-JSON here"}]}
    )
    return SeekApiError(response)


def test_the_degradation_fires_on_what_the_client_raises():
    """`SeekClient.get` raises SeekApiError, never httpx.HTTPStatusError — so
    the 4xx degradation below was written against an exception that can not
    occur, and every instance without ISA-JSON aborted the whole import."""

    class _NoOus(_FakeSeek):
        def get(self, path: str) -> Any:
            if path.endswith("/observation_units") or path.endswith("/assays"):
                raise _seek_api_error(422)
            return super().get(path)

    dataset = import_from_seek(_NoOus(), "8")  # type: ignore[arg-type]
    types = {e["_type"] for e in dataset.serialize()["entities"]}
    assert types == {"Investigation", "Study"}


def test_a_server_side_seek_error_still_aborts():
    from metaseed.seek.client import SeekApiError

    class _Boom(_FakeSeek):
        def get(self, path: str) -> Any:
            if path.endswith("/observation_units"):
                raise _seek_api_error(500)
            return super().get(path)

    with pytest.raises(SeekApiError):
        import_from_seek(_Boom(), "8")  # type: ignore[arg-type]


def _chain_imported():
    return import_from_seek(_FakeSeek(_CHAIN_RESPONSES), "9")  # type: ignore[arg-type]


def test_an_assay_stream_is_not_imported_as_an_assay():
    # The stream is sync plumbing (every Assay hangs off one); reading it back
    # as an Assay doubles the assay count on every round trip.
    entities = _chain_imported().serialize()["entities"]
    assays = [e["title"] for e in entities if e["_type"] == "Assay"]
    assert assays == ["measuring"]


def test_the_material_chain_reads_back_as_source_sample_material():
    # The sync writes Source -> Sample -> assay material, each naming its
    # predecessor in its input attribute. The importer follows those links so
    # the levels come back as levels, not as three unrelated samples.
    dataset = _chain_imported()
    entities = dataset.serialize()["entities"]
    counts: dict[str, int] = {}
    for e in entities:
        counts[e["_type"]] = counts.get(e["_type"], 0) + 1
    assert counts == {
        "Investigation": 1,
        "Study": 1,
        "Assay": 1,
        "Source": 1,
        "Sample": 1,
        "AssayMaterial": 1,
    }
    sample = next(e for e in entities if e["_type"] == "Sample")
    assert sample["sample_name"] == "SMP-1"
    assert "Input (Title)" not in sample, "the input link is structure, not data"
    material = next(e for e in entities if e["_type"] == "AssayMaterial")
    assert material["material_name"] == "MAT-1"


def test_the_imported_chain_is_nested_not_flattened():
    dataset = _chain_imported()

    def children_types(node_id):
        return sorted(
            dataset.get_entity(c.id).entity_type for c in dataset.get_children(node_id)
        )

    roots = dataset.get_tree()
    inv = roots[0]
    (study,) = dataset.get_children(inv.id)
    assert children_types(study.id) == ["Assay", "Source"]
    source = next(
        c
        for c in dataset.get_children(study.id)
        if dataset.get_entity(c.id).entity_type == "Source"
    )
    (sample,) = dataset.get_children(source.id)
    assert dataset.get_entity(sample.id).entity_type == "Sample"
    (material,) = dataset.get_children(sample.id)
    assert dataset.get_entity(material.id).entity_type == "AssayMaterial"
