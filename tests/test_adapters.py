"""Tests for the adapter (plugin) registry."""

from __future__ import annotations

import importlib.util

import pytest

from metaseed import adapters


def test_registry_covers_the_known_adapters():
    keys = {a.key for a in adapters.ADAPTERS}
    assert {"ena", "pride", "brapi", "metabolights", "dcat", "seek"} <= keys


def test_get_adapter_and_is_known():
    assert adapters.is_known("seek")
    assert not adapters.is_known("nope")
    assert adapters.get_adapter("seek").extra == "seek"
    with pytest.raises(KeyError):
        adapters.get_adapter("nope")


def test_is_available_true_when_deps_present():
    # httpx is a dev dependency, so seek's requirement is satisfied here.
    assert adapters.is_available(adapters.get_adapter("seek"))


def test_is_available_false_when_missing(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda _m: None)
    assert not adapters.is_available(adapters.get_adapter("seek"))


def test_is_available_survives_find_spec_raising(monkeypatch):
    def boom(_m: str):
        raise ModuleNotFoundError(_m)

    monkeypatch.setattr(importlib.util, "find_spec", boom)
    assert not adapters.is_available(adapters.get_adapter("dcat"))
