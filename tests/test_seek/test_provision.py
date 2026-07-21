"""Tests for the SEEK model provisioner (profile -> CVs + Sample Types)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    """Returns a fixed IRI for any exact term search."""

    def search_sync(
        self,
        query: str,
        ontology: str | None = None,
        rows: int = 10,
        exact: bool = False,
    ) -> list[Any]:
        return [type("R", (), {"iri": f"http://x/{query}"})()]


# -- planning ---------------------------------------------------------------


def test_plan_only_includes_sample_role_entities():
    plan = build_provisioning_plan(_profile())
    assert [st.entity_type for st in plan.sample_types] == ["Sample"]
    assert plan.sample_types[0].title == "testprofile Sample"


def test_plan_maps_field_types_and_skips_nested():
    plan = build_provisioning_plan(_profile())
    attrs = {a.title: a for a in plan.sample_types[0].attributes}
    assert "source" not in attrs  # nested entity dropped
    assert attrs["identifier"].attribute_type_title == "String"
    assert attrs["count"].attribute_type_title == "Integer"
    assert attrs["depth"].attribute_type_title == "Real number"
    assert attrs["collected"].attribute_type_title == "Date"
    assert attrs["organism"].attribute_type_title == "Controlled Vocabulary"


def test_plan_marks_identifier_as_title_and_positions():
    plan = build_provisioning_plan(_profile())
    attrs = plan.sample_types[0].attributes
    title_attrs = [a for a in attrs if a.is_title]
    assert len(title_attrs) == 1 and title_attrs[0].title == "identifier"
    assert title_attrs[0].required is True  # title is forced required
    assert [a.pos for a in attrs] == [1, 2, 3, 4, 5]  # 1-based, contiguous


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
    plan = build_provisioning_plan(_profile(), ontology=_StubOntology())
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

    assert seek.calls == []  # nothing created
    assert result.cv_ids["testprofile Sample.organism"] == "99"
    assert result.sample_type_ids["Sample"] == "77"
    assert result.created == []
    assert set(result.reused) == {
        "CV: testprofile Sample.organism",
        "Sample Type: testprofile Sample",
    }
