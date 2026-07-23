"""#98: richer per-field metadata surfaced through every consumer surface.

``example``/``options``/``unit``/``label``/``tier`` must appear via
``helper.field_info``, ``forms.get_field_data``, ``client.get_entity_fields``
(FieldInfo) and the MCP ``_field_to_dict`` when a field declares them, and be
absent otherwise. ``options`` falls back to ``constraints.enum``.
"""

from __future__ import annotations

from metaseed.agent.mcp.tools.profiles import _field_to_dict
from metaseed.api.client import MetaseedClient
from metaseed.forms import get_field_data
from metaseed.specs.schema import Constraints, FieldSpec, FieldType

_SPEC = {
    "name": "demo",
    "version": "1.0",
    "root_entity": "Thing",
    "entities": {
        "Thing": {
            "fields": [
                {
                    "name": "height",
                    "type": "float",
                    "unit": "cm",
                    "label": "Plant height",
                    "example": 42.0,
                    "tier": "recommended",
                    "description": "d",
                },
                {
                    "name": "status",
                    "type": "string",
                    "constraints": {"enum": ["a", "b"]},
                    "description": "d",
                },
                {"name": "plain", "type": "string", "description": "d"},
            ]
        }
    },
}

_META_KEYS = ("example", "options", "unit", "label", "tier")


def _helper():
    return MetaseedClient.from_spec(_SPEC)._facade.Thing


def test_field_info_carries_declared_metadata():
    info = _helper().field_info("height")
    assert info["example"] == 42.0
    assert info["unit"] == "cm"
    assert info["label"] == "Plant height"
    assert info["tier"] == "recommended"


def test_field_info_options_fall_back_to_enum():
    info = _helper().field_info("status")
    assert info["options"] == ["a", "b"]


def test_field_info_omits_absent_metadata():
    info = _helper().field_info("plain")
    assert not any(k in info for k in _META_KEYS)


def test_get_field_data_carries_metadata():
    fields = {f["name"]: f for f in get_field_data(_helper())}
    assert fields["height"]["unit"] == "cm"
    assert fields["height"]["example"] == 42.0
    assert fields["status"]["options"] == ["a", "b"]
    assert not any(k in fields["plain"] for k in _META_KEYS)


def test_client_field_info_carries_metadata():
    client = MetaseedClient.from_spec(_SPEC)
    fields = {f.name: f for f in client.get_entity_fields("Thing")}
    assert fields["height"].unit == "cm"
    assert fields["height"].label == "Plant height"
    assert fields["height"].example == 42.0
    assert fields["height"].tier == "recommended"
    assert fields["status"].options == ["a", "b"]
    # Absent metadata is None, not fabricated.
    assert fields["plain"].unit is None
    assert fields["plain"].options is None
    assert fields["plain"].example is None


def test_mcp_field_to_dict_carries_metadata():
    height = _field_to_dict(
        FieldSpec(
            name="height",
            type=FieldType.FLOAT,
            unit="cm",
            label="Plant height",
            example=42.0,
            tier="recommended",
        )
    )
    assert height["unit"] == "cm"
    assert height["example"] == 42.0
    assert height["tier"] == "recommended"

    enum_field = _field_to_dict(
        FieldSpec(
            name="status",
            type=FieldType.STRING,
            constraints=Constraints(enum=["a", "b"]),
        )
    )
    assert enum_field["options"] == ["a", "b"]

    plain = _field_to_dict(FieldSpec(name="plain", type=FieldType.STRING))
    assert not any(k in plain for k in _META_KEYS)


def test_fields_by_tier_groups_fields():
    tiers = _helper().fields_by_tier
    assert tiers["recommended"] == ["height"]
    assert set(tiers["optional"]) == {"status", "plain"}
    assert tiers["required"] == []
