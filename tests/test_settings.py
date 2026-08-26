"""Tests for the instance settings / adapter feature switch."""

from __future__ import annotations

import pytest

from metaseed import adapters
from metaseed.settings import Settings


def test_default_enabled_when_available(tmp_path):
    settings = Settings(tmp_path / "settings.json")
    assert settings.adapter_enabled("seek") is True  # httpx installed


def test_unknown_key_is_disabled(tmp_path):
    assert Settings(tmp_path / "settings.json").adapter_enabled("nope") is False


def test_override_persists_across_instances(tmp_path):
    path = tmp_path / "settings.json"
    Settings(path).set_adapter_enabled("seek", False)
    assert path.exists()
    assert Settings(path).adapter_enabled("seek") is False  # reloaded from disk


def test_set_unknown_key_raises(tmp_path):
    with pytest.raises(KeyError):
        Settings(tmp_path / "s.json").set_adapter_enabled("nope", True)


def test_enable_unavailable_adapter_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "is_available", lambda _info: False)
    with pytest.raises(ValueError, match="pip install"):
        Settings(tmp_path / "s.json").set_adapter_enabled("seek", True)


def test_stored_true_reads_false_when_extra_gone(tmp_path, monkeypatch):
    path = tmp_path / "s.json"
    Settings(path).set_adapter_enabled("seek", True)  # available now
    monkeypatch.setattr(adapters, "is_available", lambda _info: False)
    assert Settings(path).adapter_enabled("seek") is False


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("not json {", encoding="utf-8")
    assert Settings(path).adapter_enabled("seek") is True


def test_adapter_config_round_trips_and_drops_unknown_fields(tmp_path):
    path = tmp_path / "s.json"
    Settings(path).set_adapter_config(
        "seek", {"url": "http://x:3001", "api_key": "k", "bogus": "no"}
    )
    config = Settings(path).get_adapter_config("seek")  # reloaded from disk
    assert config == {"url": "http://x:3001", "api_key": "k"}  # bogus dropped


def test_adapter_config_blank_clears_a_field(tmp_path):
    path = tmp_path / "s.json"
    s = Settings(path)
    s.set_adapter_config("seek", {"url": "http://x:3001"})
    s.set_adapter_config("seek", {"url": ""})
    assert "url" not in Settings(path).get_adapter_config("seek")


def test_set_config_for_unknown_adapter_raises(tmp_path):
    with pytest.raises(KeyError):
        Settings(tmp_path / "s.json").set_adapter_config("nope", {"url": "x"})


def test_adapter_config_drops_script_url_schemes(tmp_path):
    # A value that would execute if rendered as a link is refused, not stored.
    path = tmp_path / "s.json"
    s = Settings(path)
    s.set_adapter_config("seek", {"url": "http://ok:3001"})
    for evil in ("javascript:alert(1)", "JavaScript:alert(1)", "data:text/html,x"):
        s.set_adapter_config("seek", {"url": evil})
        assert Settings(path).get_adapter_config("seek")["url"] == "http://ok:3001"


def test_settings_are_written_readable_only_by_their_owner(tmp_path):
    """The file holds a SEEK API key and a hub access token in plain text.

    At the default mode every account on the machine can read them, which on a
    shared workstation hands over both services.
    """
    import stat

    settings = Settings(tmp_path / "settings.json")
    settings.set_adapter_config(
        "hub", {"url": "https://hub.test", "token": "msh_secret"}
    )
    mode = stat.S_IMODE((tmp_path / "settings.json").stat().st_mode)
    assert mode == 0o600, (
        f"settings.json is {oct(mode)}; a credential file must be 0600"
    )
