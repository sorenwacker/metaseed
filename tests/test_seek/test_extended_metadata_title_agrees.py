"""The EMT title the sync looks up must equal the one uploading the TTL creates.

Two paths reach the same SEEK Extended Metadata Type: uploading the model TTL,
which SEEK titles ``FDS <Level> - <packageName>``, and the sync, which looks the
type up by title to attach a Study's or Assay's metadata. When those titles
diverged the push failed with "no Extended Metadata Type titled ...", having
created the type under a different name. This gate ties the two to one shared
derivation so they cannot drift again.
"""

from __future__ import annotations

from rdflib import RDF, Graph, Namespace

from metaseed.seek.fairds import to_fair_data_station_model_rdf
from metaseed.seek.roles import fair_ds_extended_metadata_title
from metaseed.specs.loader import SpecLoader

JERM = Namespace("http://jermontology.org/ontology/JERMOntology#")
SCHEMA = Namespace("http://schema.org/")
FAIR = Namespace("http://fairbydesign.nl/ontology/")


def _seek_title_from_ttl(ttl: str, jerm_level: str) -> str:
    """Replicate SEEK's FAIR-DS title formula from what the TTL actually emits.

    SEEK builds ``"FDS #{supported_type.humanize} - #{packageName}"`` for a node
    typed ``jerm:<supported_type>``; ``humanize`` leaves Study/Assay/Investigation
    unchanged. The package name is read from ``fair:packageName`` on the node.
    """
    graph = Graph()
    graph.parse(data=ttl, format="turtle")
    node = next(graph.subjects(RDF.type, JERM[jerm_level]))
    package = str(next(graph.objects(node, FAIR.packageName)))
    return f"FDS {jerm_level} - {package}"


def test_the_sync_lookup_title_matches_what_seek_creates_from_the_ttl() -> None:
    profile = SpecLoader().load_profile(version="1.2", profile="cropxr-phenotyping")
    ttl = to_fair_data_station_model_rdf(profile)
    for level in ("Study", "Assay"):
        seek_title = _seek_title_from_ttl(ttl, level)
        sync_title = fair_ds_extended_metadata_title(
            level, profile.name, profile.version
        )
        assert seek_title == sync_title, (
            f"{level}: SEEK would title the EMT {seek_title!r} but the sync looks up "
            f"{sync_title!r}; a push would fail with 'no Extended Metadata Type titled ...'"
        )


def test_the_title_names_the_model_not_a_random_suffix() -> None:
    assert (
        fair_ds_extended_metadata_title("Study", "cropxr-phenotyping", "1.2")
        == "FDS Study - cropxr-phenotyping 1.2"
    )
