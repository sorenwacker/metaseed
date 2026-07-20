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
