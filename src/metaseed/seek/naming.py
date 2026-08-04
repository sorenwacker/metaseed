"""The property URI a field is published under in SEEK.

SEEK matches a sample imported from a FAIR Data Station to an attribute of its
Sample Type by this URI, so the Sample Type provisioning
(:mod:`metaseed.seek.provision`) and the data RDF (:mod:`metaseed.seek.fairds`)
must derive it identically. Building it by concatenation let a field name
containing a space through unescaped, which SEEK rejects with
``sample_attributes.pid: not a valid URI`` and rdflib refuses to serialize.
"""

from urllib.parse import quote

SCHEMA_BASE = "http://schema.org/"
"""Namespace the property URIs live in; also bound as ``schema:`` in the RDF."""


def property_uri(field_name: str) -> str:
    """Return the ``schema:`` property URI for ``field_name``.

    The name is percent-encoded, so a field named with a space, a slash or any
    other character that is not legal in a URI path still yields a usable one.
    A name that needs no encoding is returned unchanged, which keeps every URI
    already provisioned in a SEEK instance exactly as it was.

    Args:
        field_name: The field's name as the profile declares it.

    Returns:
        An absolute URI in the schema.org namespace.
    """
    return SCHEMA_BASE + quote(field_name, safe="")
