"""Nested-entity resolution is bound to the class, not to a mutable global.

The global ModelContext's profile/version was mutated by every get_model call
and every facade build, while `_convert_nested_entities` ran at validation
time — arbitrarily later — and resolved against whatever was set LAST.
Building a second facade for another profile made every later validation
through the first facade resolve nested entities in the wrong context:
MIAPPE and ISA share entity names (Investigation, Study, Person), so the
wrong profile's model was instantiated, or resolution silently returned None
and left the dict unconverted. The generated class now carries its own
profile:version and resolves with it.
"""

from __future__ import annotations

from metaseed.facade import ProfileFacade


def test_a_second_facade_does_not_hijack_the_firsts_nested_resolution() -> None:
    miappe = ProfileFacade("miappe", "1.2")
    ProfileFacade("isa", "1.0")  # mutates the ambient context last

    node = miappe.add_entity(
        "Investigation",
        {
            "unique_id": "INV-1",
            "title": "T",
            "contacts": [{"name": "Dr. One", "email": "one@example.org"}],
        },
        skip_validation=False,
    )

    contact = node.instance.contacts[0]
    # The nested dict must convert against MIAPPE's Person, not ISA's.
    assert type(contact).__name__ == "Person"
    fields = set(getattr(type(contact), "__entity_fields__", {}) | {})
    assert type(contact).model_fields.keys() >= {"name", "email"}, fields
    key = getattr(type(contact), "__model_key__", None)
    assert key == ("miappe", "1.2"), (
        f"the nested model resolved under {key}, not the facade's own profile"
    )


def test_get_model_and_the_facade_agree_on_one_class() -> None:
    """The dual caches held two distinct classes for the same entity."""
    from metaseed.models import get_model

    facade = ProfileFacade("miappe", "1.2")
    from_get_model = get_model("Person", version="1.2", profile="miappe")

    assert facade.Person.model is from_get_model, (
        "two caches, two classes: nested conversion returns instances of a "
        "different class than the facade's own helper"
    )
