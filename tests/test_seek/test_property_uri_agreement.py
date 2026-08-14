"""Provisioning and the export must name a field by the identical URI.

SEEK matches a sample imported from a FAIR Data Station to an attribute of its
Sample Type by the property URI. The Sample Type carries it as ``pid``; the data
RDF carries it as the predicate. If the two disagree the import matches nothing
and reports no error -- the samples simply arrive empty.

They are derived at two separate sites, which is how they came to disagree: a
field named with a space was encoded in the Sample Type and concatenated raw in
the export, so the export could not even be serialized. The earlier tests
asserted the two agreed only on the site that had been changed.
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest
from tests.builtin_specs import builtin_only_loader

from metaseed.seek.naming import property_uri
from metaseed.seek.provision import build_provisioning_plan

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def _built_in_profiles():
    """Every built-in profile, newest version, as (name, spec)."""
    loader = builtin_only_loader()
    for name in loader.list_profiles():
        versions = loader.list_versions(name)
        if not versions:
            continue
        # Deliberately not guarded: a built-in profile that will not load is a
        # defect, and hiding it here would leave this gate quietly covering
        # fewer profiles than it appears to.
        yield name, loader.load_profile(versions[-1], name)


@pytest.mark.parametrize(
    "name,spec",
    list(_built_in_profiles()),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_every_provisioned_pid_is_a_usable_uri(name, spec) -> None:
    """A pid SEEK rejects fails the whole Sample Type, naming no attribute."""
    plan = build_provisioning_plan(spec)

    for sample_type in plan.sample_types:
        for attribute in sample_type.attributes:
            if attribute.pid is None:
                continue
            parsed = urlparse(attribute.pid)
            assert parsed.scheme and parsed.netloc, f"{name}: {attribute.pid!r}"
            assert " " not in attribute.pid, f"{name}: {attribute.pid!r}"


@pytest.mark.parametrize(
    "name,spec",
    list(_built_in_profiles()),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_the_pid_is_what_the_export_would_emit(name, spec) -> None:
    """Both sides must go through property_uri, not concatenate independently.

    Comparing the plan against the helper is what ties the two sites together:
    an export that built its predicate any other way would drift from the pid
    silently, and an import would match nothing.
    """
    plan = build_provisioning_plan(spec)

    for sample_type in plan.sample_types:
        for attribute in sample_type.attributes:
            if attribute.pid is None:
                continue
            local = attribute.pid.rsplit("/", 1)[-1]
            assert attribute.pid == property_uri(_decoded(local)), (
                f"{name}: {attribute.title} pid {attribute.pid!r} is not what "
                "property_uri would produce, so the export will not match it"
            )


def _decoded(local: str) -> str:
    from urllib.parse import unquote

    return unquote(local)


# Every built-in profile happens to use URI-safe field names, so the checks above
# pass whatever the code does. The names that broke this came from a profile
# someone authored, and a profile is user-supplied data: nothing stops a field
# being called "Source Name". These make the checks bite.
AWKWARD_FIELD_NAMES = [
    "Source Name",
    "growth medium",
    "yield/ha",
    "size (cm)",
    "temp °C",
]


def _profile_with_awkward_names():
    from metaseed.specs.schema import EntityDefSpec, FieldSpec, FieldType, ProfileSpec

    return ProfileSpec(
        version="1.0",
        name="awkward",
        display_name="Awkward",
        description="d",
        ontology="T",
        root_entity="Sample",
        entities={
            "Sample": EntityDefSpec(
                description="d",
                fields=[
                    FieldSpec(name=n, type=FieldType.STRING)
                    for n in AWKWARD_FIELD_NAMES
                ],
            )
        },
    )


@pytest.mark.parametrize("field_name", AWKWARD_FIELD_NAMES)
def test_an_authored_field_name_still_yields_a_usable_pid(field_name) -> None:
    """SEEK rejects the whole Sample Type over one unusable pid, naming none."""
    plan = build_provisioning_plan(_profile_with_awkward_names())

    pids = {
        attribute.title: attribute.pid
        for sample_type in plan.sample_types
        for attribute in sample_type.attributes
        if attribute.pid is not None
    }

    pid = pids.get(field_name)
    assert pid is not None, f"{field_name} produced no pid; pids: {pids}"
    parsed = urlparse(pid)
    assert parsed.scheme and parsed.netloc, pid
    assert " " not in pid, pid
    assert pid == property_uri(field_name), pid


def test_the_export_names_those_fields_identically() -> None:
    """The predicate in the data RDF is what an import matches the pid against."""
    pytest.importorskip("rdflib")
    from metaseed import MetaseedClient
    from metaseed.seek.fairds import to_fair_data_station_rdf

    spec = _profile_with_awkward_names()
    client = MetaseedClient.from_spec(spec.model_dump(mode="json"))
    client.create_entity(
        "Sample", dict.fromkeys(AWKWARD_FIELD_NAMES, "v"), skip_validation=True
    )

    rdf = to_fair_data_station_rdf(client)
    text = rdf.decode() if isinstance(rdf, bytes) else rdf

    plan = build_provisioning_plan(spec)
    for sample_type in plan.sample_types:
        for attribute in sample_type.attributes:
            if attribute.pid is None or attribute.title not in AWKWARD_FIELD_NAMES:
                continue
            local = attribute.pid.rsplit("/", 1)[-1]
            assert local in text, (
                f"{attribute.title}: the export does not carry the pid "
                f"{attribute.pid!r} that provisioning registered"
            )
