"""A client built from a spec validates against THAT spec (260816 review).

`MetaseedClient.from_spec()` / `from_yaml()` are the documented way to use a
custom or generated schema, but `validate()` discarded the spec the client was
composed with and re-resolved one by (profile, version) from disk. No such file
exists for a supplied spec, so every entity came back as
"Unknown entity type: X - Profile not found", and a genuinely invalid entity
was indistinguishable from a valid one.

This is the injected-collaborator rule: the validation layer reached out to a
global loader to re-find something the caller had already handed it.
"""

from __future__ import annotations

from metaseed import MetaseedClient

SPEC = {
    "version": "1.0",
    "name": "supplied_spec_probe",
    "root_entity": "Sample",
    "entities": {
        "Sample": {
            "fields": [
                {"name": "unique_id", "type": "string", "required": True},
                {"name": "title", "type": "string", "required": True},
            ]
        }
    },
}


def _client() -> MetaseedClient:
    return MetaseedClient.from_spec(SPEC)


def test_a_valid_entity_is_reported_valid() -> None:
    client = _client()
    client.create_entity("Sample", {"unique_id": "S1", "title": "t"})

    result = client.validate()

    assert result.valid, [i.message for i in result.issues]


def test_a_missing_required_field_is_still_reported() -> None:
    """The fix must not make everything valid — the spec must be enforced."""
    client = _client()
    client.create_entity("Sample", {"unique_id": "S1"}, skip_validation=True)

    result = client.validate()

    assert not result.valid
    messages = " ".join(i.message for i in result.issues).lower()
    assert "title" in messages, messages
    assert "profile not found" not in messages


def test_a_named_profile_still_validates_as_before() -> None:
    """The loader path stays for clients built by profile name."""
    client = MetaseedClient("miappe", "1.2")
    client.create_entity("Investigation", {"unique_id": "INV-1"}, skip_validation=True)

    result = client.validate()

    messages = " ".join(i.message for i in result.issues).lower()
    assert "profile not found" not in messages
