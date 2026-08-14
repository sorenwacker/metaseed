"""One malformed vocabulary file must not turn every term check into a crash.

`from_directory` fed each `*.json` straight to `LocalVocabulary.from_file`,
so broken JSON (or a file naming no ontology) raised on the first lazy router
build — deep inside a validator, with a traceback pointing nowhere near the
bad file. The module docstring promises the source will "answer honestly, and
say when it cannot": the load error now names the file, and `check_term`
reports NOT_CHECKED instead of raising.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from metaseed.services.local_terms import VocabularyStore
from metaseed.services.term_check import Outcome, check_term


def test_from_directory_names_the_bad_file(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(ValueError, match=r"bad\.json"):
        VocabularyStore.from_directory(tmp_path)


def test_check_term_reports_not_checked_when_the_sources_cannot_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "bad.json").write_text("{broken", encoding="utf-8")
    monkeypatch.setenv("METASEED_VOCABULARIES", str(tmp_path))
    from metaseed.services import terms

    monkeypatch.setattr(terms, "_router_var", terms.ContextVar("router", default=None))

    verdict = check_term("TO:0000387", None)

    assert verdict.outcome is Outcome.NOT_CHECKED
    assert "could not be checked" in (verdict.message or "")
