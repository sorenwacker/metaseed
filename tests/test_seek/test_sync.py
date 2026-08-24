"""Tests for the SEEK data pusher (dataset -> ISA-JSON compliant SEEK content).

The sync builds the structure SEEK can export as ISA-JSON: a compliant
Investigation, a Study owning a Source and a Sample Collection Sample Type, one
assay stream per Study, and one Sample Type per Assay chained to the preceding
one. See ``docs/architecture/seek-isa-compliance.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from metaseed import MetaseedClient
from metaseed.seek.ports import IsaWriter
from metaseed.seek.sync import sync_dataset_to_seek
from metaseed.specs.loader import SpecLoader


class _AnyTemplate(dict):
    """A template map that has whatever title is asked for."""

    def get(self, key, default=None):  # type: ignore[override]
        return f"template-for-{key}"


@dataclass
class _FakeSeek:
    """Records the ISA creates, handing out incrementing ids.

    Typed as :class:`IsaWriter` below, so a method added to the real client and
    not here fails type checking rather than surfacing mid-walk.
    """

    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    study_types: dict[str, dict[str, str]] = field(default_factory=dict)
    assay_types: dict[str, dict[str, str]] = field(default_factory=dict)
    templates_installed: bool = True
    _n: int = 0

    def _next(self) -> str:
        self._n += 1
        return str(self._n)

    def isa_tag_ids(self) -> dict[str, str]:
        tags = (
            "source",
            "source_characteristic",
            "sample",
            "sample_characteristic",
            "protocol",
            "parameter_value",
            "other_material",
            "other_material_characteristic",
            "data_file",
            "data_file_comment",
            "input",
        )
        return {tag: str(i) for i, tag in enumerate(tags, start=1)}

    # Extended Metadata Types "installed" on the fake: title -> id, and per
    # id its attributes (title -> nested type id or None). Empty by default.
    emt_ids: dict[str, str] = field(default_factory=dict)
    emt_attributes: dict[str, dict[str, tuple[str | None, str]]] = field(
        default_factory=dict
    )

    def extended_metadata_type_ids(self) -> dict[str, str]:
        return dict(self.emt_ids)

    def extended_metadata_attributes(
        self, type_id: str
    ) -> dict[str, tuple[str | None, str]]:
        return dict(self.emt_attributes.get(type_id, {}))

    def template_ids_by_title(self) -> dict[str, str]:
        """Every ISA Template installed, or none.

        Answers any title when ``templates_installed`` -- the sync looks them up
        by a name it derives from the profile, which a double cannot predict.
        """
        return _AnyTemplate() if self.templates_installed else {}

    def create_investigation(
        self,
        *,
        title: str,
        project_id: str,
        description: str | None = None,
        isa_json_compliant: bool = False,
        sharing: str | None = None,
    ) -> str:
        self.calls.append(
            (
                "investigation",
                {
                    "title": title,
                    "compliant": isa_json_compliant,
                    "sharing": sharing,
                },
            )
        )
        return self._next()

    def create_isa_study(
        self,
        *,
        title: str,
        investigation_id: str,
        source_title: str,
        source_attributes: Any,
        collection_title: str,
        collection_attributes: Any,
        source_template_id: str | None = None,
        collection_template_id: str | None = None,
        sharing: str | None = None,
        extended_metadata: tuple[str, Any] | None = None,
    ) -> str:
        study_id = self._next()
        self.calls.append(
            (
                "study",
                {
                    "title": title,
                    "investigation_id": investigation_id,
                    "source_attributes": list(source_attributes),
                    "collection_attributes": list(collection_attributes),
                    "source_template_id": source_template_id,
                    "collection_template_id": collection_template_id,
                    "sharing": sharing,
                    "extended_metadata": extended_metadata,
                },
            )
        )
        self.study_types[study_id] = {
            source_title: self._next(),
            collection_title: self._next(),
        }
        return study_id

    def create_isa_assay(
        self,
        *,
        title: str,
        study_id: str,
        assay_class_id: int,
        assay_stream_id: str | None = None,
        input_sample_type_id: str | None = None,
        sample_type_title: str | None = None,
        sample_type_attributes: Any = None,
        sample_type_template_id: str | None = None,
        sharing: str | None = None,
        extended_metadata: tuple[str, Any] | None = None,
    ) -> str:
        assay_id = self._next()
        self.calls.append(
            (
                "stream" if sample_type_title is None else "assay",
                {
                    "title": title,
                    "study_id": study_id,
                    "assay_class_id": assay_class_id,
                    "assay_stream_id": assay_stream_id,
                    "input_sample_type_id": input_sample_type_id,
                    "template_id": sample_type_template_id,
                    "sharing": sharing,
                    "extended_metadata": extended_metadata,
                },
            )
        )
        if sample_type_title is not None:
            self.assay_types[assay_id] = {sample_type_title: self._next()}
        return assay_id

    def study_sample_type_ids(self, study_id: str) -> dict[str, str]:
        return self.study_types.get(study_id, {})

    def assay_sample_type_ids(self, assay_id: str) -> dict[str, str]:
        return self.assay_types.get(assay_id, {})

    def create_sample(
        self,
        *,
        sample_type_id: str,
        project_id: str,
        data: dict[str, Any],
        assay_ids: Any = None,
        study_id: str | None = None,
    ) -> str:
        self.calls.append(
            (
                "sample",
                {
                    "sample_type_id": sample_type_id,
                    "data": data,
                    "assay_ids": list(assay_ids) if assay_ids else None,
                },
            )
        )
        return self._next()

    def create_sample_type(
        self, *, title: str, project_id: str, attributes: list[dict[str, Any]]
    ) -> str:
        self.calls.append(("sample_type", {"title": title}))
        return self._next()

    def find_sample_type_id_by_title(
        self, title: str, *, project_id: str | None = None
    ) -> str | None:
        return None

    # What a previous push left behind. Empty by default, so the first push of a
    # dataset creates everything; a test that pushes twice fills these from the
    # first run's calls.
    existing_investigations: dict[str, str] = field(default_factory=dict)
    existing_studies: dict[tuple[str, str], str] = field(default_factory=dict)
    existing_assays: dict[tuple[str, str], str] = field(default_factory=dict)
    existing_samples: dict[tuple[str, str], str] = field(default_factory=dict)

    def find_investigation_id_by_title(
        self, title: str, *, project_id: str
    ) -> str | None:
        return self.existing_investigations.get(title)

    def find_study_id_by_title(
        self, title: str, *, investigation_id: str
    ) -> str | None:
        return self.existing_studies.get((title, investigation_id))

    def find_assay_id_by_title(self, title: str, *, study_id: str) -> str | None:
        return self.existing_assays.get((title, study_id))

    def find_sample_id_by_title(self, title: str, *, sample_type_id: str) -> str | None:
        return self.existing_samples.get((title, sample_type_id))

    def sample_attribute_type_id(self, title: str) -> str:
        return "8"

    def create_data_file(
        self,
        *,
        title: str,
        project_id: str,
        url: str,
        original_filename: str,
        description: str | None = None,
        assay_ids: Any = None,
    ) -> str:
        self.calls.append(
            ("data_file", {"url": url, "description": description, "title": title})
        )
        return self._next()


def test_the_fake_satisfies_the_port_the_sync_depends_on() -> None:
    writer: IsaWriter = _FakeSeek()
    assert writer is not None


def _dataset(*, assays: int = 1, materials_per_assay: int = 1) -> MetaseedClient:
    """A seek-ready-template 3.0 dataset carrying the ISA material chain.

    Investigation -> Study -> Source -> Sample -> AssayMaterial, with the Assays
    hanging off the Study and each material naming the Assay that measured it.
    """
    client = MetaseedClient("seek-ready-template", "3.0")
    inv = client.create_entity(
        "Investigation",
        {"identifier": "INV1", "title": "My Investigation"},
        skip_validation=True,
    )
    study = client.create_entity(
        "Study",
        {"identifier": "STU1", "title": "Study one"},
        parent_id=inv.id,
        skip_validation=True,
    )
    for a in range(assays):
        client.create_entity(
            "Assay",
            {"identifier": f"ASSAY{a}", "title": f"Assay {a}"},
            parent_id=study.id,
            skip_validation=True,
        )
    source = client.create_entity(
        "Source",
        {"source_name": "source-1", "organism": "Arabidopsis thaliana"},
        parent_id=study.id,
        skip_validation=True,
    )
    sample = client.create_entity(
        "Sample",
        {"sample_name": "sample-1"},
        parent_id=source.id,
        skip_validation=True,
    )
    for a in range(assays):
        for m in range(materials_per_assay):
            client.create_entity(
                "AssayMaterial",
                {"material_name": f"material-{a}-{m}", "assay": f"ASSAY{a}"},
                parent_id=sample.id,
                skip_validation=True,
            )
    return client


def _of_kind(seek: _FakeSeek, kind: str) -> list[dict[str, Any]]:
    return [payload for k, payload in seek.calls if k == kind]


class TestCompliantStructure:
    def test_the_investigation_is_marked_isa_json_compliant(self) -> None:
        # Without the flag SEEK refuses to export the Investigation as ISA-JSON
        # at all, whatever its Studies and Assays look like.
        seek = _FakeSeek()
        sync_dataset_to_seek(seek, _dataset(), project_id="1")
        assert _of_kind(seek, "investigation")[0]["compliant"] is True

    def test_each_study_owns_a_source_and_a_sample_collection_type(self) -> None:
        # A Study is compliant only once it owns these two; the export fails on
        # the Study otherwise.
        seek = _FakeSeek()
        sync_dataset_to_seek(seek, _dataset(), project_id="1")
        study = _of_kind(seek, "study")[0]
        assert study["source_attributes"] and study["collection_attributes"]

    def test_each_study_gets_exactly_one_assay_stream(self) -> None:
        seek = _FakeSeek()
        sync_dataset_to_seek(seek, _dataset(assays=2), project_id="1")
        assert len(_of_kind(seek, "stream")) == 1

    def test_every_assay_hangs_off_that_stream(self) -> None:
        seek = _FakeSeek()
        sync_dataset_to_seek(seek, _dataset(assays=2), project_id="1")
        assays = _of_kind(seek, "assay")
        assert len(assays) == 2
        # All under one stream, and none left dangling as a bare EXP assay --
        # an assay outside a stream does not render in SEEK's ISA study view.
        assert all(a["assay_stream_id"] is not None for a in assays)
        assert len({a["assay_stream_id"] for a in assays}) == 1

    def test_each_assay_owns_its_own_sample_type(self) -> None:
        # A stream chains its types together, so two assays of the same profile
        # entity need two Sample Types with different links -- sharing one
        # cannot express the chain.
        seek = _FakeSeek()
        sync_dataset_to_seek(seek, _dataset(assays=2), project_id="1")
        assert len(seek.assay_types) == 2
        owned = [next(iter(t.values())) for t in seek.assay_types.values()]
        assert len(set(owned)) == 2

    def test_an_assay_takes_its_input_from_the_studys_collection_type(self) -> None:
        seek = _FakeSeek()
        sync_dataset_to_seek(seek, _dataset(), project_id="1")
        study_id = next(iter(seek.study_types))
        collection_id = list(seek.study_types[study_id].values())[1]
        assert _of_kind(seek, "assay")[0]["input_sample_type_id"] == collection_id


class TestSamplePlacement:
    def test_a_material_lands_in_the_sample_type_of_the_assay_it_names(self) -> None:
        seek = _FakeSeek()
        sync_dataset_to_seek(seek, _dataset(assays=2), project_id="1")
        owned = {next(iter(t.values())) for t in seek.assay_types.values()}
        # The Source and the Sample go in the Study's two types; the materials
        # go in the Assay-owned ones.
        used = {s["sample_type_id"] for s in _of_kind(seek, "sample")}
        assert owned <= used
        assert len(owned) == 2

    def test_a_material_is_linked_to_the_assay_that_measured_it(self) -> None:
        seek = _FakeSeek()
        sync_dataset_to_seek(seek, _dataset(), project_id="1")
        linked = [s for s in _of_kind(seek, "sample") if s["assay_ids"]]
        assert len(linked) == 1, "exactly the assay material names an Assay"

    def test_each_level_names_the_one_above_it_as_its_input(self) -> None:
        # The exporter walks Source -> Sample -> material by these links and
        # fails with "undefined method map for nil" when one is missing.
        seek = _FakeSeek()
        sync_dataset_to_seek(seek, _dataset(), project_id="1")
        samples = _of_kind(seek, "sample")
        assert "Input (Title)" not in samples[0]["data"], "a Source heads the chain"
        assert all("Input (Title)" in s["data"] for s in samples[1:])

    def test_a_core_identity_field_becomes_the_title_attribute(self) -> None:
        seek = _FakeSeek()
        sync_dataset_to_seek(seek, _dataset(), project_id="1")
        assert _of_kind(seek, "sample")[0]["data"]["Title"] == "source-1"

    def test_a_sample_nested_under_an_assay_goes_in_that_assays_type_and_links_to_it(
        self,
    ) -> None:
        # Profiles like isa 1.0 nest the Sample directly under the Assay with no
        # material chain. SEEK hangs Samples off Assays, so the ancestor Assay
        # supplies both the Sample Type and the ISA link — without it the Sample
        # lands in the Study's Source type, reachable by nothing.
        client = MetaseedClient("isa", "1.0")
        inv = client.create_entity(
            "Investigation", {"identifier": "I"}, skip_validation=True
        )
        study = client.create_entity(
            "Study", {"identifier": "S"}, parent_id=inv.id, skip_validation=True
        )
        assay = client.create_entity(
            "Assay", {"identifier": "A"}, parent_id=study.id, skip_validation=True
        )
        client.create_entity(
            "Sample", {"name": "smp"}, parent_id=assay.id, skip_validation=True
        )
        seek = _FakeSeek()
        result = sync_dataset_to_seek(seek, client, project_id="1")
        assert not result.unlinked
        samples = _of_kind(seek, "sample")
        assert len(samples) == 1
        assay_seek_id = next(iter(result.assays.values()))
        owned_types = seek.assay_types[assay_seek_id].values()
        assert samples[0]["sample_type_id"] in owned_types
        assert samples[0]["assay_ids"] == [assay_seek_id]

    def test_a_sample_chain_that_never_reaches_an_assay_is_reported(self) -> None:
        # A Sample under a Study with no Assay anywhere below it is stored in
        # the Study's Source type, but nothing walking the ISA tree down from
        # the Investigation reaches it and a re-import drops it. It is still
        # created — and the result must say so rather than count it as placed.
        client = MetaseedClient("isa", "1.0")
        inv = client.create_entity(
            "Investigation", {"identifier": "I"}, skip_validation=True
        )
        study = client.create_entity(
            "Study", {"identifier": "S"}, parent_id=inv.id, skip_validation=True
        )
        client.create_entity(
            "Sample", {"name": "smp"}, parent_id=study.id, skip_validation=True
        )
        seek = _FakeSeek()
        result = sync_dataset_to_seek(seek, client, project_id="1")
        assert result.samples, "the Sample is still created"
        assert sorted(node_id for node_id, _ in result.unlinked) == sorted(
            result.samples
        )

    def test_a_complete_material_chain_reports_nothing_unlinked(self) -> None:
        # Source and Sample carry no Assay link of their own, but the chain ends
        # at a material that does — they are reachable, so nothing is reported.
        seek = _FakeSeek()
        result = sync_dataset_to_seek(seek, _dataset(), project_id="1")
        assert not result.unlinked

    def test_a_material_naming_no_assay_is_reported_not_silently_orphaned(
        self,
    ) -> None:
        # A material whose Assay reference matches nothing has no Sample Type to
        # go in, so it is reported rather than pushed somewhere unreachable.
        client = MetaseedClient("seek-ready-template", "3.0")
        inv = client.create_entity(
            "Investigation", {"identifier": "INV1"}, skip_validation=True
        )
        study = client.create_entity(
            "Study", {"identifier": "STU1"}, parent_id=inv.id, skip_validation=True
        )
        source = client.create_entity(
            "Source", {"source_name": "src"}, parent_id=study.id, skip_validation=True
        )
        sample = client.create_entity(
            "Sample", {"sample_name": "smp"}, parent_id=source.id, skip_validation=True
        )
        client.create_entity(
            "AssayMaterial",
            {"material_name": "orphan", "assay": "NO-SUCH-ASSAY"},
            parent_id=sample.id,
            skip_validation=True,
        )
        seek = _FakeSeek()
        result = sync_dataset_to_seek(seek, client, project_id="1")
        assert result.unlinked


class TestSampleData:
    def test_core_fields_route_and_scalar_lists_survive(self) -> None:
        from metaseed.seek.values import sample_data as _sample_data

        data = _sample_data(
            {
                "_node_id": "x",  # metadata key dropped
                "unique_id": "s1",  # core identity -> Title
                "description": "d",  # core -> Description
                "empty": "",  # empty dropped
                "organism": "human",  # non-core field kept under its own name
                "tags": ["a", "b"],  # scalar list kept (CV list)
                "nested": {"k": "v"},  # non-scalar dropped
                "mixed": ["a", {"k": 1}],  # list with a dict dropped
            }
        )
        assert data == {
            "Title": "s1",
            "Description": "d",
            "organism": "human",
            "tags": ["a", "b"],
        }

    def test_core_collapse_is_priority_ordered_not_dict_ordered(self) -> None:
        from metaseed.seek.values import sample_data as _sample_data

        assert _sample_data({"title": "label", "identifier": "ID-1"})["Title"] == "ID-1"
        assert _sample_data({"identifier": "ID-1", "title": "label"})["Title"] == "ID-1"
        assert (
            _sample_data({"identifier": "ID-1", "unique_id": "U-1"})["Title"] == "U-1"
        )


def test_sync_consumes_an_in_memory_spec_dataset() -> None:
    # A dataset built via ``from_spec`` (e.g. one produced by the SEEK importer)
    # has no installed profile file. sync must read its in-memory ProfileSpec
    # rather than calling SpecLoader unconditionally, which would raise
    # SpecLoadError for the derived "seek-imported" profile.
    spec = {
        "name": "seek-imported",
        "version": "1.0",
        "root_entity": "Investigation",
        "entities": {
            "Investigation": {
                "fields": [
                    {"name": "identifier", "type": "string", "required": True},
                    {"name": "title", "type": "string"},
                    {"name": "studies", "type": "list", "items": "Study"},
                ],
                "seek": {"role": "Investigation"},
            },
            "Study": {
                "fields": [
                    {"name": "identifier", "type": "string", "required": True},
                    {"name": "samples", "type": "list", "items": "Sample"},
                ],
                "seek": {"role": "Study"},
            },
            "Sample": {
                "fields": [{"name": "identifier", "type": "string"}],
                "seek": {"role": "Sample"},
            },
        },
    }
    dataset = MetaseedClient.from_spec(spec)
    inv = dataset.create_entity(
        "Investigation",
        {"identifier": "INV1", "title": "Imported"},
        skip_validation=True,
    )
    dataset.create_entity(
        "Study", {"identifier": "STU1"}, parent_id=inv.id, skip_validation=True
    )

    seek = _FakeSeek()
    result = sync_dataset_to_seek(seek, dataset, project_id="1")
    isa_kinds = [k for k, _ in seek.calls if k in ("investigation", "study")]
    assert isa_kinds == ["investigation", "study"]
    assert not result.errors


class TestProtocolValue:
    def test_every_sample_records_the_assay_that_produced_it_as_its_protocol(
        self,
    ) -> None:
        # ISAExporter refuses a Sample with no protocol ("has no protocol"), so a
        # structurally compliant push still fails to export without this.
        seek = _FakeSeek()
        sync_dataset_to_seek(seek, _dataset(), project_id="1")
        material = _of_kind(seek, "sample")[-1]
        assert material["data"]["Protocol"] == "Assay 0"


class TestTemplates:
    def test_every_sample_type_is_created_with_its_isa_template(self) -> None:
        # ISAExporter reads sample_type.isa_template.level, so a Sample Type
        # without one cannot be exported however correct its attributes are.
        seek = _FakeSeek()
        sync_dataset_to_seek(seek, _dataset(), project_id="1")
        study = _of_kind(seek, "study")[0]
        assert study["source_template_id"]
        assert study["collection_template_id"]
        assert _of_kind(seek, "assay")[0]["template_id"]

    def test_a_missing_template_is_reported_with_what_to_do(self) -> None:
        # Pushing past it succeeds and the export then fails inside SEEK,
        # naming nothing the user can act on.
        seek = _FakeSeek(templates_installed=False)
        result = sync_dataset_to_seek(seek, _dataset(), project_id="1")
        assert result.errors
        message = result.errors[0][1]
        assert "administrator" in message and "Templates" in message


class TestSharing:
    def test_nothing_is_shared_unless_asked(self) -> None:
        # SEEK's own default is private to the contributor, and widening that is
        # a decision about who can see every record metaseed pushes.
        seek = _FakeSeek()
        sync_dataset_to_seek(seek, _dataset(), project_id="1")
        assert _of_kind(seek, "investigation")[0]["sharing"] is None

    def test_the_chosen_level_reaches_every_isa_level(self) -> None:
        # ISA-JSON export needs at least "download": export_isa authorizes as
        # :download, so a private Investigation is refused even to its own
        # contributor over HTTP.
        seek = _FakeSeek()
        sync_dataset_to_seek(seek, _dataset(), project_id="1", sharing="download")
        assert _of_kind(seek, "investigation")[0]["sharing"] == "download"
        assert _of_kind(seek, "study")[0]["sharing"] == "download"
        assert _of_kind(seek, "assay")[0]["sharing"] == "download"

    def test_an_unknown_level_is_rejected_before_anything_is_created(self) -> None:
        from metaseed.seek.payloads import isa_assay_form

        with pytest.raises(ValueError, match="sharing must be one of"):
            isa_assay_form(title="A", study_id="1", assay_class_id=1, sharing="public")


def test_data_files_under_a_study_become_one_remote_data_file():
    """A study's file entities collapse to a single SEEK DataFile linking to the
    common base URL, with the filenames listed -- the files stay in external
    storage, SEEK holds the reference."""
    from metaseed import MetaseedClient
    from metaseed.seek.sync import sync_dataset_to_seek
    from metaseed.specs.schema import (
        EntityDefSpec as E,
    )
    from metaseed.specs.schema import (
        FieldSpec as F,
    )
    from metaseed.specs.schema import (
        FieldType as T,
    )
    from metaseed.specs.schema import (
        ProfileSpec,
        SeekEntityConfig,
    )

    spec = ProfileSpec(
        spec_version="0.6",
        version="1.0",
        name="df",
        display_name="DF",
        description="d",
        ontology="T",
        root_entity="Investigation",
        entities={
            "Investigation": E(
                description="d",
                seek=SeekEntityConfig(role="Investigation"),
                fields=[
                    F(name="identifier", type=T.STRING, is_identifier=True),
                    F(name="title", type=T.STRING, is_label=True),
                    F(name="studies", type=T.LIST, items="Study"),
                ],
            ),
            "Study": E(
                description="d",
                seek=SeekEntityConfig(role="Study"),
                fields=[
                    F(name="identifier", type=T.STRING, is_identifier=True),
                    F(name="title", type=T.STRING, is_label=True),
                    F(name="files", type=T.LIST, items="DataFile"),
                ],
            ),
            "DataFile": E(
                description="d",
                seek=SeekEntityConfig(role="DataFile"),
                fields=[
                    F(name="file_name", type=T.STRING, is_label=True),
                    F(name="file_location", type=T.URI),
                ],
            ),
        },
    )
    c = MetaseedClient.from_spec(spec.model_dump(mode="json"))
    inv = c.create_entity(
        "Investigation", {"identifier": "I", "title": "t"}, skip_validation=True
    )
    st = c.create_entity(
        "Study",
        {"identifier": "S", "title": "s"},
        parent_id=inv.id,
        skip_validation=True,
    )
    for n in ("a.raw", "b.raw"):
        c.create_entity(
            "DataFile",
            {"file_name": n, "file_location": f"s3://bucket/S/{n}"},
            parent_id=st.id,
            skip_validation=True,
        )

    seek = _FakeSeek()
    res = sync_dataset_to_seek(seek, c, project_id="1")

    assert len(res.data_files) == 1, res.data_files
    assert not res.errors, res.errors
    df_calls = [c for kind, c in seek.calls if kind == "data_file"]
    assert df_calls[0]["url"] == "s3://bucket/S/"
    assert (
        "a.raw" in df_calls[0]["description"] and "b.raw" in df_calls[0]["description"]
    )


class TestAssayReferenceIsDeclaredNotGuessed:
    def test_a_field_value_that_happens_to_match_an_assay_id_does_not_link(
        self,
    ) -> None:
        # The material names its Assay in the field the profile declares as a
        # reference. Scanning every value would link this sample to ASSAY0
        # because its description mentions it.
        seek = _FakeSeek()
        client = MetaseedClient("seek-ready-template", "3.0")
        inv = client.create_entity(
            "Investigation", {"identifier": "INV1"}, skip_validation=True
        )
        study = client.create_entity(
            "Study", {"identifier": "STU1"}, parent_id=inv.id, skip_validation=True
        )
        client.create_entity(
            "Assay",
            {"identifier": "ASSAY0", "title": "Assay 0"},
            parent_id=study.id,
            skip_validation=True,
        )
        source = client.create_entity(
            "Source", {"source_name": "src"}, parent_id=study.id, skip_validation=True
        )
        client.create_entity(
            "Sample",
            # organism_part happens to equal an assay identifier; that must not
            # turn this study-level Sample into an assay material.
            {"sample_name": "smp", "organism_part": "ASSAY0"},
            parent_id=source.id,
            skip_validation=True,
        )
        sync_dataset_to_seek(seek, client, project_id="1")
        study_level = [
            s for s in _of_kind(seek, "sample") if s["data"].get("Title") == "smp"
        ]
        assert study_level, "the sample was not created"
        assert study_level[0]["assay_ids"] is None, (
            "a coincidental value match linked a study-level Sample to an Assay"
        )

    def test_the_declared_reference_wins_over_a_coincidental_match(self) -> None:
        # The material's own name equals ASSAY1's identifier, but its declared
        # ``assay`` reference names ASSAY0. Scanning values in order would meet
        # material_name first and file the material under the wrong Assay.
        seek = _FakeSeek()
        client = MetaseedClient("seek-ready-template", "3.0")
        inv = client.create_entity(
            "Investigation", {"identifier": "INV1"}, skip_validation=True
        )
        study = client.create_entity(
            "Study", {"identifier": "STU1"}, parent_id=inv.id, skip_validation=True
        )
        for i in range(2):
            client.create_entity(
                "Assay",
                {"identifier": f"ASSAY{i}", "title": f"Assay {i}"},
                parent_id=study.id,
                skip_validation=True,
            )
        source = client.create_entity(
            "Source", {"source_name": "src"}, parent_id=study.id, skip_validation=True
        )
        sample = client.create_entity(
            "Sample", {"sample_name": "smp"}, parent_id=source.id, skip_validation=True
        )
        client.create_entity(
            "AssayMaterial",
            {"material_name": "ASSAY1", "assay": "ASSAY0"},
            parent_id=sample.id,
            skip_validation=True,
        )
        sync_dataset_to_seek(seek, client, project_id="1")
        material = next(
            s for s in _of_kind(seek, "sample") if s["data"].get("Title") == "ASSAY1"
        )
        # ASSAY0 was created first, so its own sample type id is lower; what
        # matters is that the material's assay is the declared one.
        declared = seek.assay_types  # assay id -> {title: sample type id}
        assay0_type = next(iter(declared[min(declared)].values()))
        assert material["sample_type_id"] == assay0_type, (
            "the material was filed under the coincidentally-matching Assay, "
            "not the one its reference names"
        )


class TestPushingTwiceDoesNotDuplicate:
    """Pushing the same dataset again used to create a second copy of
    everything: nothing looked for what the previous push had made, so an
    Investigation, its Study, its Assays and every Sample were created afresh.
    """

    @staticmethod
    def _remember(seek: _FakeSeek, result) -> _FakeSeek:
        """A SEEK that already holds what ``result`` created."""
        second = _FakeSeek(_n=seek._n)
        second.existing_investigations = {"My Investigation": "1"}
        second.existing_studies = {("Study one", "1"): "2"}
        second.existing_assays = {
            (title, "2"): str(index)
            for index, title in enumerate(("Study one - stream", "Assay 1"), start=3)
        }
        return second

    def test_the_second_push_creates_nothing_new(self) -> None:
        first = _FakeSeek()
        result = sync_dataset_to_seek(first, _dataset(), project_id="1")
        assert result.investigations, "the first push must create the investigation"

        second = self._remember(first, result)
        again = sync_dataset_to_seek(second, _dataset(), project_id="1")

        assert not _of_kind(second, "investigation"), (
            "a second push created another investigation"
        )
        assert not _of_kind(second, "study"), "a second push created another study"
        assert again.reused, "the reused records are not reported"

    def test_the_reused_investigation_is_still_reported(self) -> None:
        """A reused record must still map its node, or the caller cannot tell
        where the dataset ended up."""
        first = _FakeSeek()
        result = sync_dataset_to_seek(first, _dataset(), project_id="1")

        second = self._remember(first, result)
        again = sync_dataset_to_seek(second, _dataset(), project_id="1")

        assert set(again.investigations.values()) == {"1"}


class TestAnnotationOnlyEntitiesAreSynced:
    """The sync resolves JERM roles from annotations like every other path.

    fairds/preview/roles all pass entity.ontology_term to entity_jerm_class
    (the #234 fix), but place_node and the two sync.py sites computed the
    class from the NAME alone — so an entity called Measurement annotated as
    JERM:Assay planned into the chain, was exported by FDS, and was then
    skipped by the sync with 'has no SEEK role'.
    """

    def _client_with_annotated_assay(self) -> MetaseedClient:
        base = SpecLoader().load_profile("3.0", "seek-ready-template")
        spec = base.model_copy(deep=True)
        # Rename the Assay entity to a name outside the JERM name map, keeping
        # its JERM annotation as the only way to resolve its role.
        assay = spec.entities.pop("Assay")
        assay = assay.model_copy(update={"ontology_term": "JERM:Assay", "seek": None})
        spec.entities["Measurement"] = assay
        study_fields = []
        for study_field in spec.entities["Study"].fields:
            if study_field.items == "Assay":
                study_field = study_field.model_copy(update={"items": "Measurement"})
            study_fields.append(study_field)
        spec.entities["Study"] = spec.entities["Study"].model_copy(
            update={"fields": study_fields}
        )

        client = MetaseedClient.from_spec(spec)
        inv = client.create_entity(
            "Investigation",
            {"identifier": "INV1", "title": "Inv"},
            skip_validation=True,
        )
        study = client.create_entity(
            "Study",
            {"identifier": "STU1", "title": "Study"},
            parent_id=inv.id,
            skip_validation=True,
        )
        client.create_entity(
            "Measurement",
            {"identifier": "M1", "title": "Measured"},
            parent_id=study.id,
            skip_validation=True,
        )
        return client

    def test_an_annotated_assay_is_placed(self) -> None:
        seek = _FakeSeek()
        sync_dataset_to_seek(seek, self._client_with_annotated_assay(), project_id="1")

        assert _of_kind(seek, "assay"), "the annotation-only Assay must be exported"


class TestFreshTypesAreFound:
    def test_the_type_lookup_outlasts_a_stale_first_read(self) -> None:
        # SEEK's list routes can serve a stale view right after a create (its
        # authorization tables are maintained by background jobs), omitting the
        # Sample Types the sync just made. One stale read must not turn every
        # Source under the Study into an unlinked sample.
        class _StaleFirstRead(_FakeSeek):
            def __init__(self) -> None:
                super().__init__()
                self.stale_reads: set[str] = set()

            def study_sample_type_ids(self, study_id: str) -> dict[str, str]:
                if study_id not in self.stale_reads:
                    self.stale_reads.add(study_id)
                    return {}
                return super().study_sample_type_ids(study_id)

        seek = _StaleFirstRead()
        result = sync_dataset_to_seek(seek, _dataset(), project_id="1")
        assert not result.unlinked, result.unlinked
        assert not result.errors, result.errors

    def test_created_study_sample_types_are_recorded_for_the_caller(self) -> None:
        # A deleted Study leaves its Sample Types behind as orphans; a caller
        # cleaning up after itself (the live tests do) needs their ids.
        seek = _FakeSeek()
        result = sync_dataset_to_seek(seek, _dataset(), project_id="1")
        created = {t for types in seek.study_types.values() for t in types.values()}
        assert set(result.sample_types) == created
