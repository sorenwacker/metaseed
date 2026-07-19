"""Tests for the shared mapper helpers (metaseed._mapping)."""

from __future__ import annotations

from metaseed._mapping import clean, clean_all


class TestClean:
    def test_drops_empty_values(self):
        assert clean(
            {"a": None, "b": "", "c": [], "d": {}, "e": "keep"}
        ) == {"e": "keep"}

    def test_keeps_falsy_but_meaningful_values(self):
        # 0 / 0.0 / False are meaningful and must be kept.
        assert clean({"a": 0, "b": 0.0, "c": False, "d": "x"}) == {
            "a": 0,
            "b": 0.0,
            "c": False,
            "d": "x",
        }

    def test_empty_input_is_empty(self):
        assert clean({}) == {}


class TestCleanAll:
    def test_cleans_each_and_drops_empty_rows(self):
        rows = [
            {"a": "x", "b": ""},
            {"a": None, "b": {}},  # becomes empty -> dropped
            {"c": 0},  # 0 kept -> row survives
        ]
        assert clean_all(rows) == [{"a": "x"}, {"c": 0}]

    def test_empty_list(self):
        assert clean_all([]) == []
