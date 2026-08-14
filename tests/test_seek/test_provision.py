"""Tests for the SEEK model provisioner (profile -> CVs + Sample Types)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from metaseed.seek.provision import (
    build_provisioning_plan,
    execute_provisioning_plan,
)
from metaseed.specs.schema import (
    Constraints,
    EntityDefSpec,
    FieldSpec,
    FieldType,
    ProfileSpec,
    SeekEntityConfig,
)


def _profile() -> ProfileSpec:
    return ProfileSpec(
        name="testprofile",
        version="1.0",
        root_entity="Investigation",
        entities={
            "Investigation": EntityDefSpec(
                fields=[FieldSpec(name="identifier", type=FieldType.STRING)]
            ),
            "Sample": EntityDefSpec(
                seek=SeekEntityConfig(role="Sample"),
                fields=[
                    FieldSpec(name="identifier", type=FieldType.STRING),
                    FieldSpec(
                        name="organism",
                        type=FieldType.STRING,
                        required=True,
                        ontologies=["ncbitaxon"],
                        constraints=Constraints(enum=["human", "mouse"]),
                    ),
                    FieldSpec(name="count", type=FieldType.INTEGER),
                    FieldSpec(name="depth", type=FieldType.FLOAT),
                    FieldSpec(name="collected", type=FieldType.DATE),
                    # nested entity reference -> not a scalar attribute, skipped
                    FieldSpec(
                        name="source", type=FieldType.ENTITY, items="Investigation"
                    ),
                ],
            ),
        },
    )


class _StubOntology:
    """A term source whose every search finds the queried label exactly."""

    def search_sync(
        self,
        query: str,
        ontology: str | None = None,
        limit: int = 20,
    ) -> list[Any]:
        return [type("R", (), {"label": query, "iri": f"http://x/{query}"})()]


# -- planning ---------------------------------------------------------------


def test_plan_only_includes_sample_role_entities():
    plan = build_provisioning_plan(_profile())
    assert [st.entity_type for st in plan.sample_types] == ["Sample"]
    assert plan.sample_types[0].title == "testprofile Sample"


def test_plan_maps_field_types_and_skips_nested_and_core():
    plan = build_provisioning_plan(_profile())
    attrs = {a.title: a for a in plan.sample_types[0].attributes}
    assert "source" not in attrs  # nested entity dropped
    assert "identifier" not in attrs  # core identity carried by the Title attribute
    assert attrs["Description"].attribute_type_title == "String"
    assert attrs["count"].attribute_type_title == "Integer"
    assert attrs["depth"].attribute_type_title == "Real number"
    assert attrs["collected"].attribute_type_title == "Date"
    assert attrs["organism"].attribute_type_title == "Controlled Vocabulary"


def test_plan_leads_with_title_and_description():
    plan = build_provisioning_plan(_profile())
    attrs = plan.sample_types[0].attributes
    assert attrs[0].title == "Title" and attrs[1].title == "Description"
    title_attrs = [a for a in attrs if a.is_title]
    assert len(title_attrs) == 1 and title_attrs[0].title == "Title"
    assert title_attrs[0].required is True
    assert attrs[1].is_title is False  # Description is not the title attribute
    # Title, Description, then organism/count/depth/collected — 1-based, contiguous
    assert [a.pos for a in attrs] == [1, 2, 3, 4, 5, 6]


def test_plan_sets_schema_org_pid_on_field_attributes_only():
    plan = build_provisioning_plan(_profile())
    attrs = {a.title: a for a in plan.sample_types[0].attributes}
    # PID must equal the URI the data RDF emits for that field, so an FDS import
    # matches the sample to this Sample Type.
    assert attrs["count"].pid == "http://schema.org/count"
    assert attrs["organism"].pid == "http://schema.org/organism"
    # Core Title/Description are matched by attribute title, not PID.
    assert attrs["Title"].pid is None and attrs["Description"].pid is None


def test_plan_builds_cv_from_enum():
    plan = build_provisioning_plan(_profile())
    assert len(plan.cvs) == 1
    cv = plan.cvs[0]
    assert cv.title == "testprofile Sample.organism"
    assert [t.label for t in cv.terms] == ["human", "mouse"]
    assert cv.source_ontology == "ncbitaxon"
    assert all(t.iri is None for t in cv.terms)  # no ontology service -> label only
    # the attribute references the CV by title
    organism = next(a for a in plan.sample_types[0].attributes if a.title == "organism")
    assert organism.cv_title == "testprofile Sample.organism"


def test_plan_enriches_cv_terms_with_ontology_iris():
    plan = build_provisioning_plan(_profile(), term_source=_StubOntology())
    cv = plan.cvs[0]
    assert [t.iri for t in cv.terms] == ["http://x/human", "http://x/mouse"]


# -- execution --------------------------------------------------------------


@dataclass
class _FakeSeek:
    """Records provisioning calls; CV/Sample Type lookups miss by default."""

    existing_cvs: dict[str, str]
    existing_sample_types: dict[str, str]

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self._n = 0

    def _next(self) -> str:
        self._n += 1
        return str(self._n)

    def find_controlled_vocab_id_by_title(self, title: str) -> str | None:
        return self.existing_cvs.get(title)

    def create_controlled_vocab(self, **kwargs: Any) -> str:
        self.calls.append(("create_cv", kwargs))
        return self._next()

    def find_sample_type_id_by_title(
        self, title: str, *, project_id: str | None = None
    ) -> str | None:
        return self.existing_sample_types.get(title)

    def sample_attribute_type_id(self, title: str) -> str:
        return {
            "String": "8",
            "Integer": "4",
            "Real number": "3",
            "Date": "5",
            "Controlled Vocabulary": "14",
        }[title]

    def create_sample_type(
        self, *, title: str, project_id: str, attributes: list[dict[str, Any]]
    ) -> str:
        self.calls.append(
            ("create_sample_type", {"title": title, "attributes": attributes})
        )
        return self._next()


def test_execute_creates_cv_before_sample_type_and_threads_id():
    plan = build_provisioning_plan(_profile())
    seek = _FakeSeek(existing_cvs={}, existing_sample_types={})
    result = execute_provisioning_plan(seek, plan, project_id="1")  # type: ignore[arg-type]

    kinds = [c[0] for c in seek.calls]
    assert kinds == ["create_cv", "create_sample_type"]  # CV first
    cv_id = result.cv_ids["testprofile Sample.organism"]
    st_attrs = seek.calls[1][1]["attributes"]
    organism = next(a for a in st_attrs if a["title"] == "organism")
    assert organism["sample_controlled_vocab_id"] == cv_id  # threaded
    assert organism["sample_attribute_type"]["id"] == "14"  # CV base type
    assert result.created == [
        "CV: testprofile Sample.organism",
        "Sample Type: testprofile Sample",
    ]


def test_execute_posts_schema_org_pids():
    plan = build_provisioning_plan(_profile())
    seek = _FakeSeek(existing_cvs={}, existing_sample_types={})
    execute_provisioning_plan(seek, plan, project_id="1")  # type: ignore[arg-type]

    st_call = next(c[1] for c in seek.calls if c[0] == "create_sample_type")
    count = next(a for a in st_call["attributes"] if a["title"] == "count")
    assert count["pid"] == "http://schema.org/count"  # else FDS import can't match
    title = next(a for a in st_call["attributes"] if a["title"] == "Title")
    assert "pid" not in title  # core Title has no PID


def test_execute_isolates_a_failing_create():
    # A SEEK failure on one create records an error and does not abort the rest.
    plan = build_provisioning_plan(_profile())
    seek = _FakeSeek(existing_cvs={}, existing_sample_types={})

    def boom(**kwargs):
        raise RuntimeError("SEEK 422")

    seek.create_controlled_vocab = boom  # CV creation fails
    result = execute_provisioning_plan(seek, plan, project_id="1")  # type: ignore[arg-type]

    assert result.errors and "SEEK 422" in result.errors[0]
    # the Sample Type is still created despite the CV failure
    assert result.sample_type_ids.get("Sample")
    assert any(c[0] == "create_sample_type" for c in seek.calls)


def test_execute_reuses_existing_and_posts_nothing():
    plan = build_provisioning_plan(_profile())
    seek = _FakeSeek(
        existing_cvs={"testprofile Sample.organism": "99"},
        existing_sample_types={"testprofile Sample": "77"},
    )
    result = execute_provisioning_plan(seek, plan, project_id="1")  # type: ignore[arg-type]

    assert seek.calls == []  # nothing created; existing type reused as-is
    assert result.cv_ids["testprofile Sample.organism"] == "99"
    assert result.sample_type_ids["Sample"] == "77"
    assert result.created == []
    assert set(result.reused) == {
        "CV: testprofile Sample.organism",
        "Sample Type: testprofile Sample",
    }


class TestPropertyUriEscaping:
    """A field name that is not URI-safe still yields a usable property URI.

    SEEK validates an attribute's ``pid`` and rejects the whole Sample Type with
    ``sample_attributes.pid: not a valid URI`` when it is not one -- naming no
    attribute, so a single field with a space in its name failed the entire
    provisioning run with nothing to go on.
    """

    def test_a_name_with_a_space_is_encoded(self) -> None:
        from metaseed.seek.naming import property_uri

        assert property_uri("Source Name") == "http://schema.org/Source%20Name"

    def test_an_ordinary_name_is_left_alone(self) -> None:
        """Encoding must not move URIs already provisioned in a SEEK instance."""
        from metaseed.seek.naming import property_uri

        assert property_uri("growth_medium") == "http://schema.org/growth_medium"

    def test_every_provisioned_pid_is_a_valid_uri(self) -> None:
        """The plan is what gets posted, so the check belongs on the plan."""
        from urllib.parse import urlparse

        from metaseed.specs.schema import (
            EntityDefSpec,
            FieldSpec,
            FieldType,
            ProfileSpec,
        )

        spec = ProfileSpec(
            version="1.0",
            name="spaced",
            display_name="Spaced",
            description="d",
            ontology="T",
            root_entity="Source",
            entities={
                "Source": EntityDefSpec(
                    description="d",
                    fields=[
                        FieldSpec(name="Source Name", type=FieldType.STRING),
                        FieldSpec(name="growth_medium", type=FieldType.STRING),
                    ],
                )
            },
        )

        plan = build_provisioning_plan(spec)
        pids = [
            attribute.pid
            for sample_type in plan.sample_types
            for attribute in sample_type.attributes
            if attribute.pid is not None
        ]
        assert pids, "the profile should produce attributes carrying a pid"
        for pid in pids:
            parsed = urlparse(pid)
            assert parsed.scheme and parsed.netloc, pid
            assert " " not in pid, pid

    def test_the_data_rdf_uses_the_same_uri(self) -> None:
        """Provisioning and the data RDF must agree or an import matches nothing."""
        pytest.importorskip("rdflib")
        from rdflib import Graph, URIRef

        from metaseed.seek.fairds import _emit_property_definition
        from metaseed.seek.naming import property_uri
        from metaseed.specs.schema import FieldSpec, FieldType

        graph = Graph()
        _emit_property_definition(
            graph, "Source Name", FieldSpec(name="Source Name", type=FieldType.STRING)
        )

        emitted = {str(s) for s in graph.subjects()}
        assert property_uri("Source Name") in emitted
        assert URIRef("http://schema.org/Source Name") not in set(graph.subjects())

    def test_a_dataset_with_a_spaced_field_name_exports(self) -> None:
        """Exporting is where the unencoded URI actually bit.

        Provisioning was fixed first, and its tests passed, but the data RDF
        built property URIs at a second site that still concatenated the field
        name. rdflib refuses to serialize ``http://schema.org/Source Name`` at
        all, so exporting any dataset on such a profile raised rather than
        producing a graph SEEK could read.
        """
        pytest.importorskip("rdflib")
        from metaseed import MetaseedClient
        from metaseed.seek.fairds import to_fair_data_station_rdf
        from metaseed.seek.naming import property_uri
        from metaseed.specs.schema import (
            EntityDefSpec,
            FieldSpec,
            FieldType,
            ProfileSpec,
        )

        spec = ProfileSpec(
            version="1.0",
            name="spaced-export",
            display_name="Spaced export",
            description="d",
            ontology="T",
            root_entity="Investigation",
            entities={
                "Investigation": EntityDefSpec(
                    description="d",
                    fields=[
                        FieldSpec(name="title", type=FieldType.STRING),
                        FieldSpec(name="Source Name", type=FieldType.STRING),
                    ],
                )
            },
        )

        client = MetaseedClient.from_spec(spec.model_dump(mode="json"))
        client.create_entity(
            "Investigation",
            {"title": "t", "Source Name": "S-1"},
            skip_validation=True,
        )

        rdf = to_fair_data_station_rdf(client)
        text = rdf.decode() if isinstance(rdf, bytes) else rdf

        assert "schema.org/Source Name" not in text, "an unserializable URI"
        assert property_uri("Source Name").rsplit("/", 1)[-1] in text


class TestCvIdsAreNamespacedByEntity:
    """resolve_cv_ids must not flatten the entity namespacing _cv_title built.

    Keying by bare field name meant two sample-role entities with same-named
    enum fields (distinct CVs in SEEK) collided: the last entity iterated won
    and every level's attributes bound to that one CV id, silently validating
    against the wrong vocabulary.
    """

    class _Client:
        def find_controlled_vocab_id_by_title(self, title: str) -> str | None:
            return f"id-for::{title}"

    def _profile_with_shared_field_name(self):
        from metaseed.specs.schema import (
            Constraints,
            EntityDefSpec,
            FieldSpec,
            FieldType,
            ProfileSpec,
            SeekEntityConfig,
        )

        def entity(enum):
            return EntityDefSpec(
                seek=SeekEntityConfig(role="Sample"),
                fields=[
                    FieldSpec(
                        name="status",
                        type=FieldType.STRING,
                        constraints=Constraints(enum=enum),
                    )
                ],
            )

        return ProfileSpec(
            name="p",
            version="1.0",
            root_entity="Source",
            entities={
                "Source": entity(["raw", "washed"]),
                "Sample": entity(["frozen", "fresh"]),
            },
        )

    def test_same_named_fields_on_two_entities_do_not_collide(self):
        from metaseed.seek.provision import resolve_cv_ids

        ids = resolve_cv_ids(self._Client(), self._profile_with_shared_field_name())

        distinct = set(ids.values())
        assert len(distinct) == 2, f"the two CVs collapsed into one: {ids}"

    def test_each_entity_reads_back_its_own_vocabulary(self):
        from metaseed.seek.provision import cv_ids_for_entity, resolve_cv_ids

        ids = resolve_cv_ids(self._Client(), self._profile_with_shared_field_name())

        source = cv_ids_for_entity(ids, "Source")
        sample = cv_ids_for_entity(ids, "Sample")
        assert source["status"] != sample["status"]
